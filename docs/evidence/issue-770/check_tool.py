"""The investigator's change tool through the harness identity (#770 evidence).

Runs in the compose `seed` container (the API image) with INCIDENT_HARNESS_API_KEY from compose:
discovery offers midnight_recent_changes when this probe of GET /v1/changes answers 200 (the full
discovery also needs Grafana MCP, compose.mcp.yaml, absent from this stack), and collect()
returns the evidence a hypothesis cites, with the request_id of the read.
"""

import asyncio
import os

from sre_agent.investigator.client import (
    CHANGES_TOOL,
    GatewaySettings,
    MCPGatewayClient,
)


async def main():
    settings = GatewaySettings(
        base_url="http://api:8000",
        api_key=os.environ["INCIDENT_HARNESS_API_KEY"],
        model_alias="remediation-agent",
    )
    client = MCPGatewayClient(settings)
    probe = await client._send("GET", "/v1/changes", params={"limit": 1})  # discover()'s probe
    print("change.read probe as incident-harness:", probe.status_code)
    result = await client.collect(CHANGES_TOOL, {"service": "sre-checkout"})
    print("source:", result.source)
    print("query:", result.query)
    print("request_id:", result.request_id)
    print("summary:", result.summary)


asyncio.run(main())
