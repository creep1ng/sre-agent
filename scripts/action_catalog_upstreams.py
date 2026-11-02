#!/usr/bin/env python3
"""API of the action catalog E2E (#870): the incident page journeys' scripted model and Grafana
MCP (scripts/incident_console_upstreams.py), whose proposal names the rollback the executor
offers for the incident's service, so approving it runs on the real deploy-executor.
"""

import uvicorn

import incident_console_upstreams as upstreams
from sre_agent.application import create_application

scripted = upstreams.decide


def decide(state: dict, prompt: str) -> dict:
    action = scripted(state, prompt)
    offered = state.get("service_operations")
    if action["action"] == "propose_mitigation" and offered:
        service = offered["service"]
        action["description"] = f"Volver `{service}` a la `1.4.0`"
        action["operation"] = {
            "service": service,
            "operation": "deployment.rollback",
            "parameters": {"to_tag": "1.4.0"},
        }
    return action


upstreams.decide = decide

if __name__ == "__main__":
    application = create_application(
        llm_provider=upstreams.ScriptedModel(), mcp_client=upstreams.ScriptedMCP()
    )
    uvicorn.run(application, host="0.0.0.0", port=8000)
