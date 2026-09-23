"""Gateway client and fixture provider of the investigator harness (issue #185, CA5, CA6)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from sre_agent.investigator.client import GatewayClient, GatewaySettings
from sre_agent.investigator.contract import InvestigationRequest
from sre_agent.investigator.fixtures import FixtureEvidenceProvider
from sre_agent.investigator.loop import investigate
from sre_agent.investigator.ports import EvidenceUnavailable, GatewayError
from sre_agent.release import CONTRACT_VERSION

ROOT = Path(__file__).parents[1]
RELEASE = ROOT / "schemas/releases" / CONTRACT_VERSION
REPLY = json.loads((RELEASE / "examples/responses/completed-response.example.json").read_text())
ENVIRONMENT = {
    "INVESTIGATOR_GATEWAY_URL": "http://api:8000",
    "INVESTIGATOR_GATEWAY_API_KEY": "sre_test_gateway_key",
    "INVESTIGATOR_MODEL_ALIAS": "triage-agent",
    "OPENROUTER_API_KEY": "sk-or-provider-secret",
}
CORRELATION = {"incident_id": "inc-otel-payment-failure", "run_id": "run_a1b2c3d4e5"}
Handler = Callable[[httpx.Request], httpx.Response]


def client(handler: Handler, environment: dict[str, str] = ENVIRONMENT) -> GatewayClient:
    transport = httpx.MockTransport(handler)
    settings = GatewaySettings.from_environment(environment)
    return GatewayClient(settings, httpx.AsyncClient(transport=transport))


def respond(handler: Handler, environment: dict[str, str] = ENVIRONMENT) -> Any:
    gateway = client(handler, environment)
    return asyncio.run(gateway.respond(input="Next action?", task_id="task_a1b2", **CORRELATION))


def replying(*texts: str) -> Handler:
    queue = list(texts)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(json.dumps(REPLY))
        body["output"][0]["content"][0]["text"] = queue.pop(0)
        return httpx.Response(200, json=body)

    return handler


def test_the_request_follows_the_contract_and_carries_only_gateway_configuration() -> None:
    seen: list[httpx.Request] = []
    reply = respond(lambda request: seen.append(request) or httpx.Response(200, json=REPLY))
    body = json.loads(seen[0].content)
    schema = json.loads((RELEASE / "json-schema/http/responses-request.schema.json").read_text())

    Draft202012Validator(schema).validate(body)
    assert body == {"model": "triage-agent", "input": "Next action?", "task_id": "task_a1b2"} | (
        CORRELATION
    )
    assert str(seen[0].url) == "http://api:8000/v1/responses"
    assert seen[0].headers["authorization"] == "Bearer sre_test_gateway_key"
    assert "sk-or-provider-secret" not in str(seen[0].headers) + seen[0].content.decode()
    assert reply.text == REPLY["output"][0]["content"][0]["text"]
    assert str(reply.request_id) == REPLY["request_id"]


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "denied"), (403, "denied"), (422, "rejected"), (500, "transient"), (504, "transient")],
)
def test_gateway_statuses_map_to_error_kinds(status: int, kind: str) -> None:
    with pytest.raises(GatewayError) as raised:
        respond(lambda request: httpx.Response(status, json={"error": {"code": "x"}}))

    assert (raised.value.kind, raised.value.status) == (kind, status)


def test_network_errors_are_transient_and_foreign_bodies_are_rejected() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(GatewayError) as network:
        respond(unreachable)
    with pytest.raises(GatewayError) as foreign:
        respond(lambda request: httpx.Response(200, json={"status": "completed"}))

    assert (network.value.kind, foreign.value.kind, foreign.value.status) == (
        "transient",
        "rejected",
        200,
    )


def test_settings_read_only_the_three_gateway_variables() -> None:
    settings = GatewaySettings.from_environment(ENVIRONMENT)
    without_alias = {k: v for k, v in ENVIRONMENT.items() if k != "INVESTIGATOR_MODEL_ALIAS"}

    assert set(GatewaySettings.model_fields) == {
        "base_url",
        "api_key",
        "model_alias",
        "timeout_seconds",
    }
    assert "sre_test_gateway_key" not in repr(settings)
    with pytest.raises(ValueError, match="INVESTIGATOR_MODEL_ALIAS"):
        GatewaySettings.from_environment(without_alias)
    with pytest.raises(ValidationError):
        GatewaySettings.from_environment(ENVIRONMENT | {"INVESTIGATOR_MODEL_ALIAS": "Bad_Alias"})


def test_a_new_base_url_or_alias_is_configuration_only() -> None:
    seen: list[httpx.Request] = []
    changed = ENVIRONMENT | {
        "INVESTIGATOR_GATEWAY_URL": "https://gateway.internal/api/",
        "INVESTIGATOR_MODEL_ALIAS": "remediation-agent",
    }
    respond(lambda request: seen.append(request) or httpx.Response(200, json=REPLY), changed)

    assert str(seen[0].url) == "https://gateway.internal/api/v1/responses"
    assert json.loads(seen[0].content)["model"] == "remediation-agent"


def test_fixture_evidence_is_labeled_and_unknown_tools_are_unavailable() -> None:
    provider = FixtureEvidenceProvider()
    result = asyncio.run(provider.collect("query_prometheus", {}))

    assert (result.source, result.datasource_uid) == ("fixture", "webstore-metrics")
    with pytest.raises(EvidenceUnavailable):
        asyncio.run(provider.collect("query_jaeger", {}))


def request() -> InvestigationRequest:
    path = ROOT / "agent/fixtures/incidents/otel-payment-failure/declared-state.yaml"
    state = yaml.safe_load(path.read_text(encoding="utf-8"))
    return InvestigationRequest.model_validate(
        CORRELATION
        | {
            "objective": "investigate",
            "context": state,
            "authorized_capabilities": state["authorized_capabilities"],
        }
    )


def test_the_loop_runs_over_http_with_labeled_fixture_evidence() -> None:
    tool = '{"action": "use_tool", "tool": "query_prometheus", "arguments": {}}'
    hypothesis = json.dumps(
        {
            "action": "propose_hypothesis",
            "statement": "Checkout cannot reach payment.",
            "confidence": "high",
            "supporting_evidence": ["ev_payment_error_rate"],
        }
    )
    gateway = client(replying(tool, hypothesis))
    result = asyncio.run(investigate(request(), gateway, FixtureEvidenceProvider()))

    assert result.status == "completed" and len(result.turns) == 2
    assert [(item.source, str(item.request_id)) for item in result.evidence] == [
        ("fixture", REPLY["request_id"])
    ]


def test_a_gateway_denial_blocks_the_run_after_one_call() -> None:
    calls: list[httpx.Request] = []
    gateway = client(lambda request: calls.append(request) or httpx.Response(403, json={}))
    result = asyncio.run(investigate(request(), gateway, FixtureEvidenceProvider()))

    assert (result.status, result.outcome, result.detail) == (
        "denied",
        None,
        "gateway denied (403)",
    )
    assert [str(call.url) for call in calls] == ["http://api:8000/v1/responses"]
