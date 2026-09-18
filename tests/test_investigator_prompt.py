"""Input the investigator harness assembles for each gateway turn (issue #185)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from sre_agent.investigator.contract import (
    CollectedEvidence,
    InvestigationRequest,
    ToolInvocation,
    Turn,
)
from sre_agent.investigator.prompt import assemble

STATE = (
    Path(__file__).parents[1] / "agent/fixtures/incidents/otel-payment-failure/declared-state.yaml"
)
WHEN = "2026-09-18T12:00:00Z"


def request() -> InvestigationRequest:
    state = yaml.safe_load(STATE.read_text(encoding="utf-8"))
    return InvestigationRequest.model_validate(
        {
            "incident_id": state["incident_id"],
            "run_id": "run_a1b2c3d4e5",
            "objective": "investigate",
            "context": state,
            "authorized_capabilities": state["authorized_capabilities"],
        }
    )


def state_of(prompt: str) -> dict[str, object]:
    return dict(json.loads(prompt.split("State: ", 1)[1].splitlines()[0]))


def test_the_prompt_carries_only_the_declared_context() -> None:
    prompt = assemble(request(), [], [], steps_left=6)
    state = state_of(prompt)

    assert state["authorized_tools"] == ["query_prometheus"]
    assert (state["objective"], state["steps_left"]) == ("investigate", 6)
    assert "ev_payment_error_rate" in prompt
    assert "dec_declare" not in prompt and "evt_declared" not in prompt
    assert "previous reply was rejected" not in prompt


def test_collected_evidence_and_tool_calls_are_carried_forward() -> None:
    evidence = CollectedEvidence(
        evidence_id="ev_new", source="fixture", summary="errors rose", collected_at=WHEN
    )
    invocation = ToolInvocation(tool="query_prometheus", arguments={"window": "2m"})
    turn = Turn(
        turn_id="turn_a1b2c3d4",
        task_id="task_a1b2c3d4",
        sequence=0,
        occurred_at=WHEN,
        tool_invocation=invocation,
    )
    state = state_of(assemble(request(), [evidence], [turn], steps_left=5))

    assert state["collected_evidence"] == [
        {
            "evidence_id": "ev_new",
            "source": "fixture",
            "tool": None,
            "query": None,
            "time_window": None,
            "summary": "errors rose",
        }
    ]
    assert state["tool_calls"] == [{"tool": "query_prometheus", "arguments": {"window": "2m"}}]


def test_a_rejected_reply_is_explained_on_the_next_turn() -> None:
    prompt = assemble(request(), [], [], steps_left=5, feedback="output: Invalid JSON")

    assert prompt.endswith("Your previous reply was rejected: output: Invalid JSON. Reply again.")
