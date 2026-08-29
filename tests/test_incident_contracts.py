"""Acceptance tests for the declarative incident contracts (HT-INC-01, issue #16).

Each test maps to one refined acceptance criterion of the issue, so a failure names
the criterion that regressed instead of a generic schema complaint.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from validate_incident_contracts import (  # noqa: E402
    STATE_SCHEMA_PATH,
    WORKFLOW_PATH,
    load_yaml,
    validate,
)


@pytest.fixture(scope="module")
def workflow() -> dict:
    return load_yaml(WORKFLOW_PATH)


@pytest.fixture(scope="module")
def state_schema() -> dict:
    return load_yaml(STATE_SCHEMA_PATH)


@pytest.fixture(scope="module")
def validator(state_schema: dict) -> Draft202012Validator:
    return Draft202012Validator(state_schema)


def _base_state() -> dict:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "incident_id": "inc-contract-test",
        "state": "detected",
        "alert": {
            "alert_id": "alt-contract-test",
            "service": "paymentservice",
            "severity": "sev2",
            "status": "new",
            "observed_at": "2026-08-24T14:05:00Z",
            "summary": "Elevated error rate.",
            "source": "grafana-alerting",
        },
        "updated_at": "2026-08-24T14:05:00Z",
    }


def test_every_contract_check_passes() -> None:
    """The full validator, exactly as CI runs it, reports no problems."""
    assert validate() == []


def test_workflow_covers_alert_intake_through_closure(workflow: dict) -> None:
    """Criterion: the workflow spans alert/triage through closure."""
    states = set(workflow["states"])
    expected = {
        "detected",
        "triage",
        "dismissed",
        "linked",
        "active",
        "investigating",
        "mitigating",
        "verifying",
        "resolved",
        "postmortem",
        "closed",
    }
    assert expected <= states
    assert workflow["initial_state"] == "detected"


def test_transitions_declare_actor_and_approval(workflow: dict) -> None:
    """Criterion: transitions state who acts and which need human approval."""
    for transition in workflow["transitions"]:
        assert transition.get("actor"), f"{transition['id']} declares no actor"
        assert "requires_approval" in transition, (
            f"{transition['id']} does not state whether approval is required"
        )

    approving = [
        transition for transition in workflow["transitions"] if transition.get("requires_approval")
    ]
    assert approving, "no transition requires human approval"
    assert {"apply_mitigation", "close_incident"} <= {t["id"] for t in approving}


def test_failed_verification_returns_to_investigation(workflow: dict) -> None:
    """Criterion: a failed verification can go back to investigating."""
    assert any(
        transition["from"] == "verifying" and transition["to"] == "investigating"
        for transition in workflow["transitions"]
    )


def test_decision_points_live_inline(workflow: dict) -> None:
    """Approved MVP decision: no separate incident-decisions.yaml exists."""
    assert workflow["decision_points"], "no inline decision points declared"
    assert not (REPOSITORY_ROOT / "agent" / "policies" / "incident-decisions.yaml").exists()


def test_workflow_and_schema_carry_explicit_versions(workflow: dict, state_schema: dict) -> None:
    """Criterion: files carry explicit id/version so a run is reproducible."""
    assert workflow["workflow_id"] == "incident-response"
    assert workflow["workflow_version"] == "1.0.0"
    assert state_schema["$id"].endswith(":1.0.0")
    assert state_schema["properties"]["workflow_version"]["pattern"]


def test_state_keeps_only_four_first_class_artifacts(state_schema: dict) -> None:
    """Criterion: alert, hypothesis, mitigation strategy and postmortem only."""
    properties = set(state_schema["properties"])
    assert {"alert", "hypotheses", "mitigation_strategy", "postmortem"} <= properties
    assert "anomaly" not in properties
    assert "anomalies" not in properties
    assert state_schema["additionalProperties"] is False


def test_anomaly_is_only_alert_origin_metadata(
    validator: Draft202012Validator, state_schema: dict
) -> None:
    """Criterion: anomaly data may appear only nested under alert.origin."""
    assert "origin" in state_schema["$defs"]["alert"]["properties"]

    state = _base_state()
    state["alert"]["origin"] = {
        "signal": "traces_span_metrics_calls_total",
        "detector": "webstore-metrics",
    }
    assert validator.is_valid(state)

    rejected = _base_state()
    rejected["anomaly"] = {"anomaly_id": "ano-1"}
    assert not validator.is_valid(rejected)


def test_closure_requires_a_postmortem(validator: Draft202012Validator) -> None:
    """Approved rule: the postmortem may be minimal but must exist before closing."""
    without = _base_state() | {"state": "closed", "severity": "sev2", "postmortem": None}
    assert not validator.is_valid(without)

    with_draft = _base_state() | {
        "state": "closed",
        "severity": "sev2",
        "postmortem": {
            "postmortem_id": "pm_contract_test",
            "summary": "Payment failure caused by an enabled feature flag.",
            "status": "draft",
            "created_by": "agent",
            "created_at": "2026-08-24T15:00:00Z",
        },
    }
    assert validator.is_valid(with_draft)


def test_declared_incident_requires_severity(validator: Draft202012Validator) -> None:
    """A declared incident always carries a severity."""
    assert not validator.is_valid(_base_state() | {"state": "investigating"})
    assert validator.is_valid(_base_state() | {"state": "investigating", "severity": "sev2"})


def test_evidence_is_never_trusted(state_schema: dict) -> None:
    """Security rule: tool and knowledge output is data, never instruction."""
    assert state_schema["$defs"]["evidence"]["properties"]["trusted"]["const"] is False


def test_evidence_and_decisions_carry_audit_correlation(state_schema: dict) -> None:
    """Criterion: an agentic step references its gateway authorization decision."""
    for definition in ("evidence", "decision", "timeline_event"):
        assert "audit_id" in state_schema["$defs"][definition]["properties"], definition


def test_capabilities_use_the_governed_resource_vocabulary(state_schema: dict) -> None:
    """The state reuses the gateway resource types instead of inventing its own."""
    declared = set(state_schema["$defs"]["capability"]["properties"]["resource_type"]["enum"])
    assert declared == {"llm_model", "mcp_server", "mcp_tool", "skill", "bok_collection"}


def test_process_stage_mapping_is_declared_and_bounded(workflow: dict) -> None:
    """Deliverable: mapeo estados operativos <-> etapas 0-11."""
    assert workflow["process_stage_range"] == [0, 11]
    assert workflow["process_stage_mapping_status"] in {"pending_reconciliation", "complete"}
    for name, definition in workflow["states"].items():
        assert "process_stages" in (definition or {}), f"state '{name}' declares no stage list"


def test_completing_the_stage_mapping_requires_actually_mapping_it() -> None:
    """The status cannot be flipped to complete while stages are unmapped."""
    from validate_incident_contracts import check_process_stage_mapping

    workflow = load_yaml(WORKFLOW_PATH)
    workflow["process_stage_mapping_status"] = "complete"
    assert check_process_stage_mapping(workflow), "an empty mapping was accepted as complete"

    workflow["states"]["detected"]["process_stages"] = [12]
    assert check_process_stage_mapping(workflow)


def test_process_stage_is_typed_as_a_bounded_index(state_schema: dict) -> None:
    """The runtime state carries a stage index, not a free-form label."""
    stage = state_schema["properties"]["process_stage"]
    assert stage["type"] == ["integer", "null"]
    assert stage["minimum"] == 0
    assert stage["maximum"] == 11


def test_runtime_state_machine_is_not_implemented_yet() -> None:
    """Out of scope for Sprint 1: the runtime engine belongs to HT-INC-02 (#26)."""
    assert not (REPOSITORY_ROOT / "src" / "sre_agent" / "incident" / "state_machine.py").exists()
