"""Real HTTP/PostgreSQL evidence for pinned Skill resume and grant revocation."""

import json

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_control_acceptance import ADMIN_KEY, DATABASE_URL, SEED_ENV, headers
from test_control_acceptance import client as _client_fixture  # noqa: F401
from test_control_acceptance import migrated_acceptance_database as _database_fixture  # noqa: F401

SKILL_ID = "lifecycle-proof-skill"
PRINCIPAL_ID = "incident-harness"
INCIDENT_KEY = SEED_ENV["INCIDENT_HARNESS_API_KEY"]


@pytest.fixture
def client(request: pytest.FixtureRequest) -> TestClient:
    return request.getfixturevalue("_client_fixture")


def publish(client: TestClient, version: str, instructions: str) -> None:
    response = client.post(
        "/v1/skills/versions",
        json={
            "skill_id": SKILL_ID,
            "version": version,
            "owner_id": "demo-human",
            "manifest": {
                "display_name": "Pinned lifecycle proof",
                "description": "Exact-version resume and grant-revocation behavior.",
                "instructions": instructions,
                "dependencies": [],
            },
        },
        headers={
            **headers(ADMIN_KEY),
            "Idempotency-Key": f"publish-lifecycle-proof-{version}",
        },
    )
    assert response.status_code == 201, response.text


def set_status(client: TestClient, version: str, status: str):
    with psycopg.connect(DATABASE_URL) as connection:
        updated_at = connection.execute(
            "SELECT updated_at FROM resources WHERE resource_type='skill' AND resource_id=%s",
            (f"{SKILL_ID}@{version}",),
        ).fetchone()[0]
    return client.put(
        f"/v1/skills/{SKILL_ID}/{version}/status",
        json={"status": status, "expected_updated_at": updated_at.isoformat()},
        headers=headers(ADMIN_KEY),
    )


def grant_invoke(*versions: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        for version in versions:
            connection.execute(
                "INSERT INTO grants "
                "(grant_id, principal_id, action, resource_type, resource_id, effect, status, "
                "created_at) VALUES (%s, %s, 'invoke', 'skill', %s, 'allow', 'active', now())",
                (
                    f"grant-{PRINCIPAL_ID}-{version.replace('.', '-')}",
                    PRINCIPAL_ID,
                    f"{SKILL_ID}@{version}",
                ),
            )


def grant_revocation_admin() -> None:
    """Give the catalog admin the separate existing grant-management authority."""
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active')"
        )
        connection.execute(
            "INSERT INTO grants "
            "(grant_id, principal_id, action, resource_type, resource_id, effect, status, "
            "created_at) VALUES "
            "('grant-lifecycle-proof-admin', 'admin-human', 'admin.write', "
            "'administrative_control', 'grants', 'allow', 'active', now())"
        )


def test_pinned_resume_and_grant_revocation_are_effective_without_content_cache(
    client: TestClient,
) -> None:
    old_marker = "OLD_PINNED_LIFECYCLE_PROOF_PRIVATE_331"
    new_marker = "NEW_PINNED_LIFECYCLE_PROOF_PRIVATE_331"
    publish(client, "1.0.0", old_marker)
    publish(client, "2.0.0", new_marker)

    assert set_status(client, "1.0.0", "active").status_code == 200
    assert set_status(client, "2.0.0", "active").status_code == 200
    grant_invoke("1.0.0", "2.0.0")
    old_url = f"/v1/skills/{SKILL_ID}/1.0.0/resolve"
    new_url = f"/v1/skills/{SKILL_ID}/2.0.0/resolve"

    old_before = client.get(old_url, headers=headers(INCIDENT_KEY))
    new_active = client.get(new_url, headers=headers(INCIDENT_KEY))
    old_resume = client.get(old_url, headers=headers(INCIDENT_KEY))
    assert old_before.status_code == new_active.status_code == old_resume.status_code == 200
    assert old_before.json()["skill"]["version"] == old_resume.json()["skill"]["version"] == "1.0.0"
    assert old_resume.json()["skill"]["manifest"]["instructions"] == old_marker
    assert new_active.json()["skill"]["manifest"]["instructions"] == new_marker

    deactivated = set_status(client, "1.0.0", "inactive")
    after_deactivation = client.get(old_url, headers=headers(INCIDENT_KEY))
    reactivated = set_status(client, "1.0.0", "active")
    after_reactivation = client.get(old_url, headers=headers(INCIDENT_KEY))
    assert deactivated.status_code == reactivated.status_code == 200
    assert after_deactivation.status_code == 404
    assert after_deactivation.json()["error"]["code"] == "resource_not_found"
    assert after_reactivation.status_code == 200
    assert after_reactivation.json()["skill"]["version"] == "1.0.0"
    assert after_reactivation.json()["skill"]["manifest"]["instructions"] == old_marker

    grant_revocation_admin()
    revoked = client.delete("/v1/grants/grant-incident-harness-1-0-0", headers=headers(ADMIN_KEY))
    after_revocation = client.get(old_url, headers=headers(INCIDENT_KEY))
    newer_version_still_allowed = client.get(new_url, headers=headers(INCIDENT_KEY))
    assert revoked.status_code == 204
    assert after_revocation.status_code == 404
    assert after_revocation.json()["error"]["code"] == "resource_not_found"
    assert newer_version_still_allowed.status_code == 200
    assert newer_version_still_allowed.json()["skill"]["version"] == "2.0.0"

    resolutions = (
        old_before,
        new_active,
        old_resume,
        after_deactivation,
        after_reactivation,
        after_revocation,
        newer_version_still_allowed,
    )
    request_ids = {response.json()["request_id"] for response in resolutions}
    with psycopg.connect(DATABASE_URL) as connection:
        events = connection.execute(
            "SELECT operation, action, correlation, identity, resource, content_state, "
            "redacted_content FROM audit_events "
            "WHERE correlation->>'request_id' = ANY(%s)",
            (list(request_ids),),
        ).fetchall()

    audit_document = json.dumps(events, default=str)
    assert len(events) == len(request_ids) == len({row[2]["request_id"] for row in events})
    assert all(row[0:2] == ("skills.resolve", "invoke") for row in events)
    assert all(row[2]["request_id"] in request_ids for row in events)
    assert all(row[3] is not None and row[4] is not None for row in events)
    assert all(row[5:] == ("absent", None) for row in events)
    assert old_marker not in audit_document
    assert new_marker not in audit_document
