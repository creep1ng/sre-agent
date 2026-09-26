"""Real HTTP and PostgreSQL evidence for immutable Skill publication."""

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
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
AUDIT_KEY = "issue331-skill-publication-audit-key"
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


def headers(key: str = ADMIN_KEY, idempotency_key: str = "publish-skill-331-key") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Idempotency-Key": idempotency_key,
    }


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


def test_skill_publication_is_closed_idempotent_and_persisted(client: TestClient) -> None:
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
