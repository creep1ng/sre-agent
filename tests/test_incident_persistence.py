import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from sre_agent.incident.persistence import (
    DecisionDraft,
    EventDraft,
    IncidentIdempotencyConflictError,
    IncidentStaleWriteError,
    SnapshotDraft,
    TextContextRecord,
)
from sre_agent.incident.runtime import IncidentCommand, IncidentRuntime
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55466/postgres"
)
NOW = datetime(2026, 9, 7, 18, tzinfo=UTC)


@pytest.fixture(scope="module", autouse=True)
def incident_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS alembic_version CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


async def _seed(database: Database, suffix: str) -> tuple[str, str]:
    incident_id = f"inc_{suffix}"
    run_id = f"run_{suffix}"
    async with PostgresIncidentUnitOfWork(database) as unit:
        await unit.incidents.add(incident_id, {"state": "active"}, now=NOW)
        await unit.runs.add(
            run_id, incident_id, {"status": "running", "current_state": "active"}, now=NOW
        )
    return incident_id, run_id


def _decision(suffix: str, offset: int = 1) -> DecisionDraft:
    return DecisionDraft(
        decision_id=f"dec_{suffix}",
        document={"outcome": "continue", "actor": "agent"},
        decided_at=NOW + timedelta(seconds=offset),
        run_id=f"run_{suffix.split('_')[0]}",
        turn_id=f"turn_{suffix}",
    )


def _event(suffix: str, state: str, offset: int = 1) -> EventDraft:
    return EventDraft(
        event_id=f"evt_{suffix}",
        kind="state_change",
        payload={"state": state},
        occurred_at=NOW + timedelta(seconds=offset),
        turn_id=f"turn_{suffix}",
    )


