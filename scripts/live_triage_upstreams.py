#!/usr/bin/env python3
"""API of the live-triage E2E (#703, #704): the real application, with a model that concludes at
once and a Grafana stand-in. Since #765 alerts only come in through intake: every two seconds the
stand-in delivers each rule below to the API's own POST /v1/alert-intake/grafana, firing unless
the file named after its rule id in FAULT_DIR reads `ok`, so the host or the browser runner opens
and ends real episodes. A number in FAULT_DIR/model-delay holds each model answer that many
seconds, so a dispatch can be interrupted while it waits (#704)."""

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

FAULT_DIR = Path(os.environ.get("FAULT_DIR", "/fault"))
REPLY = {"action": "conclude", "summary": "Modelo de prueba: sin evidencia adicional."}
# Rule id -> (service, Grafana severity): the alerts the demo's Grafana rules send.
RULES = {
    "checkout-payment-error-rate": ("checkout", "critical"),
    "checkout-orders-error-rate": ("sre-checkout", "warning"),
}
INTAKE = "http://127.0.0.1:8000/v1/alert-intake/grafana"


class ConcludingModel:
    async def create(self, request: ProviderRequest) -> ProviderResult:
        delay = FAULT_DIR / "model-delay"
        if delay.is_file():
            await asyncio.sleep(float(delay.read_text().strip() or 0))
        return ProviderResult(
            response_id=f"resp_{secrets.token_hex(8)}",
            model=request.model,
            text=json.dumps(REPLY),
            provider=request.provider,
        )


class EmptyMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if tool_name != "query_prometheus":
            return {"total": 0, "documents": []}
        return {"resultType": "vector", "result": []}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def deliver_alerts() -> None:
    """Grafana's contact point: one delivery per rule, a new episode after each `ok`."""
    secret = os.environ["ALERT_INTAKE_GRAFANA_SECRET"]
    started: dict[str, str] = {}
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {secret}"}) as client:
        while True:
            for rule, (service, severity) in RULES.items():
                fault = FAULT_DIR / rule
                healthy = fault.is_file() and fault.read_text().strip() == "ok"
                if healthy and rule not in started:
                    continue
                starts_at = started.setdefault(rule, _now())
                status = "resolved" if healthy else "firing"
                alert = {
                    "status": status,
                    "fingerprint": f"{rule}-{service}",
                    "startsAt": starts_at,
                    "endsAt": _now() if healthy else "0001-01-01T00:00:00Z",
                    "labels": {"alertname": rule, "service_name": service, "severity": severity},
                    "annotations": {"summary": f"{service}: {rule} is {status}."},
                }
                try:
                    response = await client.post(
                        INTAKE, json={"groupKey": rule, "status": status, "alerts": [alert]}
                    )
                except httpx.HTTPError:
                    continue
                if healthy and response.status_code == 200:
                    del started[rule]
            await asyncio.sleep(2)


if __name__ == "__main__":
    application = create_application(llm_provider=ConcludingModel(), mcp_client=EmptyMCP())
    tasks: set[asyncio.Task] = set()
    application.add_event_handler(
        "startup", lambda: tasks.add(asyncio.get_running_loop().create_task(deliver_alerts()))
    )
    uvicorn.run(application, host="0.0.0.0", port=8000)
