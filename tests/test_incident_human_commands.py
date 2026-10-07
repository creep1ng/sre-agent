"""Issue #330 B1: human commands over the real incident store.

Written from what could go wrong before the translation existed: approving a
mitigation nobody proposed, an approval record left behind by a command that is
not an approval, a rejection and a request for changes collapsing into one
indistinct decision, a disposition without its branch, a command the workflow
has no transition for passing silently, and a retried command deciding twice.

Every case goes through the real runtime against real PostgreSQL, so a pass
means the workflow and the store agree, not that a double answered.
"""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml
from alembic import command as alembic
from alembic.config import Config

from sre_agent.incident.commands import HumanCommand, resolve
from sre_agent.incident.persistence import IncidentIdempotencyConflictError
from sre_agent.incident.runtime import (
    ActorReference,
    IncidentRuntime,
    InvalidTransitionError,
    PreconditionFailedError,
)
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INITIAL_STATE_PATH = (
    REPOSITORY_ROOT / "agent/fixtures/incidents/otel-payment-failure/initial-state.yaml"
)
DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
OPERATOR = ActorReference(principal_id="incident-operator", display_name="Operator on call")
MITIGATION = {
    "mitigation_id": "mit-disable-payment-flag",
    "description": "Disable the paymentFailure flag in flagd.",
    "steps": ["Ask the operator to set paymentFailure to off."],
    "risk": "low",
    "verification_check": "Payment error rate stays below one percent for ten minutes.",
    "approval_status": "pending",
    "execution_mode": "human",
    "created_by": "agent",
    "created_at": NOW.isoformat(),
}


@pytest.fixture(scope="module", autouse=True)
def incident_store() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, bok_section_chunks, bok_documents, "
            "bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, "
            "resources, alert_triage, mcp_tools, mcp_servers, "
            "principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    alembic.upgrade(config, "head")


def _database() -> Database:
    return Database(DATABASE_URL)


def _runtime(database: Database) -> IncidentRuntime:
    workflow = load_incident_workflow(REPOSITORY_ROOT / "agent/workflows/incident-response.yaml")
    return IncidentRuntime(
        workflow, lambda: PostgresIncidentUnitOfWork(database), clock=lambda: NOW
    )


async def _seed(database: Database, identifier: str, state: str, **fields: Any) -> str:
    document = yaml.safe_load(INITIAL_STATE_PATH.read_text())
    document.update(state=state, **fields)
    run_id = f"run_{identifier.replace('-', '')[:16]}"
    awaiting = state == "mitigating"
    async with PostgresIncidentUnitOfWork(database) as work:
        await work.incidents.add(identifier, document, now=NOW)
        await work.runs.add(
            run_id,
            identifier,
            {
                "workflow_version": "1.0.0",
                "current_state": state,
                "status": "awaiting_human" if awaiting else "running",
                "pending_command": "approve_mitigation" if awaiting else None,
            },
            now=NOW,
        )
    return run_id


async def _proposed(database: Database, incident_id: str) -> str:
    """An incident whose agent already proposed a mitigation awaiting a human."""
    return await _seed(
        database,
        incident_id,
        "mitigating",
        incident_id=incident_id,
        severity="sev2",
        mitigation_strategy=dict(MITIGATION),
    )


async def _decision(database: Database, result: Any) -> dict[str, Any]:
    decision_id = result.events[-1].payload["decision_id"]
    async with PostgresIncidentUnitOfWork(database) as work:
        record = await work.decisions.get(decision_id)
    assert record is not None
    return dict(record.document)


def _command(incident_id: str, run_id: str, name: str, **fields: Any) -> HumanCommand:
    return HumanCommand(
        command_id=fields.pop("command_id", f"cmd-{incident_id}-{name}"),
        incident_id=incident_id,
        run_id=run_id,
        command=name,
        actor_reference=OPERATOR,
        **fields,
    )


def test_approving_a_mitigation_nobody_proposed_changes_nothing() -> None:
    async def scenario() -> None:
        database = _database()
        run_id = await _seed(
            database,
            "inc-b1-investigating",
            "investigating",
            incident_id="inc-b1-investigating",
            severity="sev2",
        )
        with pytest.raises(InvalidTransitionError):
            await _runtime(database).execute(
                resolve(_command("inc-b1-investigating", run_id, "approve_mitigation"))
            )
        async with PostgresIncidentUnitOfWork(database) as work:
            incident = await work.incidents.get("inc-b1-investigating")
            events = await work.events.list_after(run_id, sequence=-1, limit=10)
        assert incident is not None and incident.state["state"] == "investigating"
        assert list(events) == []
        await database.dispose()

    asyncio.run(scenario())


def test_the_approval_is_attributed_to_the_human_who_gave_it() -> None:
    async def scenario() -> None:
        database = _database()
        run_id = await _proposed(database, "inc-b1-approved")
        result = await _runtime(database).execute(
            resolve(
                _command(
                    "inc-b1-approved",
                    run_id,
                    "approve_mitigation",
                    comment="Blast radius reviewed with the payments owner.",
                )
            )
        )
        document = await _decision(database, result)
        assert result.incident.state["state"] == "verifying"
        assert result.incident.state["mitigation_strategy"]["approval_status"] == "approved"
        assert document["approval"]["approved"] is True
        assert document["approval"]["actor_reference"]["principal_id"] == "incident-operator"
        assert document["comment"] == "Blast radius reviewed with the payments owner."
        assert result.run.state["status"] == "running"
        assert result.run.state["pending_command"] is None
        await database.dispose()

    asyncio.run(scenario())


