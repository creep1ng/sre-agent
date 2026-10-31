#!/usr/bin/env python3
"""API of the live-triage E2E (#703, #704): the real application, with a model that concludes at
once and a Grafana MCP stand-in. Each alert rule fires (value 1) unless the file named after its
rule id in FAULT_DIR reads `ok`, so the host or the browser runner opens and ends real episodes.
A number in FAULT_DIR/model-delay holds each model answer that many seconds, so a dispatch can be
interrupted while it waits (#704)."""

import asyncio
import json
import os
import secrets
import time
from pathlib import Path

import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.alerts import RULES
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

FAULT_DIR = Path(os.environ.get("FAULT_DIR", "/fault"))
REPLY = {"action": "conclude", "summary": "Modelo de prueba: sin evidencia adicional."}


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


class FaultMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if tool_name != "query_prometheus":
            return {"total": 0, "documents": []}
        rule = next((rule for rule in RULES if rule.expr == arguments.get("expr")), None)
        if rule is None:
            return {"resultType": "vector", "result": []}
        fault = FAULT_DIR / rule.rule_id
        healthy = fault.is_file() and fault.read_text().strip() == "ok"
        sample = [time.time(), "0" if healthy else "1"]
        return {"resultType": "vector", "result": [{"metric": {}, "value": sample}]}


if __name__ == "__main__":
    application = create_application(llm_provider=ConcludingModel(), mcp_client=FaultMCP())
    uvicorn.run(application, host="0.0.0.0", port=8000)
