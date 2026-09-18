"""Deterministic scenarios of the investigator harness against a demo gateway (issue #185).

A local stub serves `POST /v1/responses` with the contract's shapes and scripted model
answers; the harness reaches it over real HTTP with its own client. Evidence comes from the
fixture provider. Nothing here calls a provider, an MCP server or the incident store.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import yaml
from jsonschema import Draft202012Validator

from sre_agent.investigator.client import GatewayClient, GatewaySettings
from sre_agent.investigator.contract import InvestigationRequest
from sre_agent.investigator.fixtures import FixtureEvidenceProvider
from sre_agent.investigator.loop import investigate
from sre_agent.release import CONTRACT_VERSION

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "agent/fixtures/incidents/otel-payment-failure/declared-state.yaml"
RELEASE = ROOT / "schemas/releases" / CONTRACT_VERSION
ALLOWED, RESTRICTED = "demo-incident-harness-key", "demo-restricted-harness-key"
PROVIDER_SECRET = "sk-or-demo-provider-secret"
TOOL = '{"action": "use_tool", "tool": "query_prometheus", "arguments": {"window": "2m"}}'


def hypothesis(evidence: str) -> str:
    statement = "Checkout cannot reach payment: its charge calls fail before reaching payment."
    return json.dumps(
        {
            "action": "propose_hypothesis",
            "statement": statement,
            "confidence": "high",
            "supporting_evidence": [evidence],
        }
    )


@dataclass
class Scenario:
    name: str
    expected: str
    key: str
    replies: list[str | int] = field(default_factory=list)


SCENARIOS = [
    Scenario(
        "valid context and objective",
        "completed",
        ALLOWED,
        [TOOL, hypothesis("ev_payment_error_rate")],
    ),
    Scenario(
        "invalid output twice", "invalid_output", ALLOWED, ["Payment looks broken.", "Still prose."]
    ),
    Scenario(
        "citation outside the context", "invalid_output", ALLOWED, [hypothesis("ev_invented")] * 2
    ),
    Scenario(
        "tool not authorized",
        "denied",
        ALLOWED,
        ['{"action": "use_tool", "tool": "query_elasticsearch"}'],
    ),
    Scenario("gateway denial", "denied", RESTRICTED),
    Scenario("step budget exhausted", "max_steps", ALLOWED, [TOOL] * 6),
]


class StubGateway(ThreadingHTTPServer):
    def __init__(self, replies: list[str | int]) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.replies = list(replies)
        self.received: list[str] = []
        self.request_schema = json.loads(
            (RELEASE / "json-schema/http/responses-request.schema.json").read_text()
        )
        self.template = json.loads(
            (RELEASE / "examples/responses/completed-response.example.json").read_text()
        )


class _Handler(BaseHTTPRequestHandler):
    server: StubGateway

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        self.server.received.append(str(dict(self.headers)) + raw)
        body = json.loads(raw)
        if self.headers.get("Authorization") == f"Bearer {RESTRICTED}":
            return self._send(403, {"error": {"code": "resource_unavailable"}})
        if self.headers.get("Authorization") != f"Bearer {ALLOWED}":
            return self._send(401, {"error": {"code": "authentication_failed"}})
        if not Draft202012Validator(self.server.request_schema).is_valid(body):
            return self._send(422, {"error": {"code": "contract_validation_failed"}})
        reply = self.server.replies.pop(0)
        if isinstance(reply, int):
            return self._send(reply, {"error": {"code": "scripted"}})
        answer = json.loads(json.dumps(self.server.template))
        answer |= {"id": "resp_demo" + uuid.uuid4().hex[:12], "model": "demo/stub"}
        answer["request_id"] = str(uuid.uuid4())
        answer["output"][0]["content"][0]["text"] = reply
        answer["metadata"]["requested_model_alias"] = body["model"]
        return self._send(200, answer)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


class CountingProvider(FixtureEvidenceProvider):
    calls = 0

    async def collect(self, tool: str, arguments: Any) -> Any:
        self.calls += 1
        return await super().collect(tool, arguments)


async def run(scenario: Scenario, request: InvestigationRequest) -> dict[str, Any]:
    stub = StubGateway(scenario.replies)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    environment = {
        "INVESTIGATOR_GATEWAY_URL": f"http://127.0.0.1:{stub.server_address[1]}",
        "INVESTIGATOR_GATEWAY_API_KEY": scenario.key,
        "INVESTIGATOR_MODEL_ALIAS": "triage-agent",
        "OPENROUTER_API_KEY": PROVIDER_SECRET,
    }
    client = GatewayClient(
        GatewaySettings.from_environment(environment), httpx.AsyncClient(trust_env=False)
    )
    provider = CountingProvider()
    try:
        result = await investigate(request, client, provider)
    finally:
        await client.aclose()
        stub.shutdown()
        stub.server_close()
    received = "".join(stub.received)
    return {
        "scenario": scenario.name,
        "expected": scenario.expected,
        "status": result.status,
        "turns": len(result.turns),
        "gateway_calls": len(stub.received),
        "tool_calls": provider.calls,
        "evidence_sources": sorted({item.source for item in result.evidence}),
        "detail": result.detail,
        "provider_secret_sent": PROVIDER_SECRET in received,
        "turn_id_sent": '"turn_id"' in received,
    }


def main() -> int:
    before = hashlib.sha256(STATE.read_bytes()).hexdigest()
    state = yaml.safe_load(STATE.read_text(encoding="utf-8"))
    request = InvestigationRequest.model_validate(
        {
            "incident_id": state["incident_id"],
            "run_id": "run_demo0001",
            "objective": "investigate",
            "context": state,
            "authorized_capabilities": state["authorized_capabilities"],
        }
    )
    rows = [asyncio.run(run(scenario, request)) for scenario in SCENARIOS]
    for row in rows:
        print(json.dumps(row))
    unchanged = hashlib.sha256(STATE.read_bytes()).hexdigest() == before
    print(json.dumps({"incident_state_unchanged": unchanged, "gateway": "demo stub"}))
    passed = unchanged and all(
        row["status"] == row["expected"]
        and not row["provider_secret_sent"]
        and not row["turn_id_sent"]
        for row in rows
    )
    print("RESULT: " + ("all scenarios as expected" if passed else "MISMATCH"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
