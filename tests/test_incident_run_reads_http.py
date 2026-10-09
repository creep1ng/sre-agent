"""Issue #330: the run state and run events of the runs contract, on real PostgreSQL.

`GET /v1/incidents/{incident_id}/runs/{run_id}` and `.../events` reuse the read path
of #189: the same authorization (`run.read` on the pinned workflow), the same event
projection and the same cursor. Written from what the routes could get wrong: a caller
without a credential or without the grant, an identifier, limit or cursor the contract
does not admit, an incident or run that does not exist, a run addressed under another
incident, a state whose cursor does not match what it shows, a page that skips or
repeats an event, and a state paired with the events of a transition that landed
between the two reads.

The module starts from the store #189 prepares: its principals, credentials and grant,
and one incident driven to `investigating`, which no case changes. A case that writes
seeds its own incident.
"""

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_incident_authorized_reads import (
    BEARERS,
    COMMANDS,
    DATABASE_URL,
    INCIDENT_ID,
    NOW,
    RUN_ID,
    _base_state,
    prepare_authorized_database,
)

from sre_agent.application import create_application
from sre_agent.gateway.incidents import StateReadRaceError, consistent_run_state
from sre_agent.incident.persistence import RunRecord
from sre_agent.incident.runtime import IncidentRuntime
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from validate_run_api import ERROR_ENVELOPE_PATH, SCHEMAS, build_validator, load_yaml  # noqa: E402

WORKFLOW = load_incident_workflow(REPOSITORY_ROOT / "agent/workflows/incident-response.yaml")
RUN_STATE = build_validator(load_yaml(SCHEMAS["run-state"]))
EVENT_PAGE = build_validator(load_yaml(SCHEMAS["run-event"]))
ENVELOPE = build_validator(json.loads(ERROR_ENVELOPE_PATH.read_text(encoding="utf-8")))
STATE = f"/v1/incidents/{INCIDENT_ID}/runs/{RUN_ID}"
EVENTS = f"{STATE}/events"


@pytest.fixture(scope="module", autouse=True)
def authorized_database() -> None:
    prepare_authorized_database()


def _drive(incident_id: str, run_id: str, steps: slice, *, seed: bool = False) -> None:
    """Apply the commands of #189 to another incident, seeding it first when asked."""

    database = Database(DATABASE_URL)

    async def _apply() -> None:
        if seed:
            async with PostgresIncidentUnitOfWork(database) as work:
                await work.incidents.add(incident_id, _base_state(), now=NOW)
                await work.runs.add(
                    run_id,
                    incident_id,
                    {"workflow_version": "1.0.0", "current_state": "detected", "status": "running"},
                    now=NOW,
                )
        runtime = IncidentRuntime(
            WORKFLOW, lambda: PostgresIncidentUnitOfWork(database), clock=lambda: NOW
        )
        for command in COMMANDS[steps]:
            await runtime.execute(replace(command, incident_id=incident_id, run_id=run_id))

    try:
        asyncio.run(_apply())
    finally:
        asyncio.run(database.dispose())


def _sequences(run_id: str) -> list[int]:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT sequence FROM incident.run_events WHERE run_id = %s ORDER BY sequence",
            (run_id,),
        ).fetchall()
    return [row[0] for row in rows]


def _get(path: str, bearer: str | None = "demo") -> Any:
    headers = {} if bearer is None else {"Authorization": BEARERS.get(bearer, bearer)}
    # A fresh application on every request: what is read comes from the store,
    # never from memory a previous request left behind.
    return TestClient(create_application(Settings(DATABASE_URL))).get(path, headers=headers)


def _get_with_query_log(path: str) -> tuple[Any, list[tuple[str, Any]]]:
    app = create_application(Settings(DATABASE_URL))
    statements: list[tuple[str, Any]] = []

    def capture(_connection, _cursor, statement, parameters, _context, _executemany) -> None:
        statements.append((statement, parameters))

    engine = app.state.database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        with TestClient(app) as client:
            response = client.get(path, headers={"Authorization": BEARERS["demo"]})
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    return response, statements


def _assert_run_lookup_is_scoped(
    statements: list[tuple[str, Any]], *, incident_id: str, run_id: str
) -> None:
    run_queries = [
        (statement.lower(), parameters)
        for statement, parameters in statements
        if "from incident.runs" in statement.lower()
    ]
    assert run_queries
    for statement, parameters in run_queries:
        normalized = " ".join(statement.split())
        assert "where run_id=" in normalized and "and incident_id=" in normalized, normalized
        assert run_id in str(parameters)
        assert incident_id in str(parameters)
    assert not any(
        "from incident.snapshots" in query.lower() or "from incident.run_events" in query.lower()
        for query, _ in statements
    )


