"""List the tools Grafana MCP exposes and fail if any of them writes (issue #186, CA5).

Runs in a throwaway container on the demo network, reading the caller token from
.demo-state/grafana-mcp.env through --env-file; the token is never printed.
"""

import json
import os
import sys
import urllib.request

URL = "http://grafana-mcp:8000/mcp"
WRITE_VERBS = ("create", "update", "delete", "add_", "patch", "put_", "set_")
session: dict[str, str] = {}


def rpc(method: str, params: dict | None = None, call_id: int | None = None) -> dict | None:
    body: dict = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if call_id is not None:
        body["id"] = call_id
    headers = {
        "Authorization": f"Bearer {os.environ['MCP_GRAFANA_SERVER_TOKEN']}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **session,
    }
    request = urllib.request.Request(URL, json.dumps(body).encode(), headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.headers.get("Mcp-Session-Id"):
            session["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
        text = response.read().decode()
    data = [line[5:] for line in text.splitlines() if line.startswith("data:")]
    payload = data[0] if data else text
    return json.loads(payload) if payload.strip() else None


client = {"name": "demo-mcp-tools", "version": "1"}
rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": client}, 1)
rpc("notifications/initialized")
tools = sorted(tool["name"] for tool in rpc("tools/list", call_id=2)["result"]["tools"])
writers = [name for name in tools if any(verb in name for verb in WRITE_VERBS)]
print(f"{len(tools)} tools: {', '.join(tools)}")
sources = rpc("tools/call", {"name": "list_datasources", "arguments": {}}, 3)["result"]
print("list_datasources:", "error" if sources.get("isError") else "answered through Grafana")
print(f"FAIL write tools exposed: {writers}" if writers else "OK no tool writes")
sys.exit(1 if writers or sources.get("isError") else 0)
