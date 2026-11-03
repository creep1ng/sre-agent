#!/usr/bin/env python3
"""API of the local full flow (docs/local-flow/README.md): the real
application with a Grafana stand-in, so the whole incident flow runs on one machine without EC2.

Like scripts/live_triage_upstreams.py, the stand-in delivers each rule below to the API's own
POST /v1/alert-intake/grafana every two seconds, but only while the file named after the rule in
FLOW_DIR reads `firing`; writing anything else afterwards sends one `resolved` delivery. The
Grafana MCP answers every Prometheus query with 42 server errors of the alert's service.
A rule file reading `flag:<name>` fires instead while that flag is not `off` in the flag stand-in
of compose.local-flow-flags.yaml (#724), so approving its flag.set resolves the alert. Without
current flag values in the catalog, the scripted model proposes the listed flags in order, and
the runtime refuses one that is already off.

LOCAL_FLOW_MODEL=real keeps the configured provider (OPENROUTER_API_KEY in .env); otherwise the
model is scripted like scripts/interrupt_policy_upstreams.py: one measured query, a hypothesis
citing it, then a rollback proposal that waits for a human decision. Asked to verify what an
approval ran (#723), it queries the service again and passes only when that query measured no
errors. Like Prometheus on EC2, the Grafana MCP counts 42 errors for a query naming a service
whose window reaches back to when its rule last fired, and 0 otherwise; the model keeps its
window after the receipt's executed_at only when its prompt asks it to."""

import asyncio
import json
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

FLOW_DIR = Path(os.environ.get("FLOW_DIR", "/flow"))
# Rule id -> (service, Grafana severity): the alerts the demo's Grafana rules send.
RULES = {
    "checkout-orders-error-rate": ("sre-checkout", "critical"),
    "checkout-payment-error-rate": ("checkout", "warning"),
}
INTAKE = "http://127.0.0.1:8000/v1/alert-intake/grafana"
STATE = re.compile(r"^State: (.*)$", re.MULTILINE)
REFUSED = re.compile(r"rejected: (\w+) is already ")
SERVICE = re.compile(r'service_name="([^"]+)"')
WINDOW = re.compile(r"\[(\d+)([smh])\]")
# What the verify prompt says when it asks for a window after the mitigation (#723).
AFTER_MITIGATION = "after mitigation.execution.executed_at"
# Rule id -> when the stand-in last saw it firing: its errors stay in any window reaching back.
LAST_FIRING: dict[str, datetime] = {}


def _errors_query(service: str, window: str = "5m") -> dict:
    query = {
        "datasource_uid": "webstore-metrics",
        "query_type": "instant",
        "expr": f'sum(increase(http_server_errors_total{{service_name="{service}"}}[{window}]))',
        "end_time": "now",
    }
    return {"action": "use_tool", "tool": "query_prometheus", "arguments": query}


def verify(service: str, collected: list[dict], since: str | None = None) -> dict:
    """A verification (#723): measure the service now, from `since` when it is given, then judge
    from what that query returned."""
    measured = [item for item in collected if not item.get("empty")]
    if not measured:
        if since is None:
            return _errors_query(service)
        elapsed = datetime.now(UTC) - datetime.fromisoformat(since.replace("Z", "+00:00"))
        return _errors_query(service, f"{max(int(elapsed.total_seconds()), 1)}s")
    values = [
        float(sample["value"][1])
        for item in measured
        for sample in json.loads(item["summary"]).get("result", [])
    ]
    passed = not any(values)
    return {
        "action": "verify_mitigation",
        "passed": passed,
        "summary": f"{service}: {max(values, default=0):g} errores 5xx tras la mitigación.",
        "supporting_evidence": [item["evidence_id"] for item in measured],
    }


def decide(state: dict, rejected: set[str] = frozenset(), windowed: bool = False) -> dict:
    incident, collected = state["incident"], state["collected_evidence"]
    service = incident["alert"].get("service") or "sre-checkout"
    if state["objective"] == "verify":
        ran = (state.get("mitigation") or {}).get("execution") or {}
        return verify(service, collected, ran.get("executed_at") if windowed else None)
    # The catalog lists flags without their current values (#724): the scripted model tries them
    # in order, and skips one the runtime refused as already off.
    flags = (state.get("service_operations") or {}).get("flags") or {}
    candidates = [name for name in flags if name not in rejected]
    if incident["hypotheses"] and candidates:  # the executor's catalog offers flag.set
        flag, variant = candidates[0], flags[candidates[0]]["allowed"][0]
        return {
            "action": "propose_mitigation",
            "description": f"Apagar el flag {flag} que rompe {service}.",
            "steps": [f"Poner {flag} en {variant} con flag.set."],
            "risk": "low",
            "verification_check": f"Los errores de {service} vuelven a cero.",
            "based_on_hypothesis": incident["hypotheses"][-1]["hypothesis_id"],
            "operation": {
                "service": service,
                "operation": "flag.set",
                "parameters": {"flag": flag, "variant": variant},
            },
        }
    if incident["hypotheses"]:
        return {
            "action": "propose_mitigation",
            "description": f"Revertir el último despliegue de {service}.",
            "steps": [f"Hacer rollback de {service} a la versión anterior."],
            "risk": "low",
            "verification_check": f"Los errores 5xx de {service} vuelven a cero.",
            "based_on_hypothesis": incident["hypotheses"][-1]["hypothesis_id"],
        }
    if not collected:
        return _errors_query(service)
    cited = [item["evidence_id"] for item in collected]
    return {
        "action": "propose_hypothesis",
        "statement": f"El último despliegue de {service} devuelve errores 5xx.",
        "confidence": "high",
        "supporting_evidence": cited,
        "verdicts": {
            evidence: {"verdict": "supports", "finding": "42 errores 5xx en 5 minutos."}
            for evidence in cited
        },
    }


