"""Real HTTP/PostgreSQL evidence for exact-version Skill access."""

import asyncio
import json
import os

import psycopg
import pytest
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
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
AUDIT_KEY = "issue331-skill-resolution-audit-key"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": INCIDENT_KEY,
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, skill_versions, grants, credentials, resources, "
            "mcp_tools, mcp_servers, principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
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


@pytest.fixture
def client() -> TestClient:
    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def publish(
    client: TestClient,
    skill_id: str,
    instructions: str,
    dependencies: list[dict[str, str]] | None = None,
) -> None:
    response = client.post(
        "/v1/skills/versions",
        json={
            "skill_id": skill_id,
            "version": "1.0.0",
            "owner_id": "demo-human",
            "manifest": {
                "display_name": "Resolution test Skill",
                "description": "A controlled exact-version resolution fixture.",
                "instructions": instructions,
                "dependencies": dependencies or [],
            },
        },
        headers={**headers(ADMIN_KEY), "Idempotency-Key": f"publish-{skill_id}-331"},
    )
    assert response.status_code == 201


def grant_invoke(skill_id: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO grants "
            "(grant_id, principal_id, action, resource_type, resource_id, effect, status, "
            "created_at) VALUES (%s, 'incident-harness', 'invoke', 'skill', %s, 'allow', "
            "'active', now())",
            (f"grant-resolution-{skill_id}", f"{skill_id}@1.0.0"),
        )


def activate(client: TestClient, skill_id: str, status: str) -> None:
    del client
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE resources SET status=%s WHERE resource_type='skill' AND resource_id=%s",
            (status, f"{skill_id}@1.0.0"),
        )


def test_exact_version_read_authorizes_before_content_and_audits_metadata_only(
    client: TestClient,
) -> None:
    private_instructions = "PRIVATE_SKILL_INSTRUCTIONS_RESOLUTION_331"
    publish(client, "authorized-root-skill", private_instructions)
    publish(client, "inactive-root-skill", "PRIVATE_INACTIVE_SKILL_INSTRUCTIONS_331")
    publish(client, "ungranted-dependency", "PRIVATE_DEPENDENCY_INSTRUCTIONS_331")
    publish(
        client,
        "dependency-bearing-root",
        "PRIVATE_DEPENDENCY_ROOT_INSTRUCTIONS_331",
        dependencies=[{"skill_id": "ungranted-dependency", "version": "1.0.0"}],
    )
    activate(client, "authorized-root-skill", "active")
    grant_invoke("authorized-root-skill")
    activate(client, "inactive-root-skill", "inactive")
    activate(client, "ungranted-dependency", "active")
    activate(client, "dependency-bearing-root", "active")
    grant_invoke("dependency-bearing-root")
    grant_invoke("inactive-root-skill")

    exact = client.get(
        "/v1/skills/authorized-root-skill/1.0.0/resolve", headers=headers(INCIDENT_KEY)
    )
    unauthorized = client.get(
        "/v1/skills/authorized-root-skill/1.0.0/resolve", headers=headers(RESTRICTED_KEY)
    )
    absent = client.get("/v1/skills/absent-root-skill/1.0.0/resolve", headers=headers(INCIDENT_KEY))
    dependency_bearing = client.get(
        "/v1/skills/dependency-bearing-root/1.0.0/resolve", headers=headers(INCIDENT_KEY)
    )
    inactive = client.get(
        "/v1/skills/inactive-root-skill/1.0.0/resolve", headers=headers(INCIDENT_KEY)
    )

    assert exact.status_code == 200, exact.text
    assert exact.json()["skill"]["skill_id"] == "authorized-root-skill"
    assert exact.json()["skill"]["version"] == "1.0.0"
    assert exact.json()["skill"]["manifest"]["instructions"] == private_instructions

    expected_error = dict(
        code="resource_not_found", message="The requested resource was not found."
    )
    for denied in (unauthorized, absent, inactive, dependency_bearing):
        assert denied.status_code == 404 and denied.json()["error"] == expected_error
    dependency_body = json.dumps(dependency_bearing.json())
    assert "PRIVATE_DEPENDENCY_ROOT_INSTRUCTIONS_331" not in dependency_body
    assert "PRIVATE_DEPENDENCY_INSTRUCTIONS_331" not in dependency_body
    assert "ungranted-dependency" not in dependency_body

    responses = (exact, unauthorized, absent, inactive, dependency_bearing)
    request_ids = {response.json()["request_id"] for response in responses}
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT operation, action, correlation, identity, resource, content_state, "
            "redacted_content, response_status, outcome, reason_code "
            "FROM audit_events WHERE correlation->>'request_id' = ANY(%s)",
            (list(request_ids),),
        ).fetchall()
    audit_json = json.dumps(rows, default=str)
    assert len(rows) == len(request_ids) == len({row[2]["request_id"] for row in rows})
    assert all(
        row[0:2] == ("skills.resolve", "invoke") and row[5:7] == ("absent", None) for row in rows
    )
    assert all(row[3] is not None and row[4] is not None for row in rows)
    dependency_audit = next(
        row for row in rows if row[2]["request_id"] == dependency_bearing.json()["request_id"]
    )
    assert dependency_audit[7:] == (404, "error", "resource_not_found")
    assert all(
        instruction not in audit_json
        for instruction in (
            private_instructions,
            "PRIVATE_INACTIVE_SKILL_INSTRUCTIONS_331",
            "PRIVATE_DEPENDENCY_ROOT_INSTRUCTIONS_331",
            "PRIVATE_DEPENDENCY_INSTRUCTIONS_331",
        )
    )
