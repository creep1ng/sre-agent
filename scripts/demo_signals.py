"""Read the injected failure's signals through Grafana MCP (issue #186, CA6).

Runs in a throwaway container on the demo network, with the caller token from
.demo-state/grafana-mcp.env passed through --env-file. For one time window it
prints error calls by service from the Prometheus span metrics, the checkout
logs of each order stage and the proxy access logs of checkout requests by
status from OpenSearch, and the trace_id of one order that never completed, which
opens the trace in Jaeger. The token is never printed; only counts, status codes
and trace ids leave the container.
"""

import json
import os
import re
import urllib.request
from collections import Counter
from datetime import UTC, datetime

URL = "http://grafana-mcp:8000/mcp"
WINDOW = os.environ.get("WINDOW", "2m")
LABEL = os.environ.get("LABEL", "")
SERVICES = "frontend-proxy|frontend|checkout|payment"
ERROR_CALLS = (
    "sum by (service_name) (increase(traces_span_metrics_calls_total"
    f'{{status_code="STATUS_CODE_ERROR", service_name=~"{SERVICES}"}}[{WINDOW}]))'
)
CHECKOUT_SPANS = (
    "sum by (span_name) (increase(traces_span_metrics_calls_total"
    f'{{status_code="STATUS_CODE_ERROR", service_name="checkout"}}[{WINDOW}]))'
)
CHECKOUT_LOGS = "resource.service.name:checkout"
PROXY_LOGS = 'resource.service.name:"frontend-proxy" AND body:*checkout*'
STAGES = ("[PlaceOrder]", "payment went through", "order placed")
STATUS = re.compile(r'"POST [^"]*checkout[^"]*" (\d{3}) ')
JAEGER = "http://localhost:8090/jaeger/ui/trace/"
session: dict[str, str] = {}


def rpc(method: str, params: dict | None = None, call_id: int | None = None) -> dict:
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
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.headers.get("Mcp-Session-Id"):
            session["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
        text = response.read().decode()
    data = [line[5:] for line in text.splitlines() if line.startswith("data:")]
    payload = data[0] if data else text
    return json.loads(payload) if payload.strip() else {}


def tool(name: str, arguments: dict, call_id: int) -> str:
    message = rpc("tools/call", {"name": name, "arguments": arguments}, call_id)
    result = message.get("result", {})
    text = " ".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    if "error" in message or result.get("isError"):
        raise SystemExit(f"{name} failed: {text or message.get('error')}"[:300])
    return text


def prometheus(expr: str, label: str, call_id: int) -> dict[str, float]:
    arguments = {"datasourceUid": "webstore-metrics", "expr": expr, "queryType": "instant"}
    rows = json.loads(tool("query_prometheus", {**arguments, "endTime": "now"}, call_id))
    return {row["metric"].get(label, "?"): float(row["value"][1]) for row in rows.get("data", [])}


def logs(query: str, call_id: int) -> list[dict]:
    arguments = {"datasourceUid": "webstore-logs", "index": "otel-logs-*", "query": query}
    window = {"startTime": f"now-{WINDOW}", "endTime": "now", "limit": 100}
    documents = json.loads(tool("query_elasticsearch", {**arguments, **window}, call_id) or "[]")
    return [document.get("_source", {}) for document in documents]


def counts(values: dict[str, float]) -> str:
    return ", ".join(f"{k}={v:.0f}" for k, v in sorted(values.items())) or "none"


client = {"name": "demo-signals", "version": "1"}
rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": client}, 1)
rpc("notifications/initialized")
ended = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
print(f"== {LABEL} | window: last {WINDOW} ending {ended}")
print("error calls by service:", counts(prometheus(ERROR_CALLS, "service_name", 2)))
print("checkout error calls by span:", counts(prometheus(CHECKOUT_SPANS, "span_name", 3)))
checkout = logs(CHECKOUT_LOGS, 4)
stages = Counter(stage for log in checkout for stage in STAGES if log.get("body") == stage)
print("checkout logs by stage:", ", ".join(f"{stage}={stages[stage]}" for stage in STAGES))
started = {log.get("traceId") for log in checkout if log.get("body") == STAGES[0]}
completed = {log.get("traceId") for log in checkout if log.get("body") == STAGES[2]}
stalled = sorted(trace for trace in started - completed if trace)
print("orders started without 'order placed':", len(stalled))
proxy = logs(PROXY_LOGS, 5)
codes = Counter(m.group(1) for log in proxy if (m := STATUS.search(str(log.get("body", "")))))
print("proxy access logs for POST checkout by status:", counts(codes))
if stalled:
    print(f"trace_id of a stalled order: {stalled[0]} | Jaeger UI: {JAEGER}{stalled[0]}")
