"""Real HTTP and PostgreSQL evidence for exact-version Skill lifecycle."""

import asyncio
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
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
AUDIT_KEY = "issue331-skill-activation-audit-key"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": "sre_inci_0123456789abcdefghijklmnop",
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


def test_skill_activation_is_exact_authorized_persisted_and_idempotent(
    client: TestClient,
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
