#!/usr/bin/env python3
"""API of the close-the-loop journey (#723): scripts/incident_console_upstreams.py's model and
MCP, plus the verification. Asked to verify, the model queries sre-checkout's 5xx since the
execution and passes only when none were measured. The MCP answers that query with ORDERS real
orders to sre-checkout, so the verdict follows the release the deploy-executor left running. Told
that a mitigation ran and failed (#710), the model proposes the rollback instead of the restart."""

import asyncio
import json
import time
import urllib.request

import incident_console_upstreams as upstreams
import uvicorn

from sre_agent.application import create_application

CHECKOUT = "http://sre-checkout:8080/checkout"
ORDERS = 20
METRIC = "checkout_requests_total"
# The 5xx of demo/grafana/alerting/midnight.yaml's sre-checkout rule, over the window asked for.
ERRORS = (
    'sum(increase(%s{service_namespace="sre-agent",service_name="sre-checkout",'
    'http_response_status_code=~"5.."}[%ds]))'
)
CHECK = "Los pedidos de sre-checkout dejan de fallar con 500."
scripted = upstreams.decide


def verify(state: dict) -> dict:
    measured = [item for item in state["collected_evidence"] if not item.get("empty")]
    if not measured:
        # Only what ran since the execution: the prompt gives the seconds (#1009).
        window = max(int(state.get("seconds_since_execution") or 1), 1)
        query = {"datasource_uid": "webstore-metrics", "query_type": "instant", "end_time": "now",
                 "expr": ERRORS % (METRIC, window)}  # fmt: skip
        return {"action": "use_tool", "tool": "query_prometheus", "arguments": query}
    failed = [
        float(sample["value"][1])
        for item in measured
        for sample in json.loads(item["summary"]).get("result", [])
    ]
    return {
        "action": "verify_mitigation",
        "passed": not any(failed),
        "summary": f"sre-checkout: {max(failed, default=0):g} de {ORDERS} pedidos fallaron.",
        "supporting_evidence": [item["evidence_id"] for item in measured],
    }


def decide(state: dict, prompt: str) -> dict:
    if state["objective"] == "verify":
        return verify(state)
    action = scripted(state, prompt)
    if action["action"] != "propose_mitigation" or "operation" not in action:
        return action
    service = action["operation"]["service"]
    if state.get("failed_mitigations"):
        action["operation"] = {"service": service, "operation": "deployment.rollback",
                               "parameters": {"to_tag": "1.4.0"}}  # fmt: skip
    restart = action["operation"]["operation"] == "deployment.restart"
    plan = f"Reiniciar `{service}`" if restart else f"Volver `{service}` a la `1.4.0`"
    return action | {"description": plan, "steps": [plan + "."], "verification_check": CHECK}


def measure() -> dict:
    """ORDERS real orders to sre-checkout: an answer of 500 or none at all is a failed order."""
    failed = 0
    for _ in range(ORDERS):
        order = urllib.request.Request(CHECKOUT, b"{}", {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(order, timeout=2).close()
        except OSError:  # a 500 raises HTTPError, an OSError, as a refused connection does
            failed += 1
    sample = {"metric": {"service_name": "sre-checkout"}, "value": [time.time(), str(failed)]}
    return {"resultType": "vector", "result": [sample]}


class MeasuringMCP(upstreams.ScriptedMCP):
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if tool_name == "query_prometheus" and METRIC in str(arguments.get("expr")):
            return await asyncio.to_thread(measure)
        return await super().call_tool(tool_name, arguments)


def postmortem(prompt: str) -> str:
    """The scripted draft says a person verified; here Midnight did, with real orders."""
    measured = "Midnight verificó cada mitigación con pedidos reales a `sre-checkout`."
    return json.dumps(json.loads(drafted(prompt)) | {"how_we_verified": measured})


drafted = upstreams.postmortem
upstreams.decide, upstreams.postmortem = decide, postmortem

if __name__ == "__main__":
    application = create_application(
        llm_provider=upstreams.ScriptedModel(), mcp_client=MeasuringMCP()
    )
    uvicorn.run(application, host="0.0.0.0", port=8000)
