"""Opening a run on the authoritative store (HT-INC-COMMANDS, issue #330).

Written from how opening a run can go wrong: an objective with no transition, an
incident that does not exist, a retry of one idempotency key, that key reused for
a different request, an objective the current state does not admit, and a run
left without the snapshot its replay needs. Every case runs against PostgreSQL;
the runtime owns the rules and this exercises them, never a second copy.
"""

import os
from datetime import UTC, datetime

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from sre_agent.incident.persistence import IncidentIdempotencyConflictError
from sre_agent.incident.runtime import (
    ActorReference,
    IncidentNotFoundError,
    IncidentRuntime,
    InvalidTransitionError,
    RunStart,
)
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 26, 9, tzinfo=UTC)
OPERATOR = ActorReference(principal_id="demo-human", display_name="Demo human")


@pytest.fixture(scope="module", autouse=True)
def run_start_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS alembic_version CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "mcp_tools, mcp_servers, principals, idempotency_records CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


def incident_state(state: str) -> dict:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": state,
        "severity": "sev2" if state != "detected" else None,
        "impact": None,
        "alert": None,
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": NOW.isoformat(),
    }


@pytest.fixture
def runtime() -> IncidentRuntime:
    workflow = load_incident_workflow("agent/workflows/incident-response.yaml")
    database = Database(DATABASE_URL)
    return IncidentRuntime(
        workflow, lambda: PostgresIncidentUnitOfWork(database), clock=lambda: NOW
    )


async def declared(runtime: IncidentRuntime, incident_id: str, state: str = "active") -> None:
    async with PostgresIncidentUnitOfWork(Database(DATABASE_URL)) as work:
        await work.incidents.add(incident_id, incident_state(state), now=NOW)


async def run_ids(incident_id: str) -> tuple[str, ...]:
    async with PostgresIncidentUnitOfWork(Database(DATABASE_URL)) as work:
        return await work.runs.list_ids(incident_id)


def opening(incident_id: str, objective: str, key: str) -> RunStart:
    return RunStart(
        command_id=key,
        incident_id=incident_id,
        objective=objective,
        actor="human",
        actor_reference=OPERATOR,
    )


@pytest.mark.asyncio
async def test_an_objective_without_transition_opens_no_run(runtime: IncidentRuntime) -> None:
    await declared(runtime, "inc-start-unknown")

    with pytest.raises(InvalidTransitionError):
        await runtime.start_run(opening("inc-start-unknown", "remediate", "key-unknown-01"))

    assert await run_ids("inc-start-unknown") == ()


@pytest.mark.asyncio
async def test_an_absent_incident_opens_no_run(runtime: IncidentRuntime) -> None:
    with pytest.raises(IncidentNotFoundError):
        await runtime.start_run(opening("inc-start-absent", "investigate", "key-absent-01"))

    assert await run_ids("inc-start-absent") == ()


@pytest.mark.asyncio
async def test_an_objective_the_state_does_not_admit_opens_no_run(
    runtime: IncidentRuntime,
) -> None:
    await declared(runtime, "inc-start-wrong-state")

    with pytest.raises(InvalidTransitionError):
        await runtime.start_run(opening("inc-start-wrong-state", "postmortem", "key-wrong-01"))

    assert await run_ids("inc-start-wrong-state") == ()


@pytest.mark.asyncio
async def test_retrying_one_key_returns_the_first_run(runtime: IncidentRuntime) -> None:
    await declared(runtime, "inc-start-retry")
    request = opening("inc-start-retry", "investigate", "key-retry-01")

    first = await runtime.start_run(request)
    second = await runtime.start_run(request)

    assert first.replayed is False and second.replayed is True
    assert first.run.run_id == second.run.run_id
    assert await run_ids("inc-start-retry") == (first.run.run_id,)


@pytest.mark.asyncio
async def test_one_key_reused_for_another_request_conflicts(runtime: IncidentRuntime) -> None:
    await declared(runtime, "inc-start-conflict", "detected")
    opened = await runtime.start_run(opening("inc-start-conflict", "triage", "key-conflict-01"))

    with pytest.raises(IncidentIdempotencyConflictError):
        await runtime.start_run(opening("inc-start-conflict", "investigate", "key-conflict-01"))

    assert await run_ids("inc-start-conflict") == (opened.run.run_id,)


@pytest.mark.asyncio
async def test_the_opened_run_replays_from_its_first_snapshot(runtime: IncidentRuntime) -> None:
    await declared(runtime, "inc-start-replay")

    opened = await runtime.start_run(opening("inc-start-replay", "investigate", "key-replay-01"))
    replayed = await runtime.reconstruct("inc-start-replay", opened.run.run_id)

    assert opened.run.state["current_state"] == "investigating"
    assert replayed.run_state == opened.run.state
    assert replayed.incident_state == opened.incident.state
