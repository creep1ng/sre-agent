"""Acceptance tests for authoritative incident queries (HT-INC-RUNTIME-B, issue #189).

Reads project persisted aggregates without mutating them: incident detail,
cursor-paginated timeline and public snapshot, with authentication,
workflow-scoped authorization and safe projections. HTTP behavior is covered
through the real router with in-memory ports; PostgreSQL wiring (reload
persistence) is covered by a dedicated database test.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.gateway.incidents import IncidentQueryService, incident_router
from sre_agent.governance.authorization import (
    AuthorizationDenialCause,
    AuthorizationEvaluation,
)
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext
from sre_agent.incident.persistence import (
    DecisionDraft,
    EventDraft,
    IncidentRecord,
    RunEvent,
    RunRecord,
    SnapshotRecord,
)
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

WORKFLOW = load_incident_workflow("agent/workflows/incident-response.yaml")
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
AUTH = {"Authorization": "Bearer sre_demo_token_demo_0001"}

ALERT = {
    "alert_id": "alt-payment-error-rate",
    "service": "paymentservice",
    "severity": "sev2",
    "status": "triaged",
    "observed_at": "2026-08-24T14:05:00Z",
    "summary": "Elevated error rate on paymentservice.",
    "source": "grafana-alerting",
    "origin": {
        "signal": "traces_span_metrics_calls_total",
        "condition": "error rate above threshold",
        "detector": "webstore-metrics",
        "observed_at": "2026-08-24T14:04:30Z",
    },
}


def _state(**overrides):
    state = {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "investigating",
        "severity": "sev2",
        "impact": "Checkout failing at payment.",
        "alert": dict(ALERT),
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": "2026-08-24T14:20:00Z",
    }
    state.update(overrides)
    return state


def _decision_document(actor, principal_id=None):
    return {
        "actor": actor,
        "actor_reference": (
            {
                "reference_version": "1.0.0",
                "principal_id": principal_id,
                "display_name": "On-call engineer",
            }
            if principal_id is not None
            else None
        ),
    }


class MemoryUnits:
    """In-memory IncidentUnitOfWork for read-path tests."""

    def __init__(self):
        self._incidents: dict[str, IncidentRecord] = {}
        self._runs: dict[str, RunRecord] = {}
        self._events: dict[str, list[RunEvent]] = {}
        self._snapshots: dict[str, SnapshotRecord] = {}
        self._decisions: dict[str, dict] = {}
        self.incidents = self._Incidents(self)
        self.runs = self._Runs(self)
        self.events = self._Events(self)
        self.snapshots = self._Snapshots(self)
        self.decisions = self._Decisions(self)

    class _Incidents:
        def __init__(self, outer):
            self._outer = outer

        async def get(self, incident_id):
            return self._outer._incidents.get(incident_id)

    class _Runs:
        def __init__(self, outer):
            self._outer = outer

        async def get(self, run_id):
            return self._outer._runs.get(run_id)

        async def list_ids(self, incident_id):
            return tuple(
                run_id
                for run_id, run in self._outer._runs.items()
                if run.incident_id == incident_id
            )

    class _Events:
        def __init__(self, outer):
            self._outer = outer

        async def list_after(self, run_id, *, sequence=-1, limit=1000):
            events = [
                event for event in self._outer._events.get(run_id, []) if event.sequence > sequence
            ]
            return tuple(events[:limit])

    class _Snapshots:
        def __init__(self, outer):
            self._outer = outer

        async def latest(self, run_id):
            return self._outer._snapshots.get(run_id)

    class _Decisions:
        def __init__(self, outer):
            self._outer = outer

        async def get(self, decision_id):
            document = self._outer._decisions.get(decision_id)
            if document is None:
                return None
            from sre_agent.incident.persistence import DecisionRecord

            return DecisionRecord(
                decision_id=decision_id,
                incident_id="inc-demo",
                run_id="run_demo0001",
                turn_id=None,
                document=document,
                decided_at=NOW,
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class MemorySessions:
    """Trivial session factory; storage ports live on MemoryUnits."""

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return None


def _seed(units: MemoryUnits, *, incident_id="inc-demo", run_id="run_demo0001"):
    units._incidents[incident_id] = IncidentRecord(incident_id, _state(), 4, NOW, NOW)
    units._runs[run_id] = RunRecord(
        run_id,
        incident_id,
        {"workflow_version": "1.0.0", "current_state": "investigating", "status": "running"},
        4,
        NOW,
        NOW,
    )
    transitions = [
        ("triage_declare", "active", "human", "demo-human"),
        ("start_investigation", "investigating", "system", None),
        ("continue_investigation", "investigating", "agent", "incident-harness"),
    ]
    events = []
    for sequence, (transition_id, to, actor, principal) in enumerate(transitions):
        decision_id = f"dec_demo000{sequence}"
        units._decisions[decision_id] = _decision_document(actor, principal)
        events.append(
            RunEvent(
                f"evt_demo000{sequence}",
                incident_id,
                run_id,
                sequence,
                "state_change",
                {"transition_id": transition_id, "to": to, "decision_id": decision_id},
                NOW,
                "turn_demo0001" if actor == "agent" else None,
            )
        )
    units._events[run_id] = events
    return incident_id, run_id


def _principal():
    return Principal(
        principal_id="demo-human",
        kind="human",
        display_name="On-call engineer",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def _context():
    return PrincipalContext(principal=_principal(), credential_id="cred_demo", authenticated_at=NOW)


async def _allow(session, principal):
    return AuthorizationEvaluation(
        decision=PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="grant-x"),
        denial_cause=None,
    )


async def _deny(session, principal):
    return AuthorizationEvaluation(
        decision=PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None),
        denial_cause=AuthorizationDenialCause.GRANT_NOT_APPLICABLE,
    )


def _service(units, authorizer=_allow):
    service = IncidentQueryService(MemorySessions, WORKFLOW, lambda: units, authorizer)
    service._authenticate = _authenticated
    return service


async def _authenticated(authorization):
    if authorization != "Bearer sre_demo_token_demo_0001":
        return None
    return _context()


def _client(service):
    return TestClient(incident_router(service))


def test_detail_returns_identity_state_and_version() -> None:
    units = MemoryUnits()
    _seed(units)
    response = _client(_service(units)).get("/v1/incidents/inc-demo", headers=AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert payload["incident_id"] == "inc-demo"
    assert payload["state"] == "investigating"
    assert payload["severity"] == "sev2"
    assert payload["version"] == 4
    assert payload["alert"]["alert_id"] == "alt-payment-error-rate"
    assert [run["run_id"] for run in payload["runs"]] == ["run_demo0001"]


def test_detail_missing_incident_is_explicit() -> None:
    units = MemoryUnits()
    response = _client(_service(units)).get("/v1/incidents/inc-missing", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "incident_not_found"


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


def test_unauthenticated_and_unauthorized_reads_reveal_nothing() -> None:
    units = MemoryUnits()
    _seed(units)
    denied = _client(_service(units, authorizer=_deny))
    anonymous = denied.get("/v1/incidents/inc-demo")
    assert anonymous.status_code == 401
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"
    forbidden = denied.get("/v1/incidents/inc-demo", headers=AUTH)
    assert forbidden.status_code == 403
    assert "paymentservice" not in forbidden.text
    assert "inc-demo" not in forbidden.json()["error"]["message"]


def test_cross_incident_run_is_not_found() -> None:
    units = MemoryUnits()
    _seed(units)
    _seed(units, incident_id="inc-other", run_id="run_other001")
    response = _client(_service(units)).get(
        "/v1/incidents/inc-demo/timeline", params={"run_id": "run_other001"}, headers=AUTH
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"


def test_reads_do_not_mutate_authoritative_state() -> None:
    units = MemoryUnits()
    incident_id, run_id = _seed(units)
    client = _client(_service(units))
    client.get(f"/v1/incidents/{incident_id}", headers=AUTH)
    client.get(f"/v1/incidents/{incident_id}/timeline", headers=AUTH)
    assert units._incidents[incident_id].version == 4
    assert units._runs[run_id].version == 4
    assert len(units._events[run_id]) == 3


def _postgres_available(dsn: str) -> bool:
    import socket

    try:
        host, _, port = dsn.split("@")[1].split("/")[0].partition(":")
        with socket.create_connection((host or "127.0.0.1", int(port or 5432)), timeout=2):
            return True
    except Exception:
        return False


PG_DSN = "postgresql://davasgo2702@localhost/sre_189_test?host=/tmp"


@pytest.mark.asyncio
async def test_postgres_queries_survive_application_restart() -> None:
    """CA3 against real storage: fresh pools read the same persisted aggregates."""
    pytest.importorskip("psycopg")
    if not _postgres_available(PG_DSN):
        pytest.skip("PostgreSQL test database is unreachable")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", PG_DSN)

    import psycopg as _psycopg

    def _reset():
        # Append-only tables forbid DELETE by trigger; reset like the
        # persistence suite does: drop schemas, governance tables, the audit
        # trigger and the version row, then migrate from scratch.
        with _psycopg.connect(PG_DSN, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
            connection.execute("DROP TABLE IF EXISTS alembic_version CASCADE")
            connection.execute(
                "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
                "principals, idempotency_records CASCADE"
            )
            connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")

    await _run_sync(_reset)
    await _run_sync(alembic_command.upgrade, config, "head")

    async def _seed_postgres():
        database = Database(PG_DSN)
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add("inc-pg-reload", _state(), now=NOW)
            await work.runs.add(
                "run_pgreload01",
                "inc-pg-reload",
                {
                    "workflow_version": "1.0.0",
                    "current_state": "investigating",
                    "status": "running",
                },
                now=NOW,
            )
            await work.persist_transition(
                command_id="cmd_pgreload01",
                payload_sha256="0" * 64,
                incident_id="inc-pg-reload",
                run_id="run_pgreload01",
                expected_incident_version=0,
                expected_run_version=0,
                incident_state=_state(),
                run_state={
                    "workflow_version": "1.0.0",
                    "current_state": "investigating",
                    "status": "running",
                },
                decision=DecisionDraft(
                    decision_id="dec_pgreload01",
                    document=_decision_document("human", "demo-human"),
                    decided_at=NOW,
                    run_id="run_pgreload01",
                ),
                events=(
                    EventDraft(
                        event_id="evt_pgreload01",
                        kind="state_change",
                        payload={
                            "transition_id": "triage_declare",
                            "to": "investigating",
                            "decision_id": "dec_pgreload01",
                        },
                        occurred_at=NOW,
                    ),
                ),
                snapshot=None,
            )
        await database.engine.dispose()

    await _seed_postgres()

    async def _read():
        database = Database(PG_DSN)
        service = IncidentQueryService(
            MemorySessions, WORKFLOW, lambda: PostgresIncidentUnitOfWork(database), _allow
        )
        service._authenticate = _authenticated
        detail = await service.get_detail("inc-pg-reload", AUTH["Authorization"])
        timeline = await service.get_timeline(
            "inc-pg-reload", "run_pgreload01", None, 50, AUTH["Authorization"]
        )
        assert detail.status_code == 200, detail.body.decode()[:200]
        assert timeline.status_code == 200, timeline.body.decode()[:200]
        body = json.loads(detail.body.decode())
        assert body["incident_id"] == "inc-pg-reload"
        assert body["version"] == 1
        events = json.loads(timeline.body.decode())["events"]
        assert [event["sequence"] for event in events] == [0]
        await database.engine.dispose()
        return body

    first = await _read()
    second = await _read()
    assert first == second


async def _run_sync(function, *args):
    import asyncio

    return await asyncio.to_thread(function, *args)
