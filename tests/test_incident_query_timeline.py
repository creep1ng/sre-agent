"""Incident timeline, snapshot and PostgreSQL tests (HT-INC-RUNTIME-B, #189).

Covers CA2 (cursor pagination), CA3 (reload persistence against real storage),
CA4 (explicit absence) and CA6 (safe attribution). Detail/authorization tests
live in test_incident_query_detail.py; shared fakes in query_testkit.py.
Timeline projection unit tests (cursor codec, turn/task mapping, actor
references, event projection) live here with the timeline slice; read ports
plus detail/snapshot unit tests live in test_incident_projections.py (#257).
"""

from __future__ import annotations

import json
import os

import psycopg
import pytest
from alembic import command as alembic_command
from alembic.config import Config
from query_testkit import (
    AUTH,
    NOW,
    WORKFLOW,
    MemorySessions,
    MemoryUnits,
    _allow,
    _authenticated,
    _client,
    _decision_document,
    _seed,
    _service,
    _state,
)

from sre_agent.gateway.incidents import IncidentQueryService
from sre_agent.incident.persistence import (
    DecisionDraft,
    EventDraft,
    RunEvent,
    SnapshotDraft,
    SnapshotRecord,
)
from sre_agent.incident.projections import (
    MissingDecisionError,
    actor_reference,
    decode_cursor,
    encode_cursor,
    event_summary,
    gateway_task_id,
    project_event,
)
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork


def test_cursor_codec_round_trips_and_rejects() -> None:
    assert decode_cursor(None) == -1
    assert decode_cursor(encode_cursor(7)) == 7
    with pytest.raises(ValueError):
        decode_cursor("banana")


def test_task_mapping_never_leaks_raw_turn() -> None:
    assert gateway_task_id("turn_a1b2c3d4") == "task_a1b2c3d4"
    assert gateway_task_id(None) is None
    assert gateway_task_id("turn tailored") is None


def test_actor_reference_accepts_versioned_identities() -> None:
    document = {"actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"}}
    reference = actor_reference(document)
    assert reference is not None and reference["principal_id"] == "demo-human"
    assert actor_reference({"actor_reference": None}) is None
    assert actor_reference(None) is None


def test_event_projection_attributes_and_rejects() -> None:
    event = RunEvent(
        "evt_1",
        "inc-demo",
        "run_demo0001",
        0,
        "state_change",
        {"transition_id": "triage_declare", "to": "active", "decision_id": "dec_1"},
        NOW,
        None,
    )
    projected = project_event(event, {"actor": "human", "actor_reference": None})
    assert projected["summary"] == "Incident declared."
    assert projected["actor"] == {"type": "human", "reference": None}
    assert event_summary({}) == "Incident event recorded."
    with pytest.raises(MissingDecisionError):
        project_event(event, {"actor": "ghost"})


def test_timeline_paginates_by_cursor_without_duplicates() -> None:
    units = MemoryUnits()
    _seed(units)
    client = _client(_service(units))
    first = client.get("/v1/incidents/inc-demo/timeline", params={"limit": 2}, headers=AUTH).json()
    assert [event["sequence"] for event in first["events"]] == [0, 1]
    assert first["has_more"] is True
    second = client.get(
        "/v1/incidents/inc-demo/timeline",
        params={"after": first["next_cursor"], "limit": 2},
        headers=AUTH,
    ).json()
    assert [event["sequence"] for event in second["events"]] == [2]
    assert second["has_more"] is False
    assert first["next_cursor"] == "seq:1"
    assert second["next_cursor"] == "seq:2"


