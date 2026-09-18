"""Unit tests for incident read projections (HT-INC-RUNTIME-B, issue #189).

Pure functions only: no I/O, no authentication, no framework. HTTP behavior
and storage wiring are covered by later slices of the stack.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sre_agent.incident.persistence import IncidentRecord, SnapshotRecord
from sre_agent.incident.projections import (
    UnsupportedWorkflowDataError,
    project_detail,
    project_snapshot,
)
from sre_agent.incident.workflow import load_incident_workflow

WORKFLOW = load_incident_workflow("agent/workflows/incident-response.yaml")
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
ALERT = {
    "alert_id": "alt-payment-error-rate",
    "service": "paymentservice",
    "severity": "sev2",
    "status": "triaged",
    "observed_at": "2026-08-24T14:05:00Z",
    "summary": "Elevated error rate.",
    "source": "grafana-alerting",
}


def _record(**overrides):
    state = {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "investigating",
        "severity": "sev2",
        "alert": dict(ALERT),
        "approvals": [],
    }
    state.update(overrides)
    return IncidentRecord("inc-demo", state, 4, NOW, NOW)


def test_detail_projection_validates_stored_data() -> None:
    payload = project_detail(_record(), [], WORKFLOW)
    assert payload["incident_id"] == "inc-demo"
    assert payload["state"] == "investigating"
    assert payload["version"] == 4
    with pytest.raises(UnsupportedWorkflowDataError):
        project_detail(_record(workflow_version="9.9.9"), [], WORKFLOW)
    with pytest.raises(UnsupportedWorkflowDataError):
        project_detail(_record(state="nope"), [], WORKFLOW)
    with pytest.raises(UnsupportedWorkflowDataError):
        bad = dict(ALERT)
        del bad["service"]
        project_detail(_record(alert=bad), [], WORKFLOW)


def test_snapshot_projection_carries_coverage() -> None:
    snapshot = SnapshotRecord(
        "snap_demo0001",
        "inc-demo",
        "run_demo0001",
        4,
        2,
        _record().state,
        {"current_state": "investigating", "status": "running"},
        NOW,
    )
    payload = project_snapshot(snapshot, WORKFLOW)
    assert (payload["version"], payload["event_sequence"]) == (4, 2)
    assert payload["incident"]["incident_id"] == "inc-demo"
    assert payload["incident"]["state"] == "investigating"


def test_snapshot_projection_uses_historical_state_not_current_aggregate() -> None:
    historical = SnapshotRecord(
        "snap_demo0001",
        "inc-demo",
        "run_demo0001",
        1,
        0,
        _record(state="triage").state,
        {"current_state": "triage", "status": "running"},
        NOW,
    )
    payload = project_snapshot(historical, WORKFLOW)
    assert (payload["version"], payload["event_sequence"]) == (1, 0)
    incident = payload["incident"]
    assert incident["state"] == "triage"
    assert incident["version"] == 1
    assert incident["updated_at"] == "2026-09-08T12:00:00Z"
    run = payload["run"]
    assert (run["version"], run["current_state"]) == (1, "triage")
    assert "investigating" not in (incident["state"], run["current_state"])
