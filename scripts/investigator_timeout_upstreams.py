#!/usr/bin/env python3
"""API of the investigator-timeout E2E: the real application, with a model that answers after
SLOW_SECONDS (a slow provider within OPENROUTER_TIMEOUT_SECONDS) and a Grafana MCP stand-in."""

import asyncio
import json
import os
import secrets

import uvicorn

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult

SLOW_SECONDS = float(os.environ.get("SLOW_SECONDS", "50"))
REPLY = {"action": "conclude", "summary": "El proveedor lento respondió; no hay más evidencia."}


class SlowModel:
    async def create(self, request: ProviderRequest) -> ProviderResult:
        await asyncio.sleep(SLOW_SECONDS)
        return ProviderResult(
            response_id=f"resp_{secrets.token_hex(8)}",
            model=request.model,
            text=json.dumps(REPLY),
            provider=request.provider,
        )


class EmptyMCP:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        return {"total": 0, "documents": []}


if __name__ == "__main__":
    application = create_application(llm_provider=SlowModel(), mcp_client=EmptyMCP())
    uvicorn.run(application, host="0.0.0.0", port=8000)