@pytest.mark.asyncio
async def test_transition_is_atomic_ordered_and_idempotent() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = await _seed(database, "atomic0001")
    try:
        async with PostgresIncidentUnitOfWork(database) as unit:
            result = await unit.persist_transition(
                command_id="cmd_atomic_1",
                payload_sha256="a" * 64,
                incident_id=incident_id,
                run_id=run_id,
                expected_incident_version=0,
                expected_run_version=0,
                incident_state={"state": "investigating"},
                run_state={"status": "running", "current_state": "investigating"},
                decision=_decision("atomic0001"),
                events=(
                    _event("atomic0001_a", "triage"),
                    _event("atomic0001_b", "investigating", 2),
                ),
                snapshot=SnapshotDraft(
                    snapshot_id="snap_atomic0001",
                    incident_state={"state": "investigating"},
                    run_state={"status": "running", "current_state": "investigating"},
                    created_at=NOW + timedelta(seconds=2),
                ),
            )
        assert result.incident.version == result.run.version == 1
        assert [event.sequence for event in result.events] == [0, 1]
        assert result.snapshot is not None and result.snapshot.event_sequence == 1

        async with PostgresIncidentUnitOfWork(database) as unit:
            replay = await unit.persist_transition(
                command_id="cmd_atomic_1",
                payload_sha256="a" * 64,
                incident_id=incident_id,
                run_id=run_id,
                expected_incident_version=0,
                expected_run_version=0,
                incident_state={"ignored": True},
                run_state={"ignored": True},
                decision=_decision("ignored"),
                events=(),
            )
        assert replay.replayed is True
        assert replay == result.__class__(
            incident=result.incident,
            run=result.run,
            events=result.events,
            snapshot=result.snapshot,
            replayed=True,
        )

        with psycopg.connect(DATABASE_URL) as connection:
            counts = connection.execute(
                """SELECT
                  (SELECT count(*) FROM incident.decisions WHERE incident_id=%s),
                  (SELECT count(*) FROM incident.run_events WHERE run_id=%s),
                  (SELECT count(*) FROM incident.snapshots WHERE run_id=%s),
                  (SELECT count(*) FROM incident.transition_commits WHERE incident_id=%s)""",
                (incident_id, run_id, run_id, incident_id),
            ).fetchone()
        assert counts == (1, 2, 1, 1)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_concurrent_commands_reject_stale_writer_without_overwrite() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = await _seed(database, "stale0001")

    async def write(command: str, state: str) -> str:
        try:
            async with PostgresIncidentUnitOfWork(database) as unit:
                await unit.persist_transition(
                    command_id=command,
                    payload_sha256=command[-1] * 64,
                    incident_id=incident_id,
                    run_id=run_id,
                    expected_incident_version=0,
                    expected_run_version=0,
                    incident_state={"state": state},
                    run_state={"status": "running", "current_state": state},
                    decision=DecisionDraft(
                        decision_id=f"dec_{command}",
                        document={"outcome": state},
                        decided_at=NOW + timedelta(seconds=1),
                        run_id=run_id,
                    ),
                    events=(_event(command, state),),
                )
            return "committed"
        except IncidentStaleWriteError:
            return "stale"

    try:
        outcomes = await asyncio.gather(
            write("cmd_stale_1", "investigating"), write("cmd_stale_2", "mitigating")
        )
        assert sorted(outcomes) == ["committed", "stale"]
        async with PostgresIncidentUnitOfWork(database) as unit:
            incident = await unit.incidents.get(incident_id)
            events = await unit.events.list_after(run_id)
        assert incident is not None and incident.version == 1
        assert len(events) == 1
        assert incident.state["state"] == events[0].payload["state"]
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_atomic_failure_rolls_back_state_decision_and_events() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = await _seed(database, "rollback01")
    try:
        with pytest.raises(IntegrityError):
            async with PostgresIncidentUnitOfWork(database) as unit:
                await unit.persist_transition(
                    command_id="cmd_rollback_1",
                    payload_sha256="b" * 64,
                    incident_id=incident_id,
                    run_id=run_id,
                    expected_incident_version=0,
                    expected_run_version=0,
                    incident_state={"state": "investigating"},
                    run_state={"status": "running", "current_state": "investigating"},
                    decision=_decision("rollback01"),
                    events=(
                        _event("rollback01_duplicate", "triage"),
                        _event("rollback01_duplicate", "investigating", 2),
                    ),
                )
        async with PostgresIncidentUnitOfWork(database) as unit:
            incident = await unit.incidents.get(incident_id)
            run = await unit.runs.get(run_id)
            events = await unit.events.list_after(run_id)
        assert incident is not None and (incident.version, incident.state) == (
            0,
            {"state": "active"},
        )
        assert run is not None and run.version == 0
        assert events == ()
        with psycopg.connect(DATABASE_URL) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM incident.decisions WHERE incident_id=%s", (incident_id,)
                ).fetchone()[0]
                == 0
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_snapshot_replay_and_text_context_survive_database_restart() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = await _seed(database, "restart01")
    try:
        async with PostgresIncidentUnitOfWork(database) as unit:
            await unit.persist_transition(
                command_id="cmd_restart_1",
                payload_sha256="c" * 64,
                incident_id=incident_id,
                run_id=run_id,
                expected_incident_version=0,
                expected_run_version=0,
                incident_state={"state": "investigating"},
                run_state={"status": "running", "current_state": "investigating"},
                decision=_decision("restart01"),
                events=(_event("restart01_a", "investigating"),),
                snapshot=SnapshotDraft(
                    snapshot_id="snap_restart01",
                    incident_state={"state": "investigating"},
                    run_state={"status": "running", "current_state": "investigating"},
                    created_at=NOW + timedelta(seconds=1),
                ),
            )
            await unit.text_context.append(
                TextContextRecord(
                    turn_id="turn_restart01",
                    incident_id=incident_id,
                    run_id=run_id,
                    task_id="task_restart01",
                    sequence=0,
                    content={"assembled_input": "bounded input", "model_output": "bounded output"},
                    occurred_at=NOW + timedelta(seconds=1),
                )
            )
        async with PostgresIncidentUnitOfWork(database) as unit:
            await unit.persist_transition(
                command_id="cmd_restart_2",
                payload_sha256="d" * 64,
                incident_id=incident_id,
                run_id=run_id,
                expected_incident_version=1,
                expected_run_version=1,
                incident_state={"state": "mitigating"},
                run_state={"status": "awaiting_human", "current_state": "mitigating"},
                decision=DecisionDraft(
                    decision_id="dec_restart02",
                    document={"outcome": "mitigate"},
                    decided_at=NOW + timedelta(seconds=2),
                    run_id=run_id,
                ),
                events=(_event("restart01_b", "mitigating", 2),),
            )
    finally:
        await database.dispose()

    restarted = Database(DATABASE_URL)
    try:
        async with PostgresIncidentUnitOfWork(restarted) as unit:
            replay = await unit.load_replay(run_id)
            incident = await unit.incidents.get(incident_id)
            contexts = await unit.text_context.list(run_id)
        assert replay.snapshot is not None
        rebuilt = dict(replay.snapshot.incident_state)
        for event in replay.events:
            rebuilt["state"] = event.payload["state"]
        assert incident is not None and rebuilt == incident.state == {"state": "mitigating"}
        assert [event.sequence for event in replay.events] == [1]
        assert [
            (item.incident_id, item.run_id, item.turn_id, item.task_id) for item in contexts
        ] == [(incident_id, run_id, "turn_restart01", "task_restart01")]
    finally:
        await restarted.dispose()