def test_timeline_rejects_invalid_cursor_without_reset() -> None:
    units = MemoryUnits()
    _seed(units)
    response = _client(_service(units)).get(
        "/v1/incidents/inc-demo/timeline", params={"after": "banana"}, headers=AUTH
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_timeline_projects_safe_attribution_without_raw_turn() -> None:
    units = MemoryUnits()
    _seed(units)
    events = (
        _client(_service(units))
        .get("/v1/incidents/inc-demo/timeline", headers=AUTH)
        .json()["events"]
    )
    human = next(event for event in events if event["actor"]["type"] == "human")
    assert human["actor"]["reference"]["principal_id"] == "demo-human"
    agent = next(event for event in events if event["actor"]["type"] == "agent")
    assert agent["turn_id"] == "turn_demo0001"
    assert agent["task_id"] == "task_demo0001"
    assert all(not str(event.get("task_id", "")).startswith("turn_") for event in events)
    blob = str(events)
    for forbidden in ("prompt", "secret", "token", "api_key", "authorization"):
        assert forbidden not in blob


def test_snapshot_absent_without_runs_or_snapshots() -> None:
    units = MemoryUnits()
    incident_id, _ = _seed(units)
    units._runs.clear()
    response = _client(_service(units)).get(f"/v1/incidents/{incident_id}/snapshot", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_absent"


def test_snapshot_reports_version_and_coverage() -> None:
    units = MemoryUnits()
    incident_id, run_id = _seed(units)
    units._snapshots[run_id] = SnapshotRecord(
        "snap_demo0001", incident_id, run_id, 4, 2, _state(), {}, NOW
    )
    payload = (
        _client(_service(units)).get(f"/v1/incidents/{incident_id}/snapshot", headers=AUTH).json()
    )
    assert payload["version"] == 4
    assert payload["event_sequence"] == 2
    assert payload["incident"]["incident_id"] == incident_id
    assert payload["run"]["run_id"] == run_id


def test_cross_incident_run_is_not_found() -> None:
    units = MemoryUnits()
    _seed(units)
    _seed(units, incident_id="inc-other", run_id="run_other001")
    response = _client(_service(units)).get(
        "/v1/incidents/inc-demo/timeline", params={"run_id": "run_other001"}, headers=AUTH
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"


DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55466/postgres"
)


@pytest.fixture(scope="module", autouse=True)
def _postgres_schema():
    """Ephemeral project database, same pattern as test_incident_persistence.py.

    No silent skips: an unreachable or misconfigured database fails loudly.
    """
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS alembic_version CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "mcp_tools, mcp_servers, "
            "principals, idempotency_records CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    alembic_command.upgrade(config, "head")


@pytest.mark.asyncio
async def test_snapshot_stays_historical_after_advance_and_recreate() -> None:
    """CA3 against real storage, including the historical/current mixing check.

    Persists a snapshot at triage (v1/seq0), advances the incident to
    investigating (v2), proves detail/timeline/snapshot before and after, then
    recreates pools and service and proves the historical snapshot is intact.
    A packaged-process restart is equivalent for this stateless service; the
    compose-smoke job covers the built image.
    """
    incident_id, run_id = "inc-pg-hist", "run_pghist0001"
    triage = _state(state="triage")
    investigating = _state(state="investigating")
    run_triage = {
        "workflow_version": "1.0.0",
        "current_state": "triage",
        "status": "running",
    }
    run_adv = {
        "workflow_version": "1.0.0",
        "current_state": "investigating",
        "status": "running",
    }

    async def _transition(
        suffix,
        incident_version,
        run_version,
        incident_state,
        run_state,
        transition_id,
        to,
        snapshot,
    ):
        database = Database(DATABASE_URL)
        try:
            async with PostgresIncidentUnitOfWork(database) as work:
                if incident_version == 0:
                    await work.incidents.add(incident_id, triage, now=NOW)
                    await work.runs.add(run_id, incident_id, run_triage, now=NOW)
                await work.persist_transition(
                    command_id=f"cmd_pghist_{suffix}",
                    payload_sha256={"t0": "a" * 64, "t1": "b" * 64}[suffix],
                    incident_id=incident_id,
                    run_id=run_id,
                    expected_incident_version=incident_version,
                    expected_run_version=run_version,
                    incident_state=incident_state,
                    run_state=run_state,
                    decision=DecisionDraft(
                        decision_id=f"dec_pghist_{suffix}",
                        document=_decision_document("human", "demo-human"),
                        decided_at=NOW,
                        run_id=run_id,
                    ),
                    events=(
                        EventDraft(
                            event_id=f"evt_pghist_{suffix}",
                            kind="state_change",
                            payload={
                                "transition_id": transition_id,
                                "to": to,
                                "decision_id": f"dec_pghist_{suffix}",
                            },
                            occurred_at=NOW,
                        ),
                    ),
                    snapshot=(
                        SnapshotDraft(
                            snapshot_id=f"snap_pghist_{suffix}",
                            incident_state=incident_state,
                            run_state=run_state,
                            created_at=NOW,
                        )
                        if snapshot
                        else None
                    ),
                )
        finally:
            await database.dispose()

    async def _query():
        database = Database(DATABASE_URL)
        try:
            service = IncidentQueryService(
                MemorySessions, WORKFLOW, lambda: PostgresIncidentUnitOfWork(database), _allow
            )
            service._authenticate = _authenticated
            detail = await service.get_detail(incident_id, AUTH["Authorization"])
            first = await service.get_timeline(incident_id, run_id, None, 1, AUTH["Authorization"])
            second = await service.get_timeline(
                incident_id,
                run_id,
                json.loads(first.body.decode())["next_cursor"],
                1,
                AUTH["Authorization"],
            )
            snapshot = await service.get_snapshot(incident_id, run_id, AUTH["Authorization"])
            assert detail.status_code == 200, detail.body.decode()[:200]
            assert first.status_code == 200, first.body.decode()[:200]
            assert second.status_code == 200, second.body.decode()[:200]
            assert snapshot.status_code == 200, snapshot.body.decode()[:200]
            return (
                json.loads(detail.body.decode()),
                json.loads(first.body.decode())["events"]
                + json.loads(second.body.decode())["events"],
                json.loads(snapshot.body.decode()),
            )
        finally:
            await database.dispose()

    await _transition("t0", 0, 0, triage, run_triage, "triage_declare", "triage", True)
    detail, events, snap = await _query()
    assert (detail["version"], detail["state"]) == (1, "triage")
    assert [event["sequence"] for event in events] == [0]
    assert (snap["version"], snap["event_sequence"]) == (1, 0)
    assert snap["incident"]["state"] == "triage"

    await _transition(
        "t1", 1, 1, investigating, run_adv, "start_investigation", "investigating", False
    )
    detail, events, snap = await _query()
    assert (detail["version"], detail["state"]) == (2, "investigating")
    assert [event["sequence"] for event in events] == [0, 1]
    assert (snap["version"], snap["event_sequence"]) == (1, 0)
    assert snap["incident"]["state"] == "triage"
    assert snap["incident"]["version"] == 1
    assert snap["run"]["current_state"] == "triage"

    recreated = await _query()
    assert recreated[0] == detail
    assert recreated[2] == snap
