"""Safe read projections for incidents (HT-INC-RUNTIME-B, issue #189).

Pure functions over persisted records. No I/O, no authentication, no framework
imports: anything the UI may read must be allow-listed in
agent/api/projection-policy.v1.yaml, and this module only emits those fields.
Timeline order always comes from one run's sequence (ADR-008).
"""

import re
from datetime import datetime
from typing import Any

from sre_agent.incident.persistence import IncidentRecord, RunEvent, RunRecord, SnapshotRecord
from sre_agent.incident.workflow import IncidentWorkflow

IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"
RUN_ID_PATTERN = r"^run_[a-z0-9]{8,32}$"
CURSOR_PATTERN = r"^seq:(-?\d+)$"
SEVERITIES = frozenset({"sev1", "sev2", "sev3", "sev4"})

TRANSITION_SUMMARIES = {
    "open_triage": "Triage opened.",
    "triage_dismiss": "Alert dismissed.",
    "triage_link": "Alert linked to an existing incident.",
    "triage_declare": "Incident declared.",
    "start_investigation": "Investigation started.",
    "continue_investigation": "Investigation continued.",
    "propose_mitigation": "Mitigation proposed.",
    "apply_mitigation": "Mitigation approved.",
    "reject_mitigation": "Mitigation sent back for changes.",
    "verification_failed": "Verification failed; returned to investigating.",
    "verification_passed": "Service verified stable.",
    "start_postmortem": "Postmortem started.",
    "close_incident": "Incident closed.",
}


class UnsupportedWorkflowDataError(Exception):
    """Persisted data names something outside the supported contract."""


class MissingDecisionError(Exception):
    """A persisted event references a decision that storage cannot return."""


def utc_iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def encode_cursor(sequence: int) -> str:
    return f"seq:{sequence}"


def decode_cursor(after: str | None) -> int:
    if after is None:
        return -1
    match = re.fullmatch(CURSOR_PATTERN, after)
    if match is None:
        raise ValueError(f"invalid cursor: {after!r}")
    sequence = int(match.group(1))
    if sequence < -1:
        raise ValueError(f"invalid cursor: {after!r}")
    return sequence


def gateway_task_id(turn_id: str | None) -> str | None:
    """Map the internal turn identifier to the gateway-facing task identifier (C05)."""
    if turn_id is None:
        return None
    match = re.fullmatch(r"^turn_([a-z0-9]{8,32})$", turn_id)
    if match is None:
        return None
    return f"task_{match.group(1)}"


def actor_reference(document: Any) -> dict[str, Any] | None:
    if not isinstance(document, dict):
        return None
    reference = document.get("actor_reference")
    if reference is None:
        return None
    if not isinstance(reference, dict):
        return None
    principal_id = reference.get("principal_id")
    display_name = reference.get("display_name")
    if (
        reference.get("reference_version") != "1.0.0"
        or not isinstance(principal_id, str)
        or re.fullmatch(IDENTIFIER_PATTERN, principal_id) is None
        or (display_name is not None and not isinstance(display_name, str))
    ):
        return None
    return {
        "reference_version": "1.0.0",
        "principal_id": principal_id,
        "display_name": display_name,
    }


def event_summary(payload: Any) -> str:
    transition_id = payload.get("transition_id") if isinstance(payload, dict) else None
    if isinstance(transition_id, str) and transition_id in TRANSITION_SUMMARIES:
        return TRANSITION_SUMMARIES[transition_id]
    if isinstance(transition_id, str):
        return f"Transition {transition_id} applied."
    return "Incident event recorded."


def project_event(event: RunEvent, decision_document: Any) -> dict[str, Any]:
    actor = decision_document.get("actor") if isinstance(decision_document, dict) else None
    if actor not in ("human", "agent", "system"):
        raise MissingDecisionError(f"event '{event.event_id}' has no attributable actor")
    payload = event.payload if isinstance(event.payload, dict) else {}
    state = payload.get("to")
    return {
        "event_id": event.event_id,
        "kind": "state_change",
        "sequence": event.sequence,
        "state": state if isinstance(state, str) else None,
        "summary": event_summary(payload),
        "actor": {"type": actor, "reference": actor_reference(decision_document)},
        "turn_id": event.turn_id,
        "task_id": gateway_task_id(event.turn_id),
        "request_id": None,
        "occurred_at": utc_iso(event.occurred_at),
    }