@pytest.mark.asyncio
async def test_concurrent_duplicate_command_has_one_commit_and_exact_replay() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = await _seed(database, "idem00001")

    async def write() -> object:
        async with PostgresIncidentUnitOfWork(database) as unit:
            return await unit.persist_transition(
                command_id="cmd_idem_1",
                payload_sha256="e" * 64,
                incident_id=incident_id,
                run_id=run_id,
                expected_incident_version=0,
                expected_run_version=0,
                incident_state={"state": "investigating"},
                run_state={"status": "running", "current_state": "investigating"},
                decision=_decision("idem00001"),
                events=(_event("idem00001", "investigating"),),
            )

    try:
        first, second = await asyncio.gather(write(), write())
        assert {first.replayed, second.replayed} == {False, True}
        assert first.incident == second.incident
        assert first.events == second.events
        async with PostgresIncidentUnitOfWork(database) as unit:
            with pytest.raises(IncidentIdempotencyConflictError):
                await unit.get_transition(incident_id, "cmd_idem_1", "f" * 64)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_runtime_and_reader_roles_enforce_adapter_boundaries() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = await _seed(database, "roles0001")
    await database.dispose()
    separator = "&" if "?" in DATABASE_URL else "?"
    runtime_database = Database(f"{DATABASE_URL}{separator}options=-crole%3Dsre_incident_runtime")
    try:
        async with PostgresIncidentUnitOfWork(runtime_database) as unit:
            result = await unit.persist_transition(
                command_id="cmd_roles_1",
                payload_sha256="9" * 64,
                incident_id=incident_id,
                run_id=run_id,
                expected_incident_version=0,
                expected_run_version=0,
                incident_state={"state": "investigating"},
                run_state={"status": "running", "current_state": "investigating"},
                decision=_decision("roles0001"),
                events=(_event("roles0001", "investigating"),),
            )
        assert result.incident.version == 1
    finally:
        await runtime_database.dispose()

    reader_database = Database(f"{DATABASE_URL}{separator}options=-crole%3Dsre_incident_reader")
    try:
        async with PostgresIncidentUnitOfWork(reader_database) as unit:
            assert await unit.incidents.get(incident_id) is not None
        with pytest.raises(DBAPIError, match="permission denied"):
            async with PostgresIncidentUnitOfWork(reader_database) as unit:
                await unit.incidents.add("inc_reader_denied", {"state": "active"}, now=NOW)
    finally:
        await reader_database.dispose()


