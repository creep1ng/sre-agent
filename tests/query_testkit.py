"""Shared fakes and builders for incident query tests (HT-INC-RUNTIME-B, #189).

Not collected as tests (no test_ prefix): import from test_incident_query_*.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from sre_agent.gateway.incidents import IncidentQueryService, incident_router
from sre_agent.governance.authorization import (
    AuthorizationDenialCause,
    AuthorizationEvaluation,
)
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext
from sre_agent.incident.persistence import (
    DecisionRecord,
    IncidentRecord,
    RunEvent,
    RunRecord,
    SnapshotRecord,
)
from sre_agent.incident.workflow import load_incident_workflow

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
