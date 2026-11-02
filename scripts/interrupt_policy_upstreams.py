#!/usr/bin/env python3
"""API of the interrupt-policy E2E (#771): the real application, with the model and Grafana MCP
scripted. An alert whose summary carries `[e2e:broken]` is investigated to a rollback proposal
(a measured query, a hypothesis, then the mitigation); any other alert concludes. A summary with
`[e2e:spike]` holds each model answer SPIKE_DELAY_SECONDS, so the spike's `resolved` delivery
lands before its investigation ends, as a short spike does in production."""

import asyncio
import json
import os
import re
import secrets

import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

STATE = re.compile(r"^State: (.*)$", re.MULTILINE)
QUERY = {
    "datasource_uid": "webstore-metrics",
    "query_type": "instant",
    "expr": "sum by (service_name) (increase(http_server_errors_total[5m]))",
    "end_time": "now",
}


def decide(state: dict) -> dict:
    incident, collected = state["incident"], state["collected_evidence"]
    if "[e2e:broken]" not in incident["alert"]["summary"]:
        return {"action": "conclude", "summary": "El servicio volvió a responder sin errores."}
    if incident["hypotheses"]:
        return {
            "action": "propose_mitigation",
            "description": "Revertir el último despliegue de sre-checkout.",
            "steps": ["Hacer rollback de sre-checkout a la versión anterior."],
            "risk": "low",
            "verification_check": "Los errores 5xx de sre-checkout vuelven a cero.",
            "based_on_hypothesis": incident["hypotheses"][-1]["hypothesis_id"],
        }
    if not collected:
        return {"action": "use_tool", "tool": "query_prometheus", "arguments": QUERY}
    cited = [item["evidence_id"] for item in collected]
    return {
        "action": "propose_hypothesis",
        "statement": "El último despliegue de sre-checkout devuelve errores 5xx.",
        "confidence": "high",
        "supporting_evidence": cited,
        "verdicts": {
            evidence: {"verdict": "supports", "finding": "42 errores 5xx desde el despliegue."}
            for evidence in cited
        },
    }


class ScriptedModel:
    async def create(self, request: ProviderRequest) -> ProviderResult:
        state = json.loads(STATE.findall(request.input)[-1])
        if "[e2e:spike]" in state["incident"]["alert"]["summary"]:
            await asyncio.sleep(float(os.environ.get("SPIKE_DELAY_SECONDS") or 8))
        return ProviderResult(
            response_id=f"resp_{secrets.token_hex(8)}",
            model=request.model,
            text=json.dumps(decide(state)),
            provider=request.provider,
        )


class ScriptedMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if tool_name != "query_prometheus":
            return {"total": 0, "documents": []}
        sample = {"metric": {"service_name": "sre-checkout"}, "value": [1761800000, "42"]}
        return {"resultType": "vector", "result": [sample]}


if __name__ == "__main__":
    application = create_application(llm_provider=ScriptedModel(), mcp_client=ScriptedMCP())
    uvicorn.run(application, host="0.0.0.0", port=8000)
