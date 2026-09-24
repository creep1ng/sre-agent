"""Issue #23 C2a commands: open/dismiss with CAS and idempotency."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from sre_agent.governance.dto import Principal
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import GrantRepository
from sre_agent.triage.service import TriageError, TriageService

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 23, tzinfo=UTC)
ACTIONS = ("alert.read", "alert.triage", "alert.dismiss")
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
def triage_commands_database() -> None:
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
            "('bystander-human','human','Bystander','active',now(),now())"
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
            for index, action in enumerate(ACTIONS):
                await grants.create(
                    f"grant-op-human-{index}",
                    "op-human",
                    action,
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


@pytest.mark.asyncio
async def test_open_dismiss_replay_conflict_stale() -> None:
    assert SERVICE is not None
    me = _principal("op-human")
    opened = await SERVICE.execute(
        me,
        alert_id="al-flow",
        operation="open_triage",
        expected_version=1,
        idempotency_key="k-flow-open-123456",
    )
    assert (opened.status, opened.expected_version) == ("open", 1)
    dismissed = await SERVICE.execute(
        me,
        alert_id="al-flow",
        operation="triage_dismiss",
        expected_version=1,
        reason=REASON,
        idempotency_key="k-flow-dismiss-123",
    )
    assert (dismissed.status, dismissed.expected_version) == ("dismissed", 2)
    replayed = await SERVICE.execute(
        me,
        alert_id="al-flow",
        operation="triage_dismiss",
        expected_version=1,
        reason=REASON,
        idempotency_key="k-flow-dismiss-123",
    )
    assert replayed.replayed is True and replayed.expected_version == 2
    with pytest.raises(TriageError) as conflict:
        await SERVICE.execute(
            me,
            alert_id="al-flow",
            operation="open_triage",
            expected_version=2,
            idempotency_key="k-flow-dismiss-123",
        )
    assert (conflict.value.http_status, conflict.value.code) == (409, "idempotency_conflict")
    with pytest.raises(TriageError) as stale:
        await SERVICE.execute(
            me,
            alert_id="al-flow",
            operation="triage_dismiss",
            expected_version=1,
            reason=REASON,
            idempotency_key="k-stale-1234567890",
        )
    assert stale.value.http_status == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "code", "status"),
    [
        ({"operation": "triage_dismiss", "expected_version": 1}, "invalid_reason", 422),
        (
            {"operation": "open_triage", "expected_version": 1, "reason": REASON},
            "invalid_reason",
            422,
        ),
        (
            {"operation": "open_triage", "expected_version": 1, "idempotency_key": "x"},
            "invalid_command",
            400,
        ),
    ],
)
async def test_invalid_commands_fail_closed(kwargs: dict, code: str, status: int) -> None:
    assert SERVICE is not None
    base = {"alert_id": "al-invalid", "idempotency_key": "k-invalid-12345678"}
    with pytest.raises(TriageError) as error:
        await SERVICE.execute(_principal("op-human"), **(base | kwargs))
    assert (error.value.code, error.value.http_status) == (code, status)


@pytest.mark.asyncio
async def test_forbidden_leaves_no_trace() -> None:
    assert SERVICE is not None
    with psycopg.connect(DATABASE_URL) as connection:
        before = connection.execute("SELECT count(*) FROM alert_triage").fetchone()[0]
    with pytest.raises(TriageError) as denied:
        await SERVICE.execute(
            _principal("bystander-human"),
            alert_id="al-denied",
            operation="open_triage",
            expected_version=1,
            idempotency_key="k-denied-123456789",
        )
    assert denied.value.http_status == 403
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute("SELECT count(*) FROM alert_triage").fetchone()[0] == before