def project_alert(alert: Any) -> dict[str, Any]:
    for field in ("alert_id", "service", "severity", "status", "observed_at", "summary", "source"):
        value = alert.get(field) if isinstance(alert, dict) else None
        if not isinstance(value, str) or not value:
            raise UnsupportedWorkflowDataError(f"stored alert is missing '{field}'")
    if alert["severity"] not in SEVERITIES:
        raise UnsupportedWorkflowDataError("stored alert carries an unknown severity")
    projected = {
        field: alert[field]
        for field in (
            "alert_id",
            "service",
            "severity",
            "status",
            "observed_at",
            "summary",
            "source",
        )
    }
    origin = alert.get("origin")
    if origin is not None:
        if not isinstance(origin, dict):
            raise UnsupportedWorkflowDataError("stored alert origin is malformed")
        if set(origin) - {"signal", "condition", "detector", "observed_at"}:
            raise UnsupportedWorkflowDataError("stored alert origin carries unknown fields")
        projected["origin"] = {
            key: origin[key]
            for key in ("signal", "condition", "detector", "observed_at")
            if isinstance(origin.get(key), str)
        }
    return projected


def project_approvals(state: Any) -> list[dict[str, Any]]:
    approvals = state.get("approvals", []) if isinstance(state, dict) else []
    if not isinstance(approvals, list):
        raise UnsupportedWorkflowDataError("stored approvals are malformed")
    projected = []
    for entry in approvals:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("approval_id"), str)
            or not isinstance(entry.get("subject_id"), str)
            or not isinstance(entry.get("granted"), bool)
            or not isinstance(entry.get("decided_at"), str)
        ):
            raise UnsupportedWorkflowDataError("stored approval entry is malformed")
        projected.append(
            {
                "approval_id": entry["approval_id"],
                "subject_id": entry["subject_id"],
                "granted": entry["granted"],
                "decided_at": entry["decided_at"],
            }
        )
    return projected


def project_run_summary(run: RunRecord) -> dict[str, Any]:
    state = run.state if isinstance(run.state, dict) else {}
    status = state.get("status")
    current_state = state.get("current_state")
    return {
        "run_id": run.run_id,
        "version": run.version,
        "status": status if isinstance(status, str) else None,
        "current_state": current_state if isinstance(current_state, str) else None,
        "updated_at": utc_iso(run.updated_at),
    }


def project_detail(
    record: IncidentRecord, runs: list[RunRecord], workflow: IncidentWorkflow
) -> dict[str, Any]:
    state = record.state if isinstance(record.state, dict) else {}
    supported = (
        state.get("workflow_version") == workflow.version
        and state.get("workflow_id") == workflow.workflow_id
    )
    if not supported:
        raise UnsupportedWorkflowDataError("stored incident uses an unsupported workflow version")
    if state.get("state") not in workflow.states:
        raise UnsupportedWorkflowDataError("stored incident names an unknown state")
    severity = state.get("severity")
    if severity is not None and severity not in SEVERITIES:
        raise UnsupportedWorkflowDataError("stored incident carries an unknown severity")
    impact = state.get("impact")
    return {
        "incident_id": record.incident_id,
        "workflow_version": workflow.version,
        "state": state.get("state"),
        "severity": severity,
        "impact": impact if isinstance(impact, str) else None,
        "alert": project_alert(state.get("alert")),
        "approvals": project_approvals(state),
        "version": record.version,
        "updated_at": utc_iso(record.updated_at),
        "runs": [project_run_summary(run) for run in runs],
    }


def project_snapshot(
    snapshot: SnapshotRecord, detail: dict[str, Any], run: RunRecord
) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "incident_id": snapshot.incident_id,
        "run_id": snapshot.run_id,
        "version": snapshot.version,
        "event_sequence": snapshot.event_sequence,
        "incident": detail,
        "run": project_run_summary(run),
        "created_at": utc_iso(snapshot.created_at),
    }
