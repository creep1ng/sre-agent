"""Issue #23 C2a link: eligibility revalidated inside the operation."""

import asyncio
import os
import time
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


def _install_link_gate(connection: psycopg.Connection) -> None:
    """Pause a real link after eligibility was checked, inside its DB write."""
    connection.execute(
        """
        CREATE OR REPLACE FUNCTION triage_test_link_gate() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.status = 'linked' THEN
            PERFORM pg_advisory_xact_lock(hashtext(NEW.alert_id));
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    connection.execute("DROP TRIGGER IF EXISTS triage_test_link_gate ON alert_triage")
    connection.execute(
        """CREATE TRIGGER triage_test_link_gate BEFORE UPDATE ON alert_triage
           FOR EACH ROW EXECUTE FUNCTION triage_test_link_gate()"""
    )
    connection.commit()


def _wait_for_lock_wait(query_fragments: tuple[str, ...], timeout: float = 5) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                """SELECT query FROM pg_stat_activity
                   WHERE datname=current_database() AND state='active'
                     AND wait_event_type='Lock' AND query LIKE ANY(%s)
                   LIMIT 1""",
                ([f"%{fragment}%" for fragment in query_fragments],),
            ).fetchone()
        if row is not None:
            return row[0]
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for PostgreSQL lock on {query_fragments!r}")


def _close_incident(incident_id: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE incident.incidents SET state=jsonb_build_object('state','closed') "
            "WHERE incident_id=%s",
            (incident_id,),
        )


def _remove_link_gate(connection: psycopg.Connection, alert_id: str) -> None:
    connection.execute("DROP TRIGGER IF EXISTS triage_test_link_gate ON alert_triage")
    connection.execute("DROP FUNCTION IF EXISTS triage_test_link_gate()")
    connection.execute("SELECT pg_advisory_unlock(hashtext(%s))", (alert_id,))
    connection.commit()


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
    await _add_incident("inc-closed", "closed")
    await SERVICE.execute(
        me,
        alert_id="al-already-closed",
        operation="open_triage",
        expected_version=1,
        idempotency_key="k-already-closed-open-1",
    )
    with pytest.raises(TriageError) as already_closed:
        await SERVICE.execute(
            me,
            alert_id="al-already-closed",
            operation="triage_link",
            expected_version=1,
            reason=REASON,
            target_incident_id="inc-closed",
            idempotency_key="k-already-closed-link-1",
        )
    assert (already_closed.value.http_status, already_closed.value.code) == (
        409,
        "destination_ineligible",
    )
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
async def test_link_rejects_malformed_target_and_severity() -> None:
    assert SERVICE is not None
    me = _principal("op-human")
    good = {
        "alert_id": "al-shape",
        "operation": "triage_link",
        "expected_version": 1,
        "reason": REASON,
        "target_incident_id": "inc-eligible",
    }
    bad = [
        ({"target_incident_id": ["inc-eligible"]}, "invalid_target", 422),
        ({"target_incident_id": None}, "invalid_target", 422),
        ({"severity": ["sev2"]}, "invalid_severity", 422),
        ({"severity": "bogus"}, "invalid_severity", 422),
        ({"reason": ""}, "invalid_reason", 422),
    ]
    for override, code, status in bad:
        with pytest.raises(TriageError) as error:
            key = f"k-shape-{code}-{status}-12345"
            await SERVICE.execute(me, **(good | override | {"idempotency_key": key}))
        assert (error.value.code, error.value.http_status) == (code, status)


@pytest.mark.asyncio
async def test_link_rejects_bad_target() -> None:
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


@pytest.mark.asyncio
async def test_close_wins_before_link_rejects_after_waiting_for_target_row() -> None:
    """A close committed while link waits must be visible to eligibility."""
    assert SERVICE is not None
    await _add_incident("inc-close-wins", "active")
    await SERVICE.execute(
        _principal("op-human"),
        alert_id="al-close-wins",
        operation="open_triage",
        expected_version=1,
        idempotency_key="k-close-wins-open-1234",
    )
    gate = psycopg.connect(DATABASE_URL, autocommit=True)
    gate.execute("SELECT pg_advisory_lock(hashtext(%s))", ("al-close-wins",))
    _install_link_gate(gate)
    closer = psycopg.connect(DATABASE_URL)
    closer.execute(
        "UPDATE incident.incidents SET state=jsonb_build_object('state','closed') "
        "WHERE incident_id='inc-close-wins'"
    )
    linker = asyncio.create_task(
        SERVICE.execute(
            _principal("op-human"),
            alert_id="al-close-wins",
            operation="triage_link",
            expected_version=1,
            reason=REASON,
            target_incident_id="inc-close-wins",
            idempotency_key="k-close-wins-link-1234",
        )
    )
    try:
        # Plain MVCC SELECT doesn't wait for the uncommitted closer; it reaches
        # the trigger and allows the close to commit before the link write.
        await asyncio.to_thread(_wait_for_lock_wait, ("incident.incidents", "UPDATE alert_triage"))
        closer.commit()
        gate.execute("SELECT pg_advisory_unlock(hashtext(%s))", ("al-close-wins",))
        with pytest.raises(TriageError) as error:
            await asyncio.wait_for(linker, timeout=5)
        assert (error.value.http_status, error.value.code) == (409, "destination_ineligible")
    finally:
        if not linker.done():
            gate.execute("SELECT pg_advisory_unlock(hashtext(%s))", ("al-close-wins",))
        # Roll back the paused close before joining the linker or dropping the
        # trigger; otherwise cleanup DDL can wait on its row lock indefinitely.
        closer.close()
        if not linker.done():
            linker.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(linker, return_exceptions=True), timeout=5)
        finally:
            _remove_link_gate(gate, "al-close-wins")
            gate.close()


@pytest.mark.asyncio
async def test_link_wins_before_close_serializes_eligibility_and_link() -> None:
    """Once link locks an eligible target, concurrent close follows it."""
    assert SERVICE is not None
    await _add_incident("inc-link-wins", "active")
    await SERVICE.execute(
        _principal("op-human"),
        alert_id="al-link-wins",
        operation="open_triage",
        expected_version=1,
        idempotency_key="k-link-wins-open-1234",
    )
    gate = psycopg.connect(DATABASE_URL, autocommit=True)
    gate.execute("SELECT pg_advisory_lock(hashtext(%s))", ("al-link-wins",))
    _install_link_gate(gate)
    linker = asyncio.create_task(
        SERVICE.execute(
            _principal("op-human"),
            alert_id="al-link-wins",
            operation="triage_link",
            expected_version=1,
            reason=REASON,
            target_incident_id="inc-link-wins",
            idempotency_key="k-link-wins-link-1234",
        )
    )
    closer = None
    try:
        await asyncio.to_thread(_wait_for_lock_wait, ("UPDATE alert_triage",))
        closer = asyncio.create_task(asyncio.to_thread(_close_incident, "inc-link-wins"))
        # The close is performed on another connection. It must block on the
        # row lock held by SELECT FOR UPDATE until the link transaction commits.
        await asyncio.to_thread(_wait_for_lock_wait, ("UPDATE incident.incidents",))
        gate.execute("SELECT pg_advisory_unlock(hashtext(%s))", ("al-link-wins",))
        linked = await asyncio.wait_for(linker, timeout=5)
        await asyncio.wait_for(closer, timeout=5)
        assert (linked.status, linked.incident_id) == ("linked", "inc-link-wins")
    finally:
        if not linker.done():
            gate.execute("SELECT pg_advisory_unlock(hashtext(%s))", ("al-link-wins",))
            linker.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(linker, return_exceptions=True), timeout=5)
        finally:
            if closer is not None:
                await asyncio.wait_for(asyncio.gather(closer, return_exceptions=True), timeout=5)
            _remove_link_gate(gate, "al-link-wins")
            gate.close()
