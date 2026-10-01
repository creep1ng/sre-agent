"""Real HTTP/PostgreSQL demonstration of governed incident Skills."""

import asyncio
import json
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
INCIDENT_KEY = "sre_inci_0123456789abcdefghijklmnop"
AUDIT_KEY = "issue331-demo-audit-key"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": INCIDENT_KEY,
    "RESTRICTED_HARNESS_API_KEY": "sre_rest_0123456789abcdefghijklmnop",
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}


def admin_headers(idempotency_key: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {ADMIN_KEY}"}
    if idempotency_key:
        result["Idempotency-Key"] = idempotency_key
    return result


def test_example_skills_publish_activate_and_resolve_with_direct_authority() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, bok_section_chunks, bok_documents, "
            "bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, resources, "
            "mcp_tools, mcp_servers, principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
        connection.execute("DROP FUNCTION IF EXISTS reject_skill_version_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            assert await seed(database, SeedSettings.from_environment(SEED_ENV))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status) "
            "VALUES ('administrative_control', 'grants', 'active')"
        )
        connection.execute(
            "INSERT INTO grants (grant_id, principal_id, action, resource_type, resource_id, "
            "effect, status, created_at) VALUES ('grant-demo-admin-grants', 'admin-human', "
            "'admin.write', 'administrative_control', 'grants', 'allow', 'active', now())"
        )

    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(app, raise_server_exceptions=False) as client:
        triage = json.loads(Path("demo/skills/incident-triage/1.0.0.json").read_text())
        postmortem = json.loads(Path("demo/skills/postmortem-writer/1.0.0.json").read_text())
        publications = (
            (triage, "demo-publish-triage"),
            (postmortem, "demo-publish-postmortem"),
        )
        for skill, idem in publications:
            response = client.post(
                "/v1/skills/versions",
                json=skill,
                headers=admin_headers(f"issue331-{idem}"),
            )
            assert response.status_code == 201

        def set_status(skill: dict[str, object], status: str) -> None:
            current = client.get(
                f"/v1/skills/{skill['skill_id']}/{skill['version']}",
                headers=admin_headers(),
            )
            assert current.status_code == 200, current.text
            response = client.put(
                f"/v1/skills/{skill['skill_id']}/{skill['version']}/status",
                json={"status": status, "expected_updated_at": current.json()["created_at"]},
                headers=admin_headers(),
            )
            assert response.status_code == 200, response.text

        set_status(triage, "active")
        set_status(postmortem, "active")
        triage_id = f"{triage['skill_id']}@{triage['version']}"
        postmortem_id = f"{postmortem['skill_id']}@{postmortem['version']}"

        def grant(skill_id: str, key: str) -> None:
            response = client.post(
                "/v1/grants",
                json={
                    "grant_id": f"grant-demo-{key}",
                    "principal_id": "incident-harness",
                    "action": "invoke",
                    "resource": {"resource_type": "skill", "resource_id": skill_id},
                    "effect": "allow",
                },
                headers=admin_headers(f"issue331-demo-grant-{key}"),
            )
            assert response.status_code == 201

        grant(postmortem_id, "postmortem")
        gateway_headers = {"Authorization": f"Bearer {INCIDENT_KEY}"}
        postmortem_url = f"/v1/skills/{postmortem['skill_id']}/{postmortem['version']}/resolve"
        denied = client.get(postmortem_url, headers=gateway_headers)
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "resource_not_found"
        assert postmortem["manifest"]["instructions"] not in denied.text

        grant(triage_id, "triage")
        triage_response = client.get(
            f"/v1/skills/{triage['skill_id']}/{triage['version']}/resolve",
            headers=gateway_headers,
        )
        postmortem_response = client.get(postmortem_url, headers=gateway_headers)

    assert triage_response.status_code == postmortem_response.status_code == 200
    assert triage_response.json()["skill"]["manifest"] == triage["manifest"]
    assert postmortem_response.json()["skill"]["manifest"] == postmortem["manifest"]
    assert postmortem_response.json()["dependencies"][0]["manifest"] == triage["manifest"]
    with psycopg.connect(DATABASE_URL) as connection:
        persisted = connection.execute(
            "SELECT skill_id, version, owner_id, manifest, content_sha256 FROM skill_versions "
            "ORDER BY skill_id"
        ).fetchall()
        grants = connection.execute(
            "SELECT resource_id FROM grants WHERE principal_id='incident-harness' "
            "AND action='invoke' AND resource_type='skill' ORDER BY resource_id"
        ).fetchall()
        events = connection.execute(
            "SELECT correlation, resource, content_state, redacted_content FROM audit_events "
            "WHERE operation='skills.resolve' ORDER BY occurred_at, event_id"
        ).fetchall()
    assert [(row[0], row[1], row[2], row[3]) for row in persisted] == [
        (triage["skill_id"], triage["version"], triage["owner_id"], triage["manifest"]),
        (
            postmortem["skill_id"],
            postmortem["version"],
            postmortem["owner_id"],
            postmortem["manifest"],
        ),
    ]
    assert all(len(row[4]) == 64 for row in persisted)
    assert grants == [(triage_id,), (postmortem_id,)]
    assert len(events) == 3 and all(row[0]["request_id"] for row in events)
    response_ids = {
        denied.json()["request_id"],
        triage_response.json()["request_id"],
        postmortem_response.json()["request_id"],
    }
    assert {row[0]["request_id"] for row in events} == response_ids
    audit_json = json.dumps(events, default=str)
    for skill in (triage, postmortem):
        assert skill["manifest"]["instructions"] not in audit_json
