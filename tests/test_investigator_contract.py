"""Contract tests for the investigator harness input and output (issue #185)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from sre_agent.investigator.contract import (
    InvalidOutput,
    InvestigationRequest,
    InvestigationResult,
    Limits,
    parse_action,
    task_id_for,
    unknown_references,
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


@pytest.mark.parametrize(
    "text",
    [
        '{"action": "use_tool", "tool": "query_prometheus", "arguments": {"window": "2m"}}',
        '{"action": "request_human", "reason": "Evidence is contradictory."}',
        '{"action": "conclude", "summary": "Payment is unreachable."}',
        '```json\n{"action": "conclude", "summary": "Payment is unreachable."}\n```',
    ],
)
def test_valid_outputs_parse_into_one_action(text: str) -> None:
    assert parse_action(text).action in {"use_tool", "request_human", "conclude"}


@pytest.mark.parametrize(
    "text",
    [
        "sk-not-a-secret, not json",
        '{"action": "restart_pod", "target": "payment"}',
        '{"action": "propose_hypothesis", "statement": "x", "confidence": "high"}',
        '{"action": "request_human", "reason": "x", "tools": []}',
        'Answer: {"action": "conclude", "summary": "x"}',
    ],
)
def test_invalid_outputs_are_rejected_without_echoing_them(text: str) -> None:
    with pytest.raises(InvalidOutput) as raised:
        parse_action(text)

    assert "sk-not-a-secret" not in str(raised.value)


def test_citations_must_exist_in_the_context_or_the_run() -> None:
    subject = request()
    uncited = parse_action(
        '{"action": "propose_hypothesis", "statement": "x", "confidence": "low",'
        ' "supporting_evidence": ["ev_payment_error_rate", "ev_new", "ev_invented"]}'
    )
    mitigation = parse_action(
        '{"action": "propose_mitigation", "description": "x", "steps": ["Disable the flag"],'
        ' "risk": "low", "verification_check": "x", "based_on_hypothesis": "hyp_invented"}'
    )

    assert unknown_references(uncited, subject, collected={"ev_new"}) == ["ev_invented"]
    assert unknown_references(mitigation, subject) == ["hyp_invented"]


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