def test_a_command_that_is_not_an_approval_leaves_no_approval_record() -> None:
    async def scenario() -> None:
        database = _database()
        run_id = await _proposed(database, "inc-b1-rejected")
        result = await _runtime(database).execute(
            resolve(_command("inc-b1-rejected", run_id, "reject_mitigation"))
        )
        document = await _decision(database, result)
        assert result.incident.state["state"] == "investigating"
        assert result.incident.state["mitigation_strategy"]["approval_status"] == "rejected"
        assert document["approval"] is None
        await database.dispose()

    asyncio.run(scenario())


def test_rejecting_and_requesting_changes_stay_distinguishable() -> None:
    async def scenario() -> None:
        database = _database()
        run_id = await _proposed(database, "inc-b1-changes")
        result = await _runtime(database).execute(
            resolve(_command("inc-b1-changes", run_id, "request_changes"))
        )
        document = await _decision(database, result)
        assert result.incident.state["state"] == "investigating"
        assert document["outcome"] == "request_changes"
        assert (
            result.incident.state["mitigation_strategy"]["approval_status"] == "changes_requested"
        )
        await database.dispose()

    asyncio.run(scenario())


def test_a_disposition_without_its_branch_is_refused() -> None:
    async def scenario() -> None:
        database = _database()
        run_id = await _seed(database, "inc-b1-triage", "triage")
        engine = _runtime(database)
        with pytest.raises(InvalidTransitionError):
            resolve(_command("inc-b1-triage", run_id, "propose_disposition"))
        with pytest.raises(PreconditionFailedError):
            await engine.execute(
                resolve(
                    _command("inc-b1-triage", run_id, "propose_disposition", disposition="declare")
                )
            )
        missing = object()
        invalid_impacts = (
            ("missing", missing),
            ("null", None),
            ("number", 7),
            ("boolean", True),
            ("array", []),
            ("blank", " \t\n "),
            ("too-long", "x" * 2001),
        )
        for label, impact in invalid_impacts:
            inputs = {"severity": "sev2"}
            if impact is not missing:
                inputs["impact"] = impact
            with pytest.raises(PreconditionFailedError, match="impact"):
                await engine.execute(
                    resolve(
                        _command(
                            "inc-b1-triage",
                            run_id,
                            "propose_disposition",
                            command_id=f"cmd-b1-declare-invalid-{label}",
                            disposition="declare",
                            inputs=inputs,
                        )
                    )
                )
        async with PostgresIncidentUnitOfWork(database) as work:
            unchanged = await work.incidents.get("inc-b1-triage")
            events = await work.events.list_after(run_id, sequence=-1, limit=10)
        assert unchanged is not None
        assert unchanged.state["state"] == "triage"
        assert unchanged.state.get("impact") is None
        assert list(events) == []
        result = await engine.execute(
            resolve(
                _command(
                    "inc-b1-triage",
                    run_id,
                    "propose_disposition",
                    command_id="cmd-b1-declare-ok",
                    disposition="declare",
                    inputs={
                        "severity": "sev2",
                        "impact": "Operators report that checkout cannot process payments.",
                    },
                )
            )
        )
        assert result.incident.state["state"] == "active"
        assert result.incident.state["severity"] == "sev2"
        assert (
            result.incident.state["impact"]
            == "Operators report that checkout cannot process payments."
        )
        assert (
            result.events[-1].payload["incident_state"]["impact"]
            == "Operators report that checkout cannot process payments."
        )
        await database.dispose()

    asyncio.run(scenario())


def test_commands_without_a_transition_are_refused_by_name() -> None:
    for name in ("escalate", "cancel_run", "delete_everything"):
        with pytest.raises(InvalidTransitionError) as refusal:
            resolve(_command("inc-b1-any", "run_b1any", name))
        assert name in str(refusal.value)
    with pytest.raises(InvalidTransitionError):
        resolve(_command("inc-b1-any", "run_b1any", "approve_mitigation", disposition="declare"))


def test_a_retried_command_replays_instead_of_deciding_twice() -> None:
    async def scenario() -> None:
        database = _database()
        run_id = await _proposed(database, "inc-b1-retry")
        engine = _runtime(database)
        first = await engine.execute(
            resolve(_command("inc-b1-retry", run_id, "approve_mitigation"))
        )
        again = await engine.execute(
            resolve(_command("inc-b1-retry", run_id, "approve_mitigation"))
        )
        assert again.replayed is True
        assert again.incident.version == first.incident.version
        with pytest.raises(IncidentIdempotencyConflictError):
            await engine.execute(
                resolve(
                    _command(
                        "inc-b1-retry",
                        run_id,
                        "approve_mitigation",
                        comment="different request, same key",
                    )
                )
            )
        async with PostgresIncidentUnitOfWork(database) as work:
            events = await work.events.list_after(run_id, sequence=-1, limit=10)
        assert len(list(events)) == 1
        await database.dispose()

    asyncio.run(scenario())
