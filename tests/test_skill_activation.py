"""Real HTTP and PostgreSQL evidence for exact-version Skill lifecycle."""

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_control_acceptance import (
    ADMIN_KEY,
    DATABASE_URL,
    RESTRICTED_KEY,
    client,  # noqa: F401 — pytest registers the imported fixture
    headers,
    migrated_acceptance_database,  # noqa: F401 — module-scoped autouse fixture
)
from test_skill_publication import skill_body

from sre_agent.persistence.repositories import AuditRepository


def test_skill_activation_is_exact_authorized_persisted_and_idempotent(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    published = client.post(
        "/v1/skills/versions",
        json={
            "skill_id": "activation-demo",
            "version": "1.0.0",
            "owner_id": "demo-human",
            "manifest": {
                "display_name": "Activation demo",
                "description": "Exact version lifecycle fixture.",
                "instructions": "Keep this version immutable.",
                "dependencies": [],
            },
        },
        headers={
            "Authorization": f"Bearer {ADMIN_KEY}",
            "Idempotency-Key": "publish-activation-demo-1",
        },
    )
    path = "/v1/skills/activation-demo/1.0.0/status"
    denied = client.put(
        path,
        json={"status": "inactive", "expected_updated_at": "2026-09-01T00:00:00Z"},
        headers={"Authorization": f"Bearer {RESTRICTED_KEY}"},
    )
    initial = client.get(
        "/v1/skills/activation-demo/1.0.0",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert published.status_code == 201
    assert denied.status_code == 403, denied.text
    assert initial.status_code == 200

    inactive = client.put(
        path,
        json={"status": "inactive", "expected_updated_at": initial.json()["created_at"]},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert inactive.status_code == 200, inactive.text
    hidden = client.get(
        "/v1/skills/activation-demo/1.0.0",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    replay = client.put(
        path,
        json={"status": "inactive", "expected_updated_at": inactive.json()["updated_at"]},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    stale = client.put(
        path,
        json={"status": "active", "expected_updated_at": initial.json()["created_at"]},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )

    assert inactive.status_code == 200, inactive.text
    assert inactive.json()["status"] == "inactive"
    assert hidden.status_code == 404
    assert replay.status_code == 200
    assert replay.json()["updated_at"] == inactive.json()["updated_at"]
    assert stale.status_code == 409

    activated = client.put(
        path,
        json={"status": "active", "expected_updated_at": inactive.json()["updated_at"]},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    visible = client.get(
        "/v1/skills/activation-demo/1.0.0",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert visible.status_code == 200
    assert visible.json()["version"] == "1.0.0"
    with psycopg.connect(DATABASE_URL) as connection:
        status = connection.execute(
            "SELECT status FROM resources WHERE resource_type='skill' "
            "AND resource_id='activation-demo@1.0.0'"
        ).fetchone()
    assert status == ("active",)


def test_status_audit_failure_rolls_back_and_allows_clean_retry(
    client: TestClient,  # noqa: F811 — pytest fixture binding
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = skill_body() | {"skill_id": "atomic-status"}
    published = client.post(
        "/v1/skills/versions", json=body, headers=headers(idempotency_key="atomic-status-create")
    )
    assert published.status_code == 201
    path = "/v1/skills/atomic-status/1.0.0/status"
    update = {"status": "inactive", "expected_updated_at": published.json()["created_at"]}

    def persisted_status():
        with psycopg.connect(DATABASE_URL) as connection:
            return connection.execute(
                "SELECT status, updated_at FROM resources "
                "WHERE resource_type='skill' AND resource_id='atomic-status@1.0.0'"
            ).fetchone()

    before = persisted_status()
    original = AuditRepository.append

    async def fail_after_append(repository, event):
        await original(repository, event)
        if event.operation == "catalog.status.replace":
            raise RuntimeError("synthetic terminal audit failure")

    with monkeypatch.context() as patch:
        patch.setattr(AuditRepository, "append", fail_after_append)
        failed = client.put(path, json=update, headers=headers())
    assert failed.status_code == 503
    assert persisted_status() == before
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT count(*) FROM audit_events WHERE correlation->>'request_id'=%s",
            (failed.json()["request_id"],),
        ).fetchone() == (0,)
    retried = client.put(path, json=update, headers=headers())
    assert retried.status_code == 200
    assert persisted_status()[0] == "inactive"
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT response_status FROM audit_events "
            "WHERE operation='catalog.status.replace' AND occurred_at > %s",
            (published.json()["created_at"],),
        ).fetchall() == [(200,)]


@pytest.mark.parametrize(("version", "status"), [("1.0.0", 404), ("1" * 29 + ".0.0", 422)])
def test_status_missing_or_oversized_version_is_audited(
    client: TestClient,  # noqa: F811 — pytest fixture binding
    version: str,
    status: int,
) -> None:
    result = client.put(
        f"/v1/skills/missing-status/{version}/status",
        headers=headers(),
        json={"status": "inactive", "expected_updated_at": "2026-09-01T00:00:00Z"},
    )
    assert result.status_code == status, result.text
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT response_status, operation FROM audit_events "
            "WHERE correlation->>'request_id'=%s",
            (result.json()["request_id"],),
        ).fetchone() == (status, "catalog.status.replace")
