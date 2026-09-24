"""Issue #23 C2a link: eligibility revalidated inside the operation."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sre_agent.governance.dto import Principal
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import GrantRepository
from sre_agent.triage.service import TriageError, TriageService

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 23, tzinfo=UTC)
REASON = "Sustained 5xx spike on checkout."
SERVICE: TriageService | None = None


def _principal(pid: str) -> Principal:
    return Principal(
        principal_id=pid,
        kind="human",
        display_name=pid,
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(scope="module", autouse=True)
def triage_link_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
        for (table,) in tables:
            connection.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('op-human','human','Operator','active',now(),now()),"
            "('linker-human','human','Linker','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at,"
            " owner_id, source, source_ref, display_name, visibility, description,"
            " tags) VALUES ('incident_workflow','incident-response','active',now(),"
            " 'papiarcacamilo','incident_workflow','incident-response@1.0.0',"
            " 'Incident response workflow','private','','[]')"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> TriageService:
        async with database.transaction() as session:
            grants = GrantRepository(session)
            actions = (
                "alert.read",
                "alert.triage",
                "alert.associate",
                "run.read",
            )
            for index, action in enumerate(actions):
                await grants.create(
                    f"grant-op-human-{index}",
                    "op-human",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
            await grants.create(
                "grant-linker-associate",
                "linker-human",
                "alert.associate",
                "incident_workflow",
                "incident-response",
            )
        workflow = load_incident_workflow(
            Path(__file__).parents[1] / "agent" / "workflows" / "incident-response.yaml"
        )
        return TriageService(database, workflow)

    global SERVICE
    SERVICE = asyncio.run(_setup())
    asyncio.run(database.dispose())


async def _add_incident(incident_id: str, state: str) -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            await session.execute(
                text(
                    "INSERT INTO incident.incidents (incident_id, state, version,"
                    " created_at, updated_at) VALUES (:id,"
                    " jsonb_build_object('state', CAST(:state AS text)), 1,"
                    " now(), now())"
                ),
                {"id": incident_id, "state": state},
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_link_and_destination_eligibility() -> None:
    assert SERVICE is not None
    me = _principal("op-human")
    await _add_incident("inc-eligible", "active")
    await _add_incident("inc-shut", "resolved")
    await SERVICE.execute(
        me,
        alert_id="al-link",
        operation="open_triage",
        expected_version=1,
        idempotency_key="k-link-open-1234567",
    )
    linked = await SERVICE.execute(
        me,
        alert_id="al-link",
        operation="triage_link",
        expected_version=1,
        reason=REASON,
        target_incident_id="inc-eligible",
        idempotency_key="k-link-12345678901",
    )
    assert (linked.status, linked.incident_id, linked.http_status) == (
        "linked",
        "inc-eligible",
        200,
    )
    await SERVICE.execute(
        me,
        alert_id="al-badlink",
        operation="open_triage",
        expected_version=1,
        idempotency_key="k-badlink-open-1234",
    )
    with pytest.raises(TriageError) as ineligible:
        await SERVICE.execute(
            me,
            alert_id="al-badlink",
            operation="triage_link",
            expected_version=1,
            reason=REASON,
            target_incident_id="inc-shut",
            idempotency_key="k-badlink-123456789",
        )
    assert ineligible.value.code == "destination_ineligible"
    with pytest.raises(TriageError) as missing:
        await SERVICE.execute(
            me,
            alert_id="al-badlink",
            operation="triage_link",
            expected_version=1,
            reason=REASON,
            target_incident_id="inc-no-such-thing",
            idempotency_key="k-missing-123456789",
        )
    assert (missing.value.http_status, missing.value.code) == (404, "incident_not_found")
    with pytest.raises(TriageError) as no_run_read:
        await SERVICE.execute(
            _principal("linker-human"),
            alert_id="al-linker",
            operation="triage_link",
            expected_version=1,
            reason=REASON,
            target_incident_id="inc-eligible",
            idempotency_key="k-linker-1234567890",
        )
    assert no_run_read.value.http_status == 403
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            await session.execute(
                text(
                    "UPDATE incident.incidents SET state = jsonb_build_object("
                    "'state', 'resolved') WHERE incident_id='inc-eligible'"
                )
            )
    finally:
        await database.dispose()
    with pytest.raises(TriageError) as raced:
        await SERVICE.execute(
            me,
            alert_id="al-link",
            operation="triage_link",
            expected_version=2,
            reason=REASON,
            target_incident_id="inc-eligible",
            idempotency_key="k-raced-12345678901",
        )
    assert raced.value.code == "destination_ineligible"


@pytest.mark.asyncio
async def test_link_rejects_bad_target_and_declare_waits() -> None:
    assert SERVICE is not None
    with pytest.raises(TriageError) as bad_target:
        await SERVICE.execute(
            _principal("op-human"),
            alert_id="al-target",
            operation="triage_link",
            expected_version=1,
            reason=REASON,
            target_incident_id="BAD ID!",
            idempotency_key="k-badtarget-1234567",
        )
    assert bad_target.value.code == "invalid_target"
    with pytest.raises(TriageError) as waiting:
        await SERVICE.execute(
            _principal("op-human"),
            alert_id="al-wait",
            operation="triage_declare",
            expected_version=1,
            reason=REASON,
            severity="sev2",
            idempotency_key="k-wait-12345678901",
        )
    assert waiting.value.code == "operation_not_supported"
