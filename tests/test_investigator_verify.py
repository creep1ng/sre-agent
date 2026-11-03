"""A verification is a bounded investigation of one approved mitigation (#723, cut b1).

Written before the objective and its outcome existed. Ways it can fail:
1. a verification is asked without the mitigation it checks, or an investigation carries one;
2. the model is not told what ran and what must hold now, or is offered the outcomes of an
   investigation (a hypothesis, a mitigation, a conclusion);
3. a verification ends with an investigation's outcome, or an investigation with a verdict;
4. a verdict cites no evidence measured in this verification: only what the investigation
   measured before the mitigation ran, or only a query that came back empty;
5. a measured verdict, passed or not, does not complete with what was measured.
The model and the tools are scripted as in the loop's tests.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import yaml
from pydantic import JsonValue, ValidationError
from test_investigator_loop import STATE, TOOL, Provider, ScriptedGateway, hypothesis, ids, run

from sre_agent.investigator.contract import InvestigationRequest, InvestigationResult, Limits
from sre_agent.investigator.loop import investigate
from sre_agent.investigator.ports import ToolResult

OPERATION = {
    "service": "paymentservice",
    "operation": "deployment.rollback",
    "parameters": {"to_tag": "1.4.0"},
}
# The mitigation as the incident keeps it once the approval ran it (#722).
MITIGATION = {
    "mitigation_id": "mit_0123456789abcdef",
    "description": "Roll paymentservice back to 1.4.0.",
    "steps": ["Roll back to 1.4.0"],
    "risk": "low",
    "verification_check": "The 5xx rate of paymentservice stays below 0.1 for two minutes.",
    "approval_status": "approved",
    "execution_mode": "executed",
    "operation": OPERATION,
    "execution": {
        "execution_id": "exe_0123456789abcdef",
        "outcome": "rolled_back",
        "replayed": False,
        "before_image": "demo/payment:1.5.0",
        "after_image": "demo/payment:1.4.0",
        "executed_at": "2026-11-02T12:00:00.000Z",
        "duration_ms": 5162,
    },
}
# Measured by the investigation, before the mitigation ran.
BEFORE = "ev_payment_error_rate"
NOW = "ev_00000000"


def verdict(passed: bool, *evidence: str) -> str:
    return json.dumps(
        {
            "action": "verify_mitigation",
            "passed": passed,
            "summary": "The 5xx rate fell to 0 after the rollback.",
            "supporting_evidence": list(evidence),
        }
    )


class Empty(Provider):
    async def collect(self, tool: str, arguments: dict[str, JsonValue]) -> ToolResult:
        self.calls.append(tool)
        return ToolResult(source="fixture", summary="no series", empty=True)


def verification(
    gateway: ScriptedGateway,
    provider: Provider | None = None,
    *,
    objective: str = "verify",
    mitigation: dict[str, Any] | None = MITIGATION,
) -> InvestigationResult:
    state = yaml.safe_load(STATE.read_text(encoding="utf-8")) | {"state": "verifying"}
    request = InvestigationRequest.model_validate(
        {
            "incident_id": state["incident_id"],
            "run_id": "run_a1b2c3d4e5",
            "objective": objective,
            "context": state,
            "authorized_capabilities": state["authorized_capabilities"],
            **({"mitigation": mitigation} if mitigation is not None else {}),
        }
    )
    return asyncio.run(investigate(request, gateway, provider or Provider(), Limits(), ids()))


def rejection(gateway: ScriptedGateway) -> str:
    """Why the model's previous reply was rejected, as the last request tells it."""
    return gateway.calls[-1]["input"].rsplit("Your previous reply was rejected: ", 1)[-1]


@pytest.mark.parametrize(
    ("objective", "mitigation"),
    [("verify", None), ("investigate", MITIGATION)],
    ids=["verify-without", "investigate-with"],
)
def test_a_verification_and_only_a_verification_carries_its_mitigation(
    objective: str, mitigation: dict[str, Any] | None
) -> None:
    with pytest.raises(ValidationError, match="only a verification carries the mitigation"):
        verification(ScriptedGateway(), objective=objective, mitigation=mitigation)


def test_the_model_is_told_what_ran_and_what_must_hold_now() -> None:
    gateway = ScriptedGateway(TOOL, verdict(True, NOW))
    verification(gateway)

    prompt = gateway.calls[0]["input"]
    state = json.loads(prompt.split("State: ", 1)[1].splitlines()[0])
    assert (state["objective"], state["incident"]["state"]) == ("verify", "verifying")
    assert state["mitigation"]["verification_check"] == MITIGATION["verification_check"]
    assert state["mitigation"]["operation"] == OPERATION
    ran = state["mitigation"]["execution"]
    assert (ran["outcome"], ran["before_image"], ran["after_image"]) == (
        "rolled_back",
        "demo/payment:1.5.0",
        "demo/payment:1.4.0",
    )
    assert '{"action": "verify_mitigation"' in prompt
    for outcome in ("propose_hypothesis", "propose_mitigation", "conclude"):
        assert f'"action": "{outcome}"' not in prompt


@pytest.mark.parametrize(
    "wrong",
    [
        hypothesis(NOW),
        json.dumps(
            {
                "action": "propose_mitigation",
                "description": "Roll back again.",
                "steps": ["Roll back"],
                "risk": "low",
                "verification_check": "5xx below 0.1",
            }
        ),
        json.dumps({"action": "conclude", "summary": "Recovered.", "supporting_evidence": [NOW]}),
    ],
    ids=["hypothesis", "mitigation", "conclusion"],
)
def test_a_verification_ends_only_with_a_verdict_or_a_human(wrong: str) -> None:
    gateway = ScriptedGateway(TOOL, wrong, wrong)
    result = verification(gateway)

    assert result.status == "invalid_output"
    assert rejection(gateway).startswith(
        "a verification ends only with verify_mitigation or request_human"
    )


def test_an_investigation_never_ends_with_a_verdict() -> None:
    gateway = ScriptedGateway(TOOL, verdict(True, NOW), verdict(True, NOW))
    result = run(gateway)

    assert result.status == "invalid_output"
    assert rejection(gateway).startswith("verify_mitigation is only valid in a verification")


@pytest.mark.parametrize(
    ("cited", "provider"), [(BEFORE, Provider()), (NOW, Empty())], ids=["before", "empty"]
)
def test_a_verdict_must_cite_what_this_verification_measured(
    cited: str, provider: Provider
) -> None:
    gateway = ScriptedGateway(TOOL, verdict(True, cited), verdict(True, cited))
    result = verification(gateway, provider)

    assert result.status == "invalid_output"
    assert rejection(gateway).startswith("cite evidence measured in this verification")


@pytest.mark.parametrize("passed", [True, False])
def test_a_measured_verdict_completes_with_what_was_measured(passed: bool) -> None:
    gateway, provider = ScriptedGateway(TOOL, verdict(passed, NOW, BEFORE)), Provider()
    result = verification(gateway, provider)

    assert result.status == "completed" and result.outcome is not None
    assert result.outcome.model_dump() == json.loads(verdict(passed, NOW, BEFORE))
    assert provider.calls == ["query_prometheus"]
    assert [(item.evidence_id, item.source) for item in result.evidence] == [(NOW, "fixture")]
