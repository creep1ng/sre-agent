#!/usr/bin/env python3
"""API of the new console's investigation journeys (#708): the real application, with the model
and Grafana MCP scripted. Each model reply waits STEP_SECONDS, so the console sees the run work.

The model reads the metrics, the logs and, when it is offered, the service's recent changes,
then proposes a hypothesis citing all of them (with a verdict each when the prompt asks for
verdicts) and a mitigation. An alert whose summary carries `[e2e:falla]` gets two replies that
are not JSON first, so its first investigation ends with `investigation_invalid_output` and a
human retry succeeds.
"""

import asyncio
import json
import os
import re
import secrets
from collections import Counter

import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

STEP_SECONDS = float(os.environ.get("STEP_SECONDS", "2"))
STATE = re.compile(r"^State: (.*)$", re.MULTILINE)
CHANGES = "midnight_recent_changes"
ERRORS = 'increase(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[2m])'
FINDINGS = {
    "query_prometheus": "checkout registra 12 llamadas con error y payment ninguna.",
    "query_elasticsearch": "Los logs de checkout muestran el cobro rechazado por payment.",
    CHANGES: "checkout desplegó la versión 1.5.0 minutos antes de la alerta.",
}
failures: Counter[str] = Counter()


def arguments(tool: str, service: str) -> dict:
    if tool == "query_prometheus":
        return {"datasource_uid": "webstore-metrics", "query_type": "instant", "end_time": "now",
                "expr": f"sum by (service_name) ({ERRORS})"}  # fmt: skip
    if tool == "query_elasticsearch":
        return {"datasource_uid": "webstore-logs", "index": "otel-logs-*", "limit": 10,
                "query": f'resource.service.name:"{service}"', "start_time": "now-15m",
                "end_time": "now"}  # fmt: skip
    return {"service": service}


def decide(state: dict, prompt: str) -> dict:
    incident, collected = state["incident"], state["collected_evidence"]
    if incident["hypotheses"]:
        return {
            "action": "propose_mitigation",
            "description": "Revertir checkout a la versión anterior a 1.5.0.",
            "steps": ["Revertir el despliegue de checkout 1.5.0.", "Vigilar los errores de cobro."],
            "risk": "low",
            "verification_check": "Las llamadas con error de checkout vuelven a cero.",
            "based_on_hypothesis": incident["hypotheses"][-1]["hypothesis_id"],
        }
    tools = ["query_prometheus", "query_elasticsearch"] + ([CHANGES] if CHANGES in prompt else [])
    for tool in tools:
        if tool not in {item["tool"] for item in collected}:
            service = incident["alert"]["service"]
            return {"action": "use_tool", "tool": tool, "arguments": arguments(tool, service)}
    reply = {
        "action": "propose_hypothesis",
        "statement": "El despliegue de checkout 1.5.0 rompió los cobros contra payment.",
        "confidence": "medium",
        "supporting_evidence": [item["evidence_id"] for item in collected],
    }
    if "verdicts" in prompt:
        reply["verdicts"] = {
            item["evidence_id"]: {"verdict": "supports", "finding": FINDINGS[item["tool"]]}
            for item in collected
        }
    return reply


class ScriptedModel:
    async def create(self, request: ProviderRequest) -> ProviderResult:
        await asyncio.sleep(STEP_SECONDS)
        state = json.loads(STATE.findall(request.input)[-1])
        incident = state["incident"]
        text = json.dumps(decide(state, request.input))
        if "[e2e:falla]" in incident["alert"]["summary"] and failures[incident["incident_id"]] < 2:
            failures[incident["incident_id"]] += 1
            text = "Esta respuesta no es JSON."
        return ProviderResult(
            response_id=f"resp_{secrets.token_hex(8)}",
            model=request.model,
            text=text,
            provider=request.provider,
        )


class ScriptedMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if tool_name == "query_elasticsearch":
            body = "checkout: payment rejected the charge (HTTP 503)"
            return {"total": 3, "documents": [{"_source": {"body": body}}], "warnings": []}
        series = {"checkout": "12", "frontend": "24", "payment": "0"}
        return {
            "resultType": "vector",
            "result": [
                {"metric": {"service_name": name}, "value": [1761800000, value]}
                for name, value in series.items()
            ],
        }


if __name__ == "__main__":
    application = create_application(llm_provider=ScriptedModel(), mcp_client=ScriptedMCP())
    uvicorn.run(application, host="0.0.0.0", port=8000)
