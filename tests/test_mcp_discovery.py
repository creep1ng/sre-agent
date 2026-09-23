import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from sre_agent.gateway import mcp
from sre_agent.gateway.authentication import AuthenticationFailed
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import MCPServer, MCPTool, PolicyDecision, Principal, PrincipalContext
from sre_agent.mcp.owner import MCP_CONTRACT_VERSION, MCP_SERVER_ID, MCP_TOOL_IDS

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)
AUTHORIZATION = "Bearer sre_demo_0123456789abcdefghijklmnop"


def _context() -> PrincipalContext:
    return PrincipalContext(
        principal=Principal(
            principal_id="demo-human",
            kind="human",
            display_name="Demo human",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        ),
        credential_id="credential-demo-human",
        authenticated_at=NOW,
    )


def _decision(allowed: bool = True) -> AuthorizationEvaluation:
    return AuthorizationEvaluation(
        decision=PolicyDecision(
            decision="allow" if allowed else "deny",
            reason_code="grant_matched" if allowed else "no_matching_grant",
            policy_id="grant-mcp" if allowed else None,
        ),
        denial_cause=None if allowed else AuthorizationDenialCause.GRANT_NOT_APPLICABLE,
    )


def _server(status: str = "active") -> MCPServer:
    return MCPServer(
        server_id=MCP_SERVER_ID,
        owner_id="mcp-platform",
        contract_version=MCP_CONTRACT_VERSION,
        status=status,  # type: ignore[arg-type]
        endpoint="http://grafana-mcp:8000/mcp",
        display_name="Grafana MCP",
        visibility="private",
        description="Governed Grafana read-only MCP.",
        tags=["grafana", "mcp"],
        created_at=NOW,
        updated_at=NOW,
    )


def _tool(tool_id: str, status: str = "active") -> MCPTool:
    return MCPTool(
        tool_id=tool_id,
        server_id=MCP_SERVER_ID,
        owner_id="mcp-platform",
        contract_version=MCP_CONTRACT_VERSION,
        status=status,  # type: ignore[arg-type]
        upstream_name=tool_id,
        display_name=tool_id,
        visibility="private",
        description=f"Governed {tool_id}.",
        tags=["grafana"],
        created_at=NOW,
        updated_at=NOW,
    )


class MemoryOwner:
    def __init__(self, *, server: MCPServer | None = None) -> None:
        self.server = server or _server()
        self.tools = {tool_id: _tool(tool_id) for tool_id in MCP_TOOL_IDS}
        self.reads: list[tuple[str, str]] = []

    async def get_server(self, server_id: str) -> MCPServer | None:
        self.reads.append(("server", server_id))
        return self.server if self.server and server_id == self.server.server_id else None

    async def get_tool(self, tool_id: str) -> MCPTool | None:
        self.reads.append(("tool", tool_id))
        return self.tools.get(tool_id)


class MemorySessions:
    def __init__(self, owner: MemoryOwner) -> None:
        self.owner = owner

    def __call__(self) -> Any:
        @asynccontextmanager
        async def session() -> Any:
            yield self.owner

        return session()


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool_name, arguments))
        return {"data": []}


def _service(monkeypatch: pytest.MonkeyPatch, owner: MemoryOwner) -> tuple[Any, RecordingClient]:
    client = RecordingClient()

    async def authorize(*_args: Any) -> tuple[PrincipalContext, AuthorizationEvaluation]:
        return _context(), _decision()

    monkeypatch.setattr(mcp, "authorize_governed_access", authorize)
    service = mcp.MCPGatewayService(
        MemorySessions(owner), client, owner_repository_factory=lambda session: session
    )
    return service, client


@pytest.mark.asyncio
async def test_granted_discovery_returns_exactly_two_active_tools_without_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = MemoryOwner()
    client = RecordingClient()
    scopes: list[tuple[str | None, str, str, str]] = []
    service = mcp.MCPGatewayService(
        MemorySessions(owner), client, owner_repository_factory=lambda session: session
    )

    async def authorize(
        _sessions: Any,
        authorization: str | None,
        action: str,
        resource_type: str,
        resource_id: str,
    ) -> tuple[PrincipalContext, AuthorizationEvaluation]:
        scopes.append((authorization, action, resource_type, resource_id))
        return _context(), _decision()

    monkeypatch.setattr(mcp, "authorize_governed_access", authorize)
    response = await service.discovery(AUTHORIZATION)

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["server"]["server_id"] == MCP_SERVER_ID
    assert [tool["tool_id"] for tool in body["tools"]] == list(MCP_TOOL_IDS)
    assert len(body["tools"]) == 2
    assert "endpoint" not in body["server"]
    assert scopes == [(AUTHORIZATION, "mcp.discovery", "mcp_server", MCP_SERVER_ID)]
    assert client.calls == []


@pytest.mark.asyncio
async def test_denied_server_grant_stops_before_owner_lookup_or_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = MemoryOwner()
    client = RecordingClient()

    async def deny(*_args: Any) -> tuple[PrincipalContext, AuthorizationEvaluation]:
        return _context(), _decision(False)

    monkeypatch.setattr(mcp, "authorize_governed_access", deny)
    service = mcp.MCPGatewayService(
        MemorySessions(owner), client, owner_repository_factory=lambda session: session
    )
    response = await service.discovery(AUTHORIZATION)

    assert response.status_code == 403
    assert owner.reads == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_authentication_failure_stops_before_owner_lookup_or_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = MemoryOwner()
    client = RecordingClient()

    async def fail(*_args: Any) -> tuple[PrincipalContext, AuthorizationEvaluation]:
        raise AuthenticationFailed

    monkeypatch.setattr(mcp, "authorize_governed_access", fail)
    service = mcp.MCPGatewayService(
        MemorySessions(owner), client, owner_repository_factory=lambda session: session
    )
    response = await service.discovery(None)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert owner.reads == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_unknown_or_inactive_owner_is_not_enumerated_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = MemoryOwner(server=_server("inactive"))
    client = RecordingClient()

    async def allow(*_args: Any) -> tuple[PrincipalContext, AuthorizationEvaluation]:
        return _context(), _decision()

    monkeypatch.setattr(mcp, "authorize_governed_access", allow)
    service = mcp.MCPGatewayService(
        MemorySessions(owner), client, owner_repository_factory=lambda session: session
    )
    response = await service.discovery(AUTHORIZATION)

    assert response.status_code == 403
    assert owner.reads == [("server", MCP_SERVER_ID)]
    assert client.calls == []