@pytest.mark.asyncio
async def test_replay_reads_every_event_beyond_one_page() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = await _seed(database, "paging001")
    rows = [
        (
            f"evt_paging_{sequence:04d}",
            incident_id,
            run_id,
            sequence,
            '{"state":"investigating"}',
            NOW,
        )
        for sequence in range(1001)
    ]
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO incident.run_events
                  (event_id, incident_id, run_id, sequence, kind, payload, occurred_at)
                  VALUES (%s, %s, %s, %s, 'state_change', %s, %s)""",
                rows,
            )
        connection.commit()
    try:
        async with PostgresIncidentUnitOfWork(database) as unit:
            replay = await unit.load_replay(run_id)
        assert len(replay.events) == 1001
        assert (replay.events[0].sequence, replay.events[-1].sequence) == (0, 1000)
        assert replay.incident.incident_id == incident_id
        assert replay.run.run_id == run_id
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_runtime_reconstructs_exact_state_from_postgres_after_restart() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = "inc_runtime01", "run_runtime01"
    workflow = load_incident_workflow(Path("agent/workflows/incident-response.yaml"))
    sequence = iter(range(10))

    def identity(prefix: str) -> str:
        return f"{prefix}_runtime{next(sequence):02d}"

    runtime = IncidentRuntime(
        workflow,
        lambda: PostgresIncidentUnitOfWork(database),
        clock=lambda: NOW,
        id_factory=identity,
        snapshot_interval=10,
    )
    initial_incident = {
        "incident_id": incident_id,
        "workflow_id": workflow.workflow_id,
        "workflow_version": workflow.version,
        "state": "active",
        "severity": "sev2",
        "updated_at": NOW.isoformat(),
    }
    initial_run = {
        "workflow_version": workflow.version,
        "current_state": "active",
        "status": "running",
        "pending_command": None,
        "updated_at": NOW.isoformat(),
    }
    try:
        async with PostgresIncidentUnitOfWork(database) as unit:
            await unit.incidents.add(incident_id, initial_incident, now=NOW)
            await unit.runs.add(run_id, incident_id, initial_run, now=NOW)
        start = IncidentCommand(
            command_id="cmd_runtime_1",
            incident_id=incident_id,
            run_id=run_id,
            transition_id="start_investigation",
            actor="system",
        )
        accepted = await runtime.execute(start)
        retried = await runtime.execute(start)
        assert accepted.replayed is False and retried.replayed is True
        assert accepted.incident == retried.incident
        await runtime.execute(
            IncidentCommand(
                command_id="cmd_runtime_2",
                incident_id=incident_id,
                run_id=run_id,
                transition_id="continue_investigation",
                actor="agent",
                inputs={"remaining_step_budget": 1},
            )
        )
        expected = await runtime.current(incident_id, run_id)
    finally:
        await database.dispose()

    restarted_database = Database(DATABASE_URL)
    restarted_runtime = IncidentRuntime(
        workflow,
        lambda: PostgresIncidentUnitOfWork(restarted_database),
        clock=lambda: NOW,
        id_factory=identity,
        snapshot_interval=10,
    )
    try:
        rebuilt = await restarted_runtime.reconstruct(incident_id, run_id)
        assert rebuilt == expected
    finally:
        await restarted_database.dispose()


@pytest.mark.asyncio
async def test_runtime_serializes_duplicate_validation_before_state_reads() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = "inc_duplicate01", "run_duplicate01"
    workflow = load_incident_workflow(Path("agent/workflows/incident-response.yaml"))
    entered, release = asyncio.Event(), asyncio.Event()

    class PausingUnitOfWork(PostgresIncidentUnitOfWork):
        async def get_transition(self, incident_id: str, command_id: str, payload_sha256: str):
            result = await super().get_transition(incident_id, command_id, payload_sha256)
            if result is None and not entered.is_set():
                entered.set()
                await release.wait()
            return result

    identities = iter(range(10))
    runtime = IncidentRuntime(
        workflow,
        lambda: PausingUnitOfWork(database),
        clock=lambda: NOW,
        id_factory=lambda prefix: f"{prefix}_duplicate{next(identities):02d}",
    )
    command_value = IncidentCommand(
        command_id="cmd_duplicate_1",
        incident_id=incident_id,
        run_id=run_id,
        transition_id="start_investigation",
        actor="system",
    )
    try:
        async with PostgresIncidentUnitOfWork(database) as unit:
            await unit.incidents.add(
                incident_id,
                {
                    "incident_id": incident_id,
                    "workflow_id": workflow.workflow_id,
                    "workflow_version": workflow.version,
                    "state": "active",
                    "severity": "sev2",
                },
                now=NOW,
            )
            await unit.runs.add(
                run_id,
                incident_id,
                {
                    "workflow_version": workflow.version,
                    "current_state": "active",
                    "status": "running",
                    "pending_command": None,
                },
                now=NOW,
            )
        first_task = asyncio.create_task(runtime.execute(command_value))
        await asyncio.wait_for(entered.wait(), timeout=2)
        duplicate_task = asyncio.create_task(runtime.execute(command_value))
        await asyncio.sleep(0.05)
        assert duplicate_task.done() is False
        release.set()
        first, duplicate = await asyncio.gather(first_task, duplicate_task)
        assert (first.replayed, duplicate.replayed) == (False, True)
        assert first.incident == duplicate.incident
    finally:
        release.set()
        await database.dispose()


@pytest.mark.asyncio
async def test_replay_watermark_blocks_a_concurrent_transition_until_consistent_read() -> None:
    database = Database(DATABASE_URL)
    incident_id, run_id = "inc_watermark01", "run_watermark01"
    workflow = load_incident_workflow(Path("agent/workflows/incident-response.yaml"))
    identities = iter(range(30))

    def identity(prefix: str) -> str:
        return f"{prefix}_watermark{next(identities):02d}"

    writer = IncidentRuntime(
        workflow,
        lambda: PostgresIncidentUnitOfWork(database),
        clock=lambda: NOW,
        id_factory=identity,
        snapshot_interval=10,
    )
    entered, release = asyncio.Event(), asyncio.Event()

    class PausingReplayUnitOfWork(PostgresIncidentUnitOfWork):
        async def load_replay(self, run_id: str):
            session = self._require_session()
            await session.execute(
                text("""SELECT i.incident_id FROM incident.incidents i
                    JOIN incident.runs r ON r.incident_id=i.incident_id
                    WHERE r.run_id=:run_id FOR SHARE OF i, r"""),
                {"run_id": run_id},
            )
            entered.set()
            await release.wait()
            return await super().load_replay(run_id)

    reader = IncidentRuntime(
        workflow,
        lambda: PausingReplayUnitOfWork(database),
        clock=lambda: NOW,
        id_factory=identity,
        snapshot_interval=10,
    )
    try:
        async with PostgresIncidentUnitOfWork(database) as unit:
            await unit.incidents.add(
                incident_id,
                {
                    "incident_id": incident_id,
                    "workflow_id": workflow.workflow_id,
                    "workflow_version": workflow.version,
                    "state": "active",
                    "severity": "sev2",
                },
                now=NOW,
            )
            await unit.runs.add(
                run_id,
                incident_id,
                {
                    "workflow_version": workflow.version,
                    "current_state": "active",
                    "status": "running",
                    "pending_command": None,
                },
                now=NOW,
            )
        await writer.execute(
            IncidentCommand(
                command_id="cmd_watermark_1",
                incident_id=incident_id,
                run_id=run_id,
                transition_id="start_investigation",
                actor="system",
            )
        )
        replay_task = asyncio.create_task(reader.reconstruct(incident_id, run_id))
        await asyncio.wait_for(entered.wait(), timeout=2)
        write_task = asyncio.create_task(
            writer.execute(
                IncidentCommand(
                    command_id="cmd_watermark_2",
                    incident_id=incident_id,
                    run_id=run_id,
                    transition_id="continue_investigation",
                    actor="agent",
                    inputs={"remaining_step_budget": 1},
                )
            )
        )
        await asyncio.sleep(0.05)
        assert write_task.done() is False
        release.set()
        replayed, committed = await asyncio.gather(replay_task, write_task)
        assert replayed.incident_version == replayed.run_version == 1
        assert replayed.incident_state["state"] == "investigating"
        assert committed.incident.version == committed.run.version == 2
    finally:
        release.set()
        await database.dispose()


def test_schema_roles_append_only_guards_and_bounded_context_isolation() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        owner = connection.execute(
            "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='incident'"
        ).fetchone()[0]
        assert owner == "sre_incident_owner"
        assert connection.execute(
            "SELECT rolcanlogin, rolsuper FROM pg_roles WHERE rolname='sre_incident_runtime'"
        ).fetchone() == (False, False)
        cross_schema_foreign_keys = connection.execute("""SELECT count(*)
          FROM pg_constraint c
          JOIN pg_class child ON child.oid=c.conrelid
          JOIN pg_namespace child_ns ON child_ns.oid=child.relnamespace
          JOIN pg_class parent ON parent.oid=c.confrelid
          JOIN pg_namespace parent_ns ON parent_ns.oid=parent.relnamespace
          WHERE c.contype='f' AND child_ns.nspname='incident'
            AND parent_ns.nspname<>'incident'""").fetchone()[0]
        assert cross_schema_foreign_keys == 0
        public_incident_tables = connection.execute("""SELECT count(*) FROM pg_tables
          WHERE schemaname='public' AND tablename IN
            ('incidents','runs','run_events','snapshots','text_context','decisions')""").fetchone()[
            0
        ]
        assert public_incident_tables == 0

        connection.execute("SET ROLE sre_incident_runtime")
        privileges = connection.execute("""SELECT
          has_table_privilege(current_user, 'incident.run_events', 'INSERT'),
          has_table_privilege(current_user, 'incident.run_events', 'UPDATE'),
          has_table_privilege(current_user, 'public.audit_events', 'SELECT')""").fetchone()
        assert privileges == (True, False, False)
        connection.execute("RESET ROLE")

        with pytest.raises(psycopg.errors.RaiseException), connection.transaction():
            connection.execute("SET ROLE sre_incident_owner")
            connection.execute(
                "UPDATE incident.run_events SET payload='{}' WHERE event_id='evt_atomic0001_a'"
            )


def test_incident_migration_downgrade_and_recovery_are_reproducible() -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.downgrade(config, "20260907_05")
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute("SELECT to_regnamespace('incident') IS NULL").fetchone()[0] is True
        )
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "20260910_07"
        )
        assert (
            connection.execute("SELECT to_regclass('incident.run_events') IS NOT NULL").fetchone()[
                0
            ]
            is True
        )