def _refused(response: Any, status: int, code: str) -> None:
    """A refusal is the shared error envelope of the contract, with the expected code."""

    assert response.status_code == status
    body = response.json()
    assert ENVELOPE.is_valid(body), list(ENVELOPE.iter_errors(body))
    assert body["error"]["code"] == code


def test_a_request_without_a_usable_credential_is_401() -> None:
    for path in (STATE, EVENTS):
        for bearer in (None, "Bearer not-a-key"):
            response = _get(path, bearer)
            _refused(response, 401, "authentication_failed")
            assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_credential_without_run_read_is_403_and_reveals_nothing() -> None:
    for path in (STATE, EVENTS):
        response = _get(path, "bystander")
        _refused(response, 403, "not_authorized")
        for detail in (INCIDENT_ID, RUN_ID, "paymentservice", "investigating"):
            assert detail not in response.text


@pytest.mark.parametrize(
    ("path", "code"),
    [
        (f"/v1/incidents/X/runs/{RUN_ID}", "validation_error"),
        (f"/v1/incidents/{INCIDENT_ID}/runs/run-1", "validation_error"),
        (f"/v1/incidents/{INCIDENT_ID}/runs/run-1/events", "validation_error"),
        (f"{EVENTS}?limit=0", "validation_error"),
        (f"{EVENTS}?limit=201", "validation_error"),
        (f"{EVENTS}?limit=many", "validation_error"),
        (f"{EVENTS}?after=nope", "invalid_cursor"),
        (f"{EVENTS}?after=seq:-2", "invalid_cursor"),
    ],
    ids=[
        "incident-id",
        "run-id",
        "events-run-id",
        "limit-zero",
        "limit-over",
        "limit-text",
        "cursor-text",
        "cursor-negative",
    ],
)
def test_a_request_the_contract_does_not_admit_is_422(path: str, code: str) -> None:
    _refused(_get(path), 422, code)


def test_a_missing_incident_or_run_is_404() -> None:
    for path, code in (
        ("/v1/incidents/inc-reads-absent/runs/run_increadsabsent", "incident_not_found"),
        ("/v1/incidents/inc-reads-absent/runs/run_increadsabsent/events", "incident_not_found"),
        (f"/v1/incidents/{INCIDENT_ID}/runs/run_increadsabsent", "run_not_found"),
        (f"/v1/incidents/{INCIDENT_ID}/runs/run_increadsabsent/events", "run_not_found"),
    ):
        _refused(_get(path), 404, code)


def test_a_run_of_another_incident_is_404_on_both_routes() -> None:
    _drive("inc-reads-elsewhere", "run_increadselse1", slice(1), seed=True)
    for path in (
        f"/v1/incidents/inc-reads-elsewhere/runs/{RUN_ID}",
        f"/v1/incidents/inc-reads-elsewhere/runs/{RUN_ID}/events",
    ):
        response, statements = _get_with_query_log(path)
        _refused(response, 404, "run_not_found")
        assert "investigating" not in response.text
        _assert_run_lookup_is_scoped(statements, incident_id="inc-reads-elsewhere", run_id=RUN_ID)


def test_the_state_is_the_stored_run_with_a_cursor_for_its_last_event() -> None:
    response = _get(STATE)
    assert response.status_code == 200
    state = response.json()
    assert RUN_STATE.is_valid(state), list(RUN_STATE.iter_errors(state))
    assert (state["run_id"], state["incident_id"]) == (RUN_ID, INCIDENT_ID)
    assert (state["current_state"], state["status"]) == ("investigating", "running")
    assert state["cursor"] == f"seq:{_sequences(RUN_ID)[-1]}"
    # Read again through another application instance: the same stored state.
    assert _get(STATE).json() == state


def test_events_come_in_order_and_continue_from_their_cursor() -> None:
    sequences = _sequences(RUN_ID)
    assert len(sequences) >= 3
    first = _get(f"{EVENTS}?limit=2").json()
    assert EVENT_PAGE.is_valid(first), list(EVENT_PAGE.iter_errors(first))
    assert [event["sequence"] for event in first["events"]] == sequences[:2]
    assert (first["has_more"], first["next_cursor"]) == (True, f"seq:{sequences[1]}")
    rest = _get(f"{EVENTS}?after={first['next_cursor']}&limit=200").json()
    assert EVENT_PAGE.is_valid(rest), list(EVENT_PAGE.iter_errors(rest))
    assert [event["sequence"] for event in rest["events"]] == sequences[2:]
    assert (rest["has_more"], rest["next_cursor"]) == (False, f"seq:{sequences[-1]}")
    assert _get(EVENTS).json()["events"] == first["events"] + rest["events"]


