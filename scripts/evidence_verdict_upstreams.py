#!/usr/bin/env python3
"""API of the evidence-verdict E2E (#707): the real application, with the model and Grafana MCP
scripted. The model plays the scenario its alert names and says every evidence supports its
hypothesis; Prometheus answers one series per service, Elasticsearch no documents."""

import json
import os
import re
import secrets

import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

STATE = re.compile(r"^State: (.*)$", re.MULTILINE)
ERRORS = 'increase(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[2m])'
TOOLS = {
    "query_prometheus": {"datasource_uid": "webstore-metrics", "query_type": "instant",
                         "expr": f"sum by (service_name) ({ERRORS})", "end_time": "now"},
    "query_elasticsearch": {"datasource_uid": "webstore-logs", "index": "otel-logs-*",
                            "query": 'resource.service.name:"payment"', "start_time": "now-15m",
                            "end_time": "now", "limit": 10},
}  # fmt: skip
FINDINGS = {
    "query_prometheus": "checkout registra 12 llamadas con error y payment ninguna.",
    "query_elasticsearch": "Los logs de payment muestran el cobro rechazado.",
}


def decide(state: dict) -> dict:
    incident, collected = state["incident"], state["collected_evidence"]
    if incident["hypotheses"]:
        return {
            "action": "propose_mitigation",
            "description": "Reiniciar payment para restablecer los cobros.",
            "steps": ["Reiniciar el servicio payment."],
            "risk": "low",
            "verification_check": "Las llamadas con error de checkout vuelven a cero.",
            "based_on_hypothesis": incident["hypotheses"][-1]["hypothesis_id"],
        }
    wanted = list(TOOLS)[1:] if "[e2e:logs-only]" in incident["alert"]["summary"] else TOOLS
    for tool in wanted:
        if tool not in {item["tool"] for item in collected}:
            return {"action": "use_tool", "tool": tool, "arguments": TOOLS[tool]}
    return {
        "action": "propose_hypothesis",
        "statement": "checkout falla al cobrar porque payment no responde.",
        "confidence": "medium",
        "supporting_evidence": [item["evidence_id"] for item in collected],
        "verdicts": {
            item["evidence_id"]: {"verdict": "supports", "finding": FINDINGS[item["tool"]]}
            for item in collected
        },
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
        if tool_name != "query_prometheus":
            return {"total": 0, "documents": []}
        series = {"checkout": "12", "frontend": "24", "payment": "0"}
        return {
            "resultType": "vector",
            "result": [
                {"metric": {"service_name": name}, "value": [1761800000, value]}
                for name, value in series.items()
            ],
        }


if __name__ == "__main__":
    # E2E_REAL_MODEL=1 keeps the gateway's own provider (OPENROUTER_API_KEY) for acceptance.
    model = None if os.environ.get("E2E_REAL_MODEL") == "1" else ScriptedModel()
    application = create_application(llm_provider=model, mcp_client=ScriptedMCP())
    uvicorn.run(application, host="0.0.0.0", port=8000)
