"""Issue #189 A2: run.read provisioning through the governed API."""

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationDenialCause,
)
from sre_agent.governance.dto import Principal
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import (
    CredentialRepository,
    GrantRepository,
    ResourceRepository,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from provision_incident_workflow import (  # noqa: E402
    _run,
    build_service,
    provision,
    revoke_run_read,
)

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 22, tzinfo=UTC)
SUBJECT = Principal(
    principal_id="demo-human",
    kind="human",
    display_name="Demo",
    status="active",
    created_at=NOW,
    updated_at=NOW,
)
BEARER: list[str] = []


@pytest.fixture(scope="module", autouse=True)
def provisioned_database() -> None:
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
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('admin-human','human','Admin','active',now(),now()),"
            "('demo-human','human','Demo','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at) VALUES "
            "('administrative_control','catalog','active',now()),"
            "('administrative_control','grants','active',now())"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> str:
        async with database.transaction() as session:
            issued = await CredentialRepository(session).issue("admin-human")
            grants = GrantRepository(session)
            for resource in ("catalog", "grants"):
                await grants.create(
                    f"grant-admin-human-admin-write-{resource}",
                    "admin-human",
                    "admin.write",
                    "administrative_control",
                    resource,
                )
        return f"Bearer {issued.key}"

    BEARER.append(asyncio.run(_setup()))
    asyncio.run(database.dispose())


async def _decision() -> str:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            engine = AuthorizationDecisionEngine(
                ResourceRepository(session), GrantRepository(session)
            )
            evaluation = await engine.evaluate(
                SUBJECT, "run.read", "incident_workflow", "incident-response"
            )
            if evaluation.decision.decision == "allow":
                return "allow"
            return f"deny:{evaluation.denial_cause}"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_governed_provision_opens_and_revoke_closes(monkeypatch, capsys) -> None:
    assert await _decision() == f"deny:{AuthorizationDenialCause.RESOURCE_MISSING}"
    database = Database(DATABASE_URL)
    try:
        service = build_service(database, b"0" * 32)
        result = await provision(service, BEARER[0])
        assert (result.catalog_status, result.grant_status, result.run_read_active) == (
            201,
            201,
            True,
        )
        assert await _decision() == "allow"
        replayed = await provision(service, BEARER[0])
        assert (replayed.catalog_status, replayed.grant_status, replayed.run_read_active) == (
            201,
            201,
            True,
        )
        assert await revoke_run_read(service, BEARER[0]) == 204
        revoked_replay = await provision(service, BEARER[0])
        assert (revoked_replay.catalog_status, revoked_replay.grant_status) == (201, 201)
        assert revoked_replay.run_read_active is False
    finally:
        await database.dispose()
    assert await _decision() == f"deny:{AuthorizationDenialCause.GRANT_NOT_APPLICABLE}"

    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("ADMIN_API_KEY", BEARER[0].removeprefix("Bearer "))
    monkeypatch.setenv("AUDIT_KEY_HEX", "00" * 32)
    assert await _run(revoke=False) == 1
    assert '"run_read_active": false' in capsys.readouterr().out
