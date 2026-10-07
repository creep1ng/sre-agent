"""Real HTTP and PostgreSQL evidence for immutable Skill publication."""

import json

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


def skill_body() -> dict[str, object]:
    return {
        "skill_id": "incident-triage-demo",
        "version": "1.0.0",
        "owner_id": "demo-human",
        "manifest": {
            "display_name": "Incident triage",
            "description": "A concise incident triage guide for an independent maintainer.",
            "instructions": (
                "Assess impact, identify recent changes, and record evidence "
                "before proposing recovery."
            ),
            "dependencies": [],
        },
    }


def test_skill_publication_is_closed_idempotent_and_persisted(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    body = skill_body()

    denied = client.post(
        "/v1/skills/versions",
        json=body,
        headers=headers(RESTRICTED_KEY, "publish-skill-331-denied"),
    )
    first = client.post(
        "/v1/skills/versions",
        json=body,
        headers=headers(idempotency_key="publish-skill-331-first"),
    )
    replay = client.post(
        "/v1/skills/versions",
        json=body,
        headers=headers(idempotency_key="publish-skill-331-replay"),
    )
    collision = client.post(
        "/v1/skills/versions",
        json={
            **body,
            "manifest": {
                **body["manifest"],  # type: ignore[arg-type]
                "instructions": "Different instructions must not replace a published version.",
            },
        },
        headers=headers(idempotency_key="publish-skill-331-collision"),
    )
    arbitrary_path = client.post(
        "/v1/skills/versions",
        json={**body, "skill_id": "path-skill", "path": "../../etc/passwd"},
        headers=headers(idempotency_key="publish-skill-331-path"),
    )
    secret_config = client.post(
        "/v1/skills/versions",
        json={
            **body,
            "skill_id": "secret-skill",
            "config": {"api_key": "never-persist-this"},
        },
        headers=headers(idempotency_key="publish-skill-331-secret"),
    )
    oversized = client.post(
        "/v1/skills/versions",
        json={
            **body,
            "skill_id": "oversized-skill",
            "manifest": {
                **body["manifest"],  # type: ignore[arg-type]
                "instructions": "x" * 17_000,
            },
        },
        headers=headers(idempotency_key="publish-skill-331-size"),
    )
    fetched = client.get(
        "/v1/skills/incident-triage-demo/1.0.0",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )

    assert denied.status_code == 403
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json()["resource_id"] == "incident-triage-demo@1.0.0"
    assert collision.status_code == 409, collision.text
    assert arbitrary_path.status_code == secret_config.status_code == oversized.status_code == 422
    assert fetched.status_code == 200
    assert fetched.json()["manifest"] == body["manifest"]

    with psycopg.connect(DATABASE_URL) as connection:
        persisted = connection.execute(
            "SELECT skill_id, version, owner_id, manifest, content_sha256 "
            "FROM skill_versions WHERE skill_id = %s AND version = %s",
            ("incident-triage-demo", "1.0.0"),
        ).fetchone()
        resource_count = connection.execute(
            "SELECT count(*) FROM resources WHERE resource_type='skill' "
            "AND resource_id='incident-triage-demo@1.0.0'"
        ).fetchone()[0]
        invalid_count = connection.execute(
            "SELECT count(*) FROM skill_versions WHERE skill_id IN "
            "('path-skill', 'secret-skill', 'oversized-skill')"
        ).fetchone()[0]
        audit_content = connection.execute(
            "SELECT identity, resource, redacted_content FROM audit_events "
            "WHERE operation='catalog.create' ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()

    assert persisted is not None
    assert persisted[:3] == ("incident-triage-demo", "1.0.0", "demo-human")
    assert persisted[3] == body["manifest"]
    assert len(persisted[4]) == 64
    assert resource_count == 1
    assert invalid_count == 0
    assert audit_content is not None
    assert "Assess impact" not in json.dumps(audit_content)


@pytest.mark.parametrize("target", ["version", "dependency", "path"])
def test_version_storage_bound_rejects_before_persistence_with_audit(
    client: TestClient,  # noqa: F811 — pytest fixture binding
    target: str,
) -> None:
    version = "1" * 28 + ".0.0"
    body = skill_body()
    body.update(skill_id=f"bounded-{target}", version=version)
    body["manifest"]["dependencies"] = [{"skill_id": "bounded-dependency", "version": version}]
    created = client.post(
        "/v1/skills/versions",
        json=body,
        headers=headers(idempotency_key=f"bounded-{target}-accept"),
    )
    assert created.status_code == 201
    path = f"/v1/skills/bounded-{target}/{version}"
    assert client.get(path, headers=headers()).status_code == 200
    if target == "path":
        rejected = client.get(f"/v1/skills/bounded-{target}/1{version}", headers=headers())
    else:
        body["skill_id"] = f"rejected-{target}"
        if target == "version":
            body["version"] = "1" + version
        else:
            body["manifest"]["dependencies"][0]["version"] = "1" + version
        rejected = client.post(
            "/v1/skills/versions",
            json=body,
            headers=headers(idempotency_key=f"bounded-{target}-reject"),
        )
    assert rejected.status_code == 422, rejected.text
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT count(*) FROM skill_versions WHERE skill_id IN (%s,%s)",
            (f"bounded-{target}", f"rejected-{target}"),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT response_status, reason_code FROM audit_events "
            "WHERE correlation->>'request_id'=%s",
            (rejected.json()["request_id"],),
        ).fetchone() == (422, "contract_validation_failed")


def test_skill_publication_adopts_preexisting_catalog_draft(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    draft_id = "adopted-catalog-skill@1.0.0"
    draft = client.post(
        "/v1/catalog/resources",
        json={
            "resource_type": "skill",
            "resource_id": draft_id,
            "owner_id": "demo-human",
            "source": "skill",
            "source_ref": "catalog-draft",
            "status": "draft",
            "discoverability": {
                "display_name": "Adopted draft",
                "visibility": "private",
                "description": "Pre-existing catalog draft.",
                "tags": [],
            },
        },
        headers=headers(idempotency_key="adopt-catalog-draft"),
    )
    assert draft.status_code == 201, draft.text

    body = skill_body()
    body.update(skill_id="adopted-catalog-skill", version="1.0.0")
    published = client.post(
        "/v1/skills/versions",
        json=body,
        headers=headers(idempotency_key="adopt-catalog-publish"),
    )
    assert published.status_code == 201, published.text
    assert published.json()["resource_id"] == draft_id

    with psycopg.connect(DATABASE_URL) as connection:
        version_row = connection.execute(
            "SELECT owner_id FROM skill_versions WHERE skill_id=%s AND version=%s",
            ("adopted-catalog-skill", "1.0.0"),
        ).fetchone()
        catalog_row = connection.execute(
            "SELECT status, source, source_ref FROM resources "
            "WHERE resource_type='skill' AND resource_id=%s",
            (draft_id,),
        ).fetchone()
        catalog_count = connection.execute(
            "SELECT count(*) FROM resources WHERE resource_type='skill' AND resource_id=%s",
            (draft_id,),
        ).fetchone()[0]

    assert version_row is not None
    assert catalog_count == 1
    assert catalog_row == ("published", "skill", draft_id)


@pytest.mark.parametrize("status", ["active", "inactive", "revoked"])
def test_skill_publication_rejects_adoption_of_lifecycle_states(
    client: TestClient,  # noqa: F811 — pytest fixture binding
    status: str,
) -> None:
    resource_id = f"lifecycle-{status}-skill@1.0.0"
    draft = client.post(
        "/v1/catalog/resources",
        json={
            "resource_type": "skill",
            "resource_id": resource_id,
            "owner_id": "demo-human",
            "source": "skill",
            "source_ref": "catalog-draft",
            "status": status,
            "discoverability": {
                "display_name": "Lifecycle draft",
                "visibility": "private",
                "description": "Pre-existing lifecycle state.",
                "tags": [],
            },
        },
        headers=headers(idempotency_key=f"lifecycle-{status}-draft"),
    )
    assert draft.status_code == 201, draft.text
    body = skill_body()
    body.update(skill_id=f"lifecycle-{status}-skill", version="1.0.0")
    rejected = client.post(
        "/v1/skills/versions",
        json=body,
        headers=headers(idempotency_key=f"lifecycle-{status}-publish"),
    )
    assert rejected.status_code == 409, rejected.text
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT count(*) FROM skill_versions WHERE skill_id=%s",
            (f"lifecycle-{status}-skill",),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT status FROM resources WHERE resource_type='skill' AND resource_id=%s",
            (resource_id,),
        ).fetchone() == (status,)
