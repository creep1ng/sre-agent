import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gateway.health import postgres_readiness_probe
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)


@pytest.fixture(scope="module")
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, skill_versions, grants, credentials, resources, "
            "principals, idempotency_records, mcp_tools, mcp_servers, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


@pytest.mark.usefixtures("migrated_database")
def test_readiness_accepts_database_at_current_migration_head() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert version == "20260926_16"

    client = TestClient(
        create_application(
            Settings(DATABASE_URL), readiness_probe=postgres_readiness_probe(DATABASE_URL)
        )
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "dependency": "postgresql"}


@pytest.mark.usefixtures("migrated_database")
def test_readiness_rejects_previous_database_migration_head() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '20260926_15'")

    try:
        client = TestClient(
            create_application(
                Settings(DATABASE_URL), readiness_probe=postgres_readiness_probe(DATABASE_URL)
            )
        )

        response = client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "dependency": "postgresql"}
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("UPDATE alembic_version SET version_num = '20260926_16'")


def test_liveness_does_not_call_readiness_dependency() -> None:
    calls = 0

    async def readiness_probe() -> None:
        nonlocal calls
        calls += 1

    client = TestClient(
        create_application(Settings("postgresql://unused"), readiness_probe=readiness_probe)
    )

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert calls == 0


def test_readiness_reports_healthy_postgres() -> None:
    async def readiness_probe() -> None:
        return None

    client = TestClient(
        create_application(Settings("postgresql://unused"), readiness_probe=readiness_probe)
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "dependency": "postgresql"}


def test_readiness_sanitizes_postgres_failure() -> None:
    secret_dsn = "postgresql://admin:do-not-leak@db:5432/sre_agent"

    async def readiness_probe() -> None:
        raise RuntimeError(secret_dsn)

    client = TestClient(create_application(Settings(secret_dsn), readiness_probe=readiness_probe))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "dependency": "postgresql"}
    assert secret_dsn not in response.text
