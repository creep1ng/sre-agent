import json

import httpx
import pytest

from sre_agent.gateway.mcp import GrafanaMCPClient, MCPUpstreamInvalid, MCPUpstreamTimeout


@pytest.mark.asyncio
async def test_confined_client_initializes_once_and_calls_tools_exactly_once() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        method = json.loads(request.content)["method"]
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": "init", "result": {}},
                headers={"Mcp-Session-Id": "session-1"},
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": "call", "result": {"data": []}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GrafanaMCPClient(http_client, "http://grafana-mcp:8000/mcp", "secret-token")
        await client.call_tool("query_prometheus", {})
        await client.call_tool("query_prometheus", {})

    methods = [json.loads(request.content)["method"] for request in requests]
    assert methods == ["initialize", "notifications/initialized", "tools/call", "tools/call"]
    assert methods.count("tools/call") == 2
    assert "tools/list" not in methods
    assert all(request.url == "http://grafana-mcp:8000/mcp" for request in requests)
    assert all(request.headers["authorization"] == "Bearer secret-token" for request in requests)
    assert requests[2].headers["mcp-session-id"] == "session-1"
    assert all(b"secret-token" not in request.content for request in requests)


@pytest.mark.asyncio
async def test_confined_client_rejects_invalid_initialize_before_tools_call() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": "init", "result": "invalid"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GrafanaMCPClient(http_client, "http://grafana-mcp:8000/mcp", "secret-token")
        with pytest.raises(MCPUpstreamInvalid):
            await client.call_tool("query_prometheus", {})

    assert [json.loads(request.content)["method"] for request in requests] == ["initialize"]


@pytest.mark.asyncio
async def test_confined_client_maps_http_timeout_without_retrying() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("upstream timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GrafanaMCPClient(http_client, "http://grafana-mcp:8000/mcp", "secret-token")
        with pytest.raises(MCPUpstreamTimeout):
            await client.call_tool("query_prometheus", {})

    assert len(requests) == 1
