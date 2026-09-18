"""Investigator loop against a scripted gateway and provider (issue #185, CA1 to CA5)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Callable, Mapping
from itertools import count
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml
from pydantic import JsonValue

from sre_agent.investigator.contract import InvestigationRequest, InvestigationResult, Limits
from sre_agent.investigator.loop import investigate
from sre_agent.investigator.ports import EvidenceUnavailable, GatewayError, GatewayReply, ToolResult

STATE = (
    Path(__file__).parents[1] / "agent/fixtures/incidents/otel-payment-failure/declared-state.yaml"
)
TOOL = '{"action": "use_tool", "tool": "query_prometheus", "arguments": {"window": "2m"}}'
TRANSIENT = GatewayError("transient", 503)


def hypothesis(*evidence: str) -> str:
    return json.dumps(
        {
            "action": "propose_hypothesis",
            "statement": "Checkout cannot reach payment.",
            "confidence": "high",
            "supporting_evidence": list(evidence),
        }
    )


HYPOTHESIS = hypothesis("ev_payment_error_rate")


class ScriptedGateway:
    def __init__(self, *replies: str | GatewayError) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, str]] = []

    async def respond(self, **request: str) -> GatewayReply:
        self.calls.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, GatewayError):
            raise reply
        return GatewayReply(text=reply, request_id=uuid4())


class Provider:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[str] = []

    async def collect(self, tool: str, arguments: Mapping[str, JsonValue]) -> ToolResult:
        self.calls.append(tool)
        if self.failure:
            raise self.failure
        return ToolResult(source="fixture", summary="checkout error calls rose from 0 to 12")


def ids() -> Callable[[str], str]:
    counters: defaultdict[str, count[int]] = defaultdict(count)
    return lambda prefix: f"{prefix}_{next(counters[prefix]):08d}"


def run(gateway: ScriptedGateway, provider: Provider | None = None) -> InvestigationResult:
    state = yaml.safe_load(STATE.read_text(encoding="utf-8"))
    request = InvestigationRequest.model_validate(
        {
            "incident_id": state["incident_id"],
            "run_id": "run_a1b2c3d4e5",
            "objective": "investigate",
            "context": state,
            "authorized_capabilities": state["authorized_capabilities"],
        }
    )
    return asyncio.run(investigate(request, gateway, provider or Provider(), Limits(), ids()))


def test_a_tool_then_a_cited_hypothesis_completes() -> None:
    gateway, provider = ScriptedGateway(TOOL, hypothesis("ev_00000000")), Provider()
    result = run(gateway, provider)

    assert result.status == "completed" and result.outcome is not None
    assert result.outcome.model_dump() == json.loads(hypothesis("ev_00000000"))
    assert provider.calls == ["query_prometheus"]
    assert [(item.evidence_id, item.source) for item in result.evidence] == [
        ("ev_00000000", "fixture")
    ]
    assert [call["task_id"] for call in gateway.calls] == ["task_00000000", "task_00000001"]
    assert [turn.task_id for turn in result.turns] == ["task_00000000", "task_00000001"]
    assert all(set(call) == {"input", "incident_id", "run_id", "task_id"} for call in gateway.calls)


@pytest.mark.parametrize(
    ("replies", "status", "turns"),
    [
        (["not json", "still not json"], "invalid_output", 2),
        ([hypothesis("ev_invented")] * 2, "invalid_output", 2),
        (["not json", HYPOTHESIS], "completed", 2),
        (['{"action": "use_tool", "tool": "query_elasticsearch"}'], "denied", 1),
        ([GatewayError("denied", 403)], "denied", 0),
        ([GatewayError("rejected", 422)], "needs_human", 0),
        ([TRANSIENT, TRANSIENT], "upstream_unavailable", 0),
        (['{"action": "request_human", "reason": "No metrics yet."}'], "needs_human", 1),
    ],
)
def test_each_path_ends_with_its_status_and_no_tool(
    replies: list[Any], status: str, turns: int
) -> None:
    gateway, provider = ScriptedGateway(*replies), Provider()
    result = run(gateway, provider)

    assert (result.status, len(result.turns), provider.calls) == (status, turns, [])
    assert gateway.replies == []


def test_the_retry_explains_the_rejection_to_the_model() -> None:
    gateway = ScriptedGateway("not json", HYPOTHESIS)
    run(gateway)

    assert "previous reply was rejected" not in gateway.calls[0]["input"]
    assert "previous reply was rejected: output: Invalid JSON" in gateway.calls[1]["input"]


def test_a_transient_failure_repeats_the_same_turn() -> None:
    gateway = ScriptedGateway(TRANSIENT, HYPOTHESIS)
    result = run(gateway)

    assert result.status == "completed" and len(result.turns) == 1
    assert [call["task_id"] for call in gateway.calls] == ["task_00000000"] * 2


def test_the_step_budget_ends_the_run() -> None:
    gateway, provider = ScriptedGateway(*[TOOL] * 6), Provider()
    result = run(gateway, provider)

    assert (result.status, result.detail) == ("max_steps", "step budget of 6 exhausted")
    assert len(result.turns) == len(provider.calls) == 6 and gateway.replies == []


def test_a_failing_tool_ends_as_upstream_unavailable() -> None:
    result = run(ScriptedGateway(TOOL), Provider(EvidenceUnavailable()))

    assert (result.status, result.detail) == (
        "upstream_unavailable",
        "tool failed: query_prometheus",
    )
