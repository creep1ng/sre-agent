"""Confined streamable-HTTP transport for the governed Grafana MCP."""

import json
from asyncio import Lock
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

MCP_TIMEOUT_SECONDS = 30.0


class MCPUpstreamTimeout(Exception):
    """The confined MCP client exceeded its request timeout."""


class MCPUpstreamUnavailable(Exception):
    """The confined MCP endpoint could not be reached or returned a transport error."""


class MCPUpstreamInvalid(Exception):
    """The upstream response could not be adapted to the published result contract."""


class MCPUpstreamClient(Protocol):
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any: ...


class GrafanaMCPClient:
    """Fixed-endpoint MCP transport with a gateway-owned bearer token.

    One streamable-HTTP session is initialized lazily. The transport never
    enumerates tools and sends one ``tools/call`` request per call_tool call.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        token: str,
        *,
        timeout_seconds: float = MCP_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Grafana MCP endpoint must be an absolute HTTP URL")
        if not token:
            raise ValueError("Grafana MCP token is required")
        self._client = client
        self._endpoint = endpoint
        self._token = token
        self._timeout = timeout_seconds
        self._session_id: str | None = None
        self._initialized = False
        self._initialization_lock = Lock()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        await self._initialize()
        return await self._post_rpc(
            {
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        )

    async def _initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialization_lock:
            if self._initialized:
                return
            response = await self._post_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": str(uuid4()),
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "sre-agent-gateway", "version": "1"},
                    },
                }
            )
            if not (
                isinstance(response, dict)
                and response.get("jsonrpc") == "2.0"
                and "error" not in response
                and isinstance(response.get("result"), dict)
            ):
                raise MCPUpstreamInvalid
            await self._post_rpc(
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            )
            self._initialized = True

    async def _post_rpc(self, request: dict[str, Any]) -> Any:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            response = await self._client.post(
                self._endpoint, headers=headers, json=request, timeout=self._timeout
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise MCPUpstreamTimeout from error
        except httpx.HTTPError as error:
            raise MCPUpstreamUnavailable from error
        if session_id := response.headers.get("Mcp-Session-Id"):
            self._session_id = session_id
        try:
            return self._decode_response(response)
        except ValueError as error:
            if request.get("method") == "notifications/initialized" and not response.text.strip():
                return None
            raise MCPUpstreamInvalid from error

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        text = response.text
        if not text.strip():
            return None
        data_lines = [line[5:] for line in text.splitlines() if line.startswith("data:")]
        return json.loads(data_lines[0] if data_lines else text)