def test_polling_from_the_state_cursor_returns_exactly_what_came_after() -> None:
    incident_id, run_id = "inc-reads-poll", "run_increadspoll1"
    _drive(incident_id, run_id, slice(2), seed=True)
    state = _get(f"/v1/incidents/{incident_id}/runs/{run_id}").json()
    events = f"/v1/incidents/{incident_id}/runs/{run_id}/events?after={state['cursor']}"
    quiet = _get(events).json()
    assert (quiet["events"], quiet["has_more"], quiet["next_cursor"]) == (
        [],
        False,
        state["cursor"],
    )
    before = _sequences(run_id)
    _drive(incident_id, run_id, slice(2, 3))
    fresh = _get(events).json()
    new = [sequence for sequence in _sequences(run_id) if sequence not in before]
    assert new and [event["sequence"] for event in fresh["events"]] == new
    later = _get(f"/v1/incidents/{incident_id}/runs/{run_id}").json()
    assert (state["current_state"], later["current_state"]) == ("active", "investigating")
    assert later["cursor"] == fresh["next_cursor"] == f"seq:{new[-1]}"


class RacingUnit:
    """A unit of work whose run moves on while its events are being read."""

    def __init__(self, races: int) -> None:
        self.reads, self.races = 0, races
        self.runs, self.snapshots, self.events = self, self, self

    async def get_for_incident(self, run_id: str, incident_id: str) -> RunRecord:
        self.reads += 1
        # Each pair of reads is one attempt; the first `races` attempts see a
        # transition land between their two reads.
        attempt, second = divmod(self.reads - 1, 2)
        version = attempt + 1 if attempt < self.races and second else attempt
        return RunRecord(run_id, incident_id, {}, version, NOW, NOW)

    async def latest(self, run_id: str) -> None:
        return None

    async def list_after(self, run_id: str, *, sequence: int, limit: int) -> tuple[Any, ...]:
        return ()


def test_a_transition_landing_mid_read_is_read_again_and_never_paired_wrong() -> None:
    settled = asyncio.run(
        consistent_run_state(RacingUnit(races=2), "run_increadsrace", "inc-reads-race")
    )  # type: ignore[arg-type]
    assert settled is not None and settled[0].version == 2
    with pytest.raises(StateReadRaceError):
        asyncio.run(consistent_run_state(RacingUnit(races=3), "run_increadsrace", "inc-reads-race"))  # type: ignore[arg-type]


def test_a_read_that_keeps_racing_is_503_and_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def racing(work: Any, run_id: str, incident_id: str) -> None:
        raise StateReadRaceError(run_id)

    monkeypatch.setattr("sre_agent.gateway.incidents.consistent_run_state", racing)
    response = _get(STATE)
    _refused(response, 503, "storage_unavailable")
    assert (response.headers["Retry-After"], response.json()["retryable"]) == ("5", True)


class PagedUnit:
    """A unit of work with more events after its latest snapshot than fit in one page."""

    def __init__(self, snapshot: int, last: int) -> None:
        self.snapshot, self.last, self.reads = snapshot, last, []
        self.runs, self.snapshots, self.events = self, self, self

    async def get_for_incident(self, run_id: str, incident_id: str) -> RunRecord:
        return RunRecord(run_id, incident_id, {}, 7, NOW, NOW)

    async def latest(self, run_id: str) -> Any:
        return SimpleNamespace(event_sequence=self.snapshot)

    async def list_after(self, run_id: str, *, sequence: int, limit: int) -> tuple[Any, ...]:
        self.reads.append(sequence)
        stop = min(self.last, sequence + limit)
        return tuple(SimpleNamespace(sequence=value) for value in range(sequence + 1, stop + 1))


def test_the_cursor_reaches_the_last_event_from_the_snapshot_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sre_agent.gateway.incidents.EVENT_PAGE", 2)
    unit = PagedUnit(snapshot=3, last=8)
    found = asyncio.run(consistent_run_state(unit, "run_increadspaged", "inc-reads-paged"))  # type: ignore[arg-type]
    assert found is not None and found[1] == 8
    # Read from the snapshot on, one page after another: never from the first event.
    assert unit.reads == [3, 5, 7]