class ScriptedModel:
    async def create(self, request: ProviderRequest) -> ProviderResult:
        await asyncio.sleep(float(os.environ.get("STEP_SECONDS") or 2))
        state = json.loads(STATE.findall(request.input)[-1])
        rejected = set(REFUSED.findall(request.input))
        return ProviderResult(
            response_id=f"resp_{secrets.token_hex(8)}",
            model=request.model,
            text=json.dumps(decide(state, rejected, AFTER_MITIGATION in request.input)),
            provider=request.provider,
        )


class GrafanaMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if tool_name != "query_prometheus":
            return {"total": 0, "documents": []}
        firing = [service for rule, (service, _) in RULES.items() if _firing(rule)]
        expr = str(arguments.get("expr", ""))
        # A query naming a service measures it: 42 errors while its rule fires, or while its
        # window still reaches back to when it fired, else 0.
        window = WINDOW.search(expr)
        seconds = int(window[1]) * {"s": 1, "m": 60, "h": 3600}[window[2]] if window else 0
        start = datetime.now(UTC).timestamp() - seconds
        recent = {
            service
            for rule, (service, _) in RULES.items()
            if rule in LAST_FIRING and LAST_FIRING[rule].timestamp() >= start
        }
        named = SERVICE.findall(expr)
        values = {
            name: "42" if name in firing or name in recent else "0" for name in named
        } or dict.fromkeys(firing, "42")
        samples = [
            {"metric": {"service_name": service}, "value": [datetime.now(UTC).timestamp(), value]}
            for service, value in values.items()
        ]
        return {"resultType": "vector", "result": samples}


def _firing(rule: str) -> bool:
    path = FLOW_DIR / rule
    content = path.read_text().strip() if path.is_file() else ""
    if content.startswith("flag:"):
        try:
            flags = json.loads((FLOW_DIR / "otel-state/flagd/demo.flagd.json").read_text())
        except (OSError, ValueError):
            return False
        firing = flags["flags"][content[5:]]["defaultVariant"] != "off"
    else:
        firing = content == "firing"
    if firing:
        LAST_FIRING[rule] = datetime.now(UTC)
    return firing


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def deliver_alerts() -> None:
    """Grafana's contact point: one delivery per firing rule, then one `resolved` when it clears."""
    secret = os.environ["ALERT_INTAKE_GRAFANA_SECRET"]
    started: dict[str, str] = {}
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {secret}"}) as client:
        while True:
            for rule, (service, severity) in RULES.items():
                firing = _firing(rule)
                if not firing and rule not in started:
                    continue
                starts_at = started.setdefault(rule, _now())
                status = "firing" if firing else "resolved"
                alert = {
                    "status": status,
                    "fingerprint": f"{rule}-{service}",
                    "startsAt": starts_at,
                    "endsAt": "0001-01-01T00:00:00Z" if firing else _now(),
                    "labels": {"alertname": rule, "service_name": service, "severity": severity},
                    "annotations": {"summary": f"{service}: {rule} is {status}."},
                }
                try:
                    response = await client.post(
                        INTAKE, json={"groupKey": rule, "status": status, "alerts": [alert]}
                    )
                except httpx.HTTPError:
                    continue
                if not firing and response.status_code == 200:
                    del started[rule]
            await asyncio.sleep(2)


if __name__ == "__main__":
    real = os.environ.get("LOCAL_FLOW_MODEL") == "real"
    application = create_application(
        llm_provider=None if real else ScriptedModel(), mcp_client=GrafanaMCP()
    )
    tasks: set[asyncio.Task] = set()
    application.add_event_handler(
        "startup", lambda: tasks.add(asyncio.get_running_loop().create_task(deliver_alerts()))
    )
    uvicorn.run(application, host="0.0.0.0", port=8000)
