#!/usr/bin/env python3
"""API of the store-topology BoK E2E (#718): the real application, with the model and Grafana
MCP scripted. The model searches the store topology when the run offers it, reads payment's
logs, then proposes a hypothesis citing both and a mitigation for it."""

import json
import re
import secrets

import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

STATE = re.compile(r"^State: (.*)$", re.MULTILINE)
COLLECTION = "otel-demo-store@1.0.0"
LOGS = {"datasource_uid": "webstore-logs", "index": "otel-logs-*",
        "query": 'resource.service.name:"payment"', "start_time": "now-15m", "end_time": "now",
        "limit": 10}  # fmt: skip


def decide(state: dict) -> dict:
    incident, collected = state["incident"], state["collected_evidence"]
    if incident["hypotheses"]:
        return {
            "action": "propose_mitigation",
            "description": "Volver el flag paymentFailure de flagd a off.",
            "steps": ["Poner paymentFailure en off en flagd."],
            "risk": "low",
            "verification_check": "Las llamadas con error de checkout y payment vuelven a cero.",
            "based_on_hypothesis": incident["hypotheses"][-1]["hypothesis_id"],
        }
    tools = {item["tool"] for item in [*collected, *state["tool_calls"]]}
    if COLLECTION in state.get("authorized_bok_collections", []) and "bok.search" not in tools:
        query = "checkout payment feature flag"
        return {"action": "search_bok", "collection": COLLECTION, "query": query}
    if "query_elasticsearch" not in tools:
        return {"action": "use_tool", "tool": "query_elasticsearch", "arguments": LOGS}
    return {
        "action": "propose_hypothesis",
        "statement": "Causa: el flag paymentFailure hace fallar los cobros en payment. Mecanismo: "
        "checkout llama a payment en cada pedido y su PlaceOrder falla con el cobro. Lo refutaría "
        "que payment no registre errores mientras checkout falla.",
        "confidence": "medium",
        "supporting_evidence": [item["evidence_id"] for item in collected],
    }


class ScriptedModel:
    async def create(self, request: ProviderRequest) -> ProviderResult:
        reply = decide(json.loads(STATE.findall(request.input)[-1]))
        return ProviderResult(
            response_id=f"resp_{secrets.token_hex(8)}",
            model=request.model,
            text=json.dumps(reply),
            provider=request.provider,
        )


class ScriptedMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        body = "Payment request failed. Invalid token. demo.user_context.loyalty_level=gold"
        document = {"resource": {"service": {"name": "payment"}}, "body": body}
        return {"total": 2, "documents": [document, document]}


if __name__ == "__main__":
    application = create_application(llm_provider=ScriptedModel(), mcp_client=ScriptedMCP())
    uvicorn.run(application, host="0.0.0.0", port=8000)
