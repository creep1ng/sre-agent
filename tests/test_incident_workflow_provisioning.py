"""Governed provisioning of the incident workflow run grants (issues #189 and #330)."""

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
HARNESS = Principal(
    principal_id="incident-harness",
    kind="agent",
    display_name="Incident harness",
    status="active",
    created_at=NOW,
    updated_at=NOW,
)


@pytest.fixture(autouse=True)
def admin_bearer() -> str:
    """Start every case from an empty store holding only the administrative prerequisites.

    No case may depend on what another one left behind: each provisions the state
    it asserts through the governed path itself, so a case selected alone, or run
    in any order, sees exactly the state it declares.
    """

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS request_attributions, consumption_limit_policies, "
            "bok_section_chunks, bok_documents, "
            "bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, "
            "resources, alert_triage, mcp_tools, mcp_servers, "
            "principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('admin-human','human','Admin','active',now(),now()),"
            "('demo-human','human','Demo','active',now(),now()),"
            "('incident-harness','agent','Incident harness','active',now(),now())"
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

    bearer = asyncio.run(_setup())
    asyncio.run(database.dispose())
    return bearer


async def _provision_then_revoke_run_read(bearer: str) -> None:
    """Reach the state the grant cases assert on, through the governed API only."""

    database = Database(DATABASE_URL)
    try:
        service = build_service(database, b"0" * 32)
        result = await provision(service, bearer)
        assert (
            result.run_read_active,
            result.run_start_active,
            result.run_command_active,
            result.run_approve_active,
        ) == (True, True, True, True)
        assert await revoke_run_read(service, bearer) == 204
    finally:
        await database.dispose()


async def _decision(action: str = "run.read", subject: Principal = SUBJECT) -> str:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            engine = AuthorizationDecisionEngine(
                ResourceRepository(session), GrantRepository(session)
            )
            evaluation = await engine.evaluate(
                subject, action, "incident_workflow", "incident-response"
            )
            if evaluation.decision.decision == "allow":
                return "allow"
            return f"deny:{evaluation.denial_cause}"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_governed_provision_opens_and_revoke_closes(
    monkeypatch, capsys, admin_bearer: str
) -> None:
    assert await _decision() == f"deny:{AuthorizationDenialCause.RESOURCE_MISSING}"
    database = Database(DATABASE_URL)
    try:
        service = build_service(database, b"0" * 32)
        result = await provision(service, admin_bearer)
        assert (result.catalog_status, result.grant_status, result.run_read_active) == (
            201,
            201,
            True,
        )
        assert await _decision() == "allow"
        replayed = await provision(service, admin_bearer)
        assert (replayed.catalog_status, replayed.grant_status, replayed.run_read_active) == (
            201,
            201,
            True,
        )
        assert await revoke_run_read(service, admin_bearer) == 204
        revoked_replay = await provision(service, admin_bearer)
        assert (revoked_replay.catalog_status, revoked_replay.grant_status) == (201, 201)
        assert revoked_replay.run_read_active is False
    finally:
        await database.dispose()
    assert await _decision() == f"deny:{AuthorizationDenialCause.GRANT_NOT_APPLICABLE}"

    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("ADMIN_API_KEY", admin_bearer.removeprefix("Bearer "))
    monkeypatch.setenv("AUDIT_KEY_HEX", "00" * 32)
    assert await _run(revoke=False) == 1
    assert '"run_read_active": false' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_start_is_granted_and_revoked_apart_from_run_read(admin_bearer: str) -> None:
    """Least privilege only means something if the two grants move separately.

    The case provisions both grants and revokes the reader through the governed
    path itself, so starting runs must still be allowed afterwards: revoking the
    reader cannot take the starter with it, and neither can be inferred from the
    other.
    """

    await _provision_then_revoke_run_read(admin_bearer)
    assert await _decision("run.read") == f"deny:{AuthorizationDenialCause.GRANT_NOT_APPLICABLE}"
    assert await _decision("run.start") == "allow"
    assert (
        await _decision("run.start", HARNESS)
        == f"deny:{AuthorizationDenialCause.GRANT_NOT_APPLICABLE}"
    )


@pytest.mark.asyncio
async def test_the_harness_can_never_approve_what_it_proposed(admin_bearer: str) -> None:
    """The operator sends commands and approves; the agent does neither.

    Provisioning both actions for one principal is not the risk; provisioning
    either of them for the harness is. An agent that could approve its own
    mitigation would make the human gate decorative, so the decision is asserted
    for the harness too, on the state this case provisions through the governed
    path itself.
    """

    await _provision_then_revoke_run_read(admin_bearer)
    assert await _decision("run.command") == "allow"
    assert await _decision("run.approve") == "allow"
    assert (
        await _decision("run.command", HARNESS)
        == f"deny:{AuthorizationDenialCause.GRANT_NOT_APPLICABLE}"
    )
    assert (
        await _decision("run.approve", HARNESS)
        == f"deny:{AuthorizationDenialCause.GRANT_NOT_APPLICABLE}"
    )
    assert await _decision("run.read") == f"deny:{AuthorizationDenialCause.GRANT_NOT_APPLICABLE}"
