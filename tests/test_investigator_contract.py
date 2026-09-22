"""Contract tests for the investigator harness input and output (issue #185)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from sre_agent.investigator.contract import (
    InvestigationRequest,
    InvestigationResult,
    Limits,
    task_id_for,
)

ROOT = Path(__file__).parents[1]
TURN = {"turn_id": "turn_a1b2c3d4", "task_id": "task_a1b2c3d4", "sequence": 0}
WHEN = "2026-09-18T12:00:00Z"
HYPOTHESIS = {
    "action": "propose_hypothesis",
    "statement": "Checkout cannot reach payment.",
    "confidence": "high",
    "supporting_evidence": ["ev_payment_error_rate"],
}


def load(path: str) -> Any:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def request(**changes: Any) -> InvestigationRequest:
    state = load("agent/fixtures/incidents/otel-payment-failure/declared-state.yaml")
    document = {
        "incident_id": state["incident_id"],
        "run_id": "run_a1b2c3d4e5",
        "objective": "investigate",
        "context": state,
        "authorized_capabilities": state["authorized_capabilities"],
    }
    return InvestigationRequest.model_validate(document | changes)


def test_a_full_incident_state_is_a_valid_context() -> None:
    subject = request()

    assert subject.context.incident_id == subject.incident_id
    assert [item.evidence_id for item in subject.context.evidence] == ["ev_payment_error_rate"]
    assert subject.authorizes_tool("query_prometheus")
    assert not subject.authorizes_tool("query_elasticsearch")
    assert not subject.authorizes_tool("triage-agent")


@pytest.mark.parametrize("change", [{"run_id": "run-001"}, {"objective": "remediate"}])
def test_request_rejects_foreign_identifiers(change: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        request(**change)


def test_request_rejects_a_state_without_agentic_step() -> None:
    state = load("agent/fixtures/incidents/otel-payment-failure/declared-state.yaml")
    with pytest.raises(ValidationError):
        request(context=state | {"state": "active"})


def test_request_rejects_context_for_a_different_incident() -> None:
    with pytest.raises(ValidationError, match="context incident_id must match request incident_id"):
        request(incident_id="inc-another-incident")


def test_task_id_is_derived_from_the_turn() -> None:
    assert task_id_for("turn_a1b2c3d4") == "task_a1b2c3d4"
    with pytest.raises(ValueError):
        task_id_for("task_a1b2c3d4")


def test_result_conforms_to_run_context_and_incident_evidence() -> None:
    tool = {"tool": "query_prometheus", "arguments": {"window": "2m"}, "result_summary": "x"}
    evidence = {"evidence_id": "ev_new", "source": "fixture", "summary": "x", "collected_at": WHEN}
    result = InvestigationResult.model_validate(
        {
            "incident_id": "inc-otel-payment-failure",
            "run_id": "run_a1b2c3d4e5",
            "status": "completed",
            "outcome": HYPOTHESIS,
            "evidence": [evidence],
            "turns": [TURN | {"occurred_at": WHEN, "tool_invocation": tool}],
        }
    ).model_dump(mode="json")
    run_context = load("agent/schemas/run-context.schema.yaml")
    incident = load("agent/schemas/incident-state.schema.yaml")
    context = {key: result[key] for key in ("run_id", "incident_id", "turns")}

    Draft202012Validator(run_context, format_checker=FormatChecker()).validate(
        context | {"retrieved_at": WHEN}
    )
    Draft202012Validator(incident["$defs"]["evidence"], format_checker=FormatChecker()).validate(
        result["evidence"][0]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"status": "completed", "outcome": None},
        {"status": "denied"},
        {"status": "completed", "outcome": {"action": "request_human", "reason": "x"}},
        {"turns": [TURN | {"occurred_at": WHEN, "sequence": 1}]},
        {"turns": [TURN | {"occurred_at": WHEN, "task_id": "task_other000"}]},
        {"turns": [TURN | {"occurred_at": "2026-09-18T12:00:00"}]},
        {"outcome": HYPOTHESIS | {"supporting_evidence": []}},
        {"outcome": HYPOTHESIS | {"tools": []}},
        {"outcome": {"action": "use_tool", "tool": "query_prometheus"}},
    ],
)
def test_result_rejects_inconsistent_or_malformed_results(change: dict[str, Any]) -> None:
    valid = {
        "incident_id": "inc-otel-payment-failure",
        "run_id": "run_a1b2c3d4e5",
        "status": "completed",
        "outcome": HYPOTHESIS,
    }
    with pytest.raises(ValidationError):
        InvestigationResult.model_validate(valid | change)


def test_limits_are_the_values_set_for_the_definition_of_ready() -> None:
    assert Limits().model_dump() == {
        "max_steps": 6,
        "transient_retries": 1,
        "gateway_timeout_seconds": 45.0,
        "tool_timeout_seconds": 10.0,
    }
