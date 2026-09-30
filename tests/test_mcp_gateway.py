"""Gateway boundary contract for governed Grafana MCP access (#187 T3)."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import MCPServer, MCPTool, PolicyDecision, Principal, PrincipalContext
from sre_agent.mcp.owner import MCP_CONTRACT_VERSION, MCP_SERVER_ID, MCP_TOOL_IDS
from sre_agent.settings import Settings

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)
AUTHORIZATION = "Bearer sre_demo_0123456789abcdefghijklmnop"


def _context() -> PrincipalContext:
    return PrincipalContext(
        principal=Principal(
            principal_id="demo-agent",
            kind="agent",
            display_name="Demo agent",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        ),
        credential_id="credential-demo-agent",
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
    def __init__(self, *, server_status: str = "active", tool_status: str = "active") -> None:
        self.server = _server(server_status)
        self.tools = {tool_id: _tool(tool_id, tool_status) for tool_id in MCP_TOOL_IDS}
        self.reads: list[tuple[str, str]] = []

    async def get_server(self, server_id: str) -> MCPServer | None:
        self.reads.append(("server", server_id))
        return self.server if server_id == self.server.server_id else None

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
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((tool_name, arguments))
        if self.error:
            raise self.error
        return self.result


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def append(self, event: Any) -> None:
        self.events.append(event)


class FailingAudit:
    async def append(self, event: Any) -> None:
        del event
        raise RuntimeError("audit sink unavailable")


def _service(
    monkeypatch: pytest.MonkeyPatch,
    owner: MemoryOwner,
    client: RecordingClient,
    *,
    audit: Any | None = None,
    projector: AuditProjector | None = None,
):
    import sre_agent.gateway.mcp as mcp_gateway

    async def authorize(*_args: Any) -> tuple[PrincipalContext, AuthorizationEvaluation]:
        return _context(), _decision()

    monkeypatch.setattr(mcp_gateway, "authorize_governed_access", authorize)
    return mcp_gateway.MCPGatewayService(
        MemorySessions(owner),
        client,
        audit=audit or RecordingAudit(),
        projector=projector,
        owner_repository_factory=lambda session: session,
    )


@pytest.mark.asyncio
async def test_discovery_is_granted_without_upstream_enumeration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingClient()
    service = _service(monkeypatch, MemoryOwner(), client)

    response = await service.discovery(AUTHORIZATION)

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["server"]["server_id"] == MCP_SERVER_ID
    assert [tool["tool_id"] for tool in body["tools"]] == list(MCP_TOOL_IDS)
    assert body["server"].get("endpoint") is None
    assert client.calls == []
    event = service.audit.events[0].model_dump(mode="json")
    assert event["content_state"] == "absent"
    assert event["arguments_recorded"] is False
    assert event["result_recorded"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", [False, True])
async def test_denied_or_unknown_invocation_is_uniform_and_does_not_probe_owner_or_upstream(
    monkeypatch: pytest.MonkeyPatch, unknown: bool
) -> None:
    import sre_agent.gateway.mcp as mcp_gateway

    owner = MemoryOwner()
    client = RecordingClient()

    async def deny(*_args: Any) -> tuple[PrincipalContext, AuthorizationEvaluation]:
        return _context(), _decision(False)

    monkeypatch.setattr(mcp_gateway, "authorize_governed_access", deny)
    service = mcp_gateway.MCPGatewayService(
        MemorySessions(owner),
        client,
        audit=RecordingAudit(),
        owner_repository_factory=lambda session: session,
    )
    tool_id = "query_unknown" if unknown else "query_prometheus"

    response = await service.invoke(tool_id, {}, AUTHORIZATION)

    assert response.status_code == 403
    assert json.loads(response.body)["error"]["code"] == "resource_unavailable"
    assert client.calls == []
    assert owner.reads == []


@pytest.mark.asyncio
async def test_missing_credential_is_401_before_owner_or_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sre_agent.gateway.mcp as mcp_gateway

    owner = MemoryOwner()
    client = RecordingClient()

    async def authenticate(*_args: Any) -> Any:
        raise mcp_gateway.AuthenticationFailed

    monkeypatch.setattr(mcp_gateway, "authorize_governed_access", authenticate)
    service = mcp_gateway.MCPGatewayService(
        MemorySessions(owner),
        client,
        audit=RecordingAudit(),
        owner_repository_factory=lambda session: session,
    )

    response = await service.discovery(None)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert json.loads(response.body)["error"]["code"] == "authentication_failed"
    assert owner.reads == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_allowed_invocation_validates_closed_input_maps_result_and_calls_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = {"data": [{"metric": {"service_name": "checkout"}, "value": [1, "4"]}]}
    client = RecordingClient(upstream)
    service = _service(monkeypatch, MemoryOwner(), client)

    response = await service.invoke(
        "query_prometheus",
        {
            "datasource_uid": "webstore-metrics",
            "expr": "sum(rate(calls_total[5m]))",
            "query_type": "instant",
            "end_time": "now",
        },
        AUTHORIZATION,
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "result_type": "vector",
        "result": upstream["data"],
        "warnings": [],
    }
    assert client.calls == [
        (
            "query_prometheus",
            {
                "datasourceUid": "webstore-metrics",
                "expr": "sum(rate(calls_total[5m]))",
                "queryType": "instant",
                "endTime": "now",
            },
        )
    ]


@pytest.mark.asyncio
async def test_audit_failure_suppresses_success_payload_and_returns_public_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingClient({"data": []})
    service = _service(monkeypatch, MemoryOwner(), client, audit=FailingAudit())

    response = await service.invoke(
        "query_prometheus",
        {
            "datasource_uid": "webstore-metrics",
            "expr": "up",
            "query_type": "instant",
            "end_time": "now",
        },
        AUTHORIZATION,
    )

    body = json.loads(response.body)
    assert response.status_code == 503
    assert body["error"]["code"] == "audit_unavailable"
    assert body["retryable"] is True
    assert "data" not in body
    assert "up" not in body


@pytest.mark.asyncio
async def test_invalid_input_persists_validation_stage_without_subject_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = RecordingAudit()
    service = _service(
        monkeypatch,
        MemoryOwner(),
        RecordingClient(),
        audit=audit,
        projector=AuditProjector(b"mcp-test-audit-key"),
    )

    response = await service.invoke(
        "query_prometheus", {"expr": "bad", "extra": True}, AUTHORIZATION
    )

    assert response.status_code == 422
    event = audit.events[0]
    assert event.stage == "validation"
    assert event.reason_code == "contract_validation_failed"
    assert event.identity is None
    assert event.resource is None
    assert event.policy_decision is None


@pytest.mark.asyncio
async def test_inactive_catalog_shadow_does_not_override_active_owner_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = MemoryOwner()
    owner.catalog_shadow_status = "inactive"
    client = RecordingClient({"data": []})
    service = _service(monkeypatch, owner, client)

    response = await service.invoke(
        "query_prometheus",
        {
            "datasource_uid": "webstore-metrics",
            "expr": "up",
            "query_type": "instant",
            "end_time": "now",
        },
        AUTHORIZATION,
    )

    assert response.status_code == 200
    assert len(client.calls) == 1
    assert owner.reads == [("server", "grafana-mcp"), ("tool", "query_prometheus")]


@pytest.mark.asyncio
async def test_invalid_input_is_public_422_and_never_calls_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingClient()
    service = _service(monkeypatch, MemoryOwner(), client)

    response = await service.invoke(
        "query_prometheus", {"expr": "bad", "extra": True}, AUTHORIZATION
    )

    assert response.status_code == 422
    assert json.loads(response.body)["error"]["code"] == "contract_validation_failed"
    assert client.calls == []


@pytest.mark.asyncio
async def test_zero_duration_is_contract_invalid_and_never_calls_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingClient()
    service = _service(monkeypatch, MemoryOwner(), client)

    response = await service.invoke(
        "query_prometheus",
        {
            "datasource_uid": "webstore-metrics",
            "expr": "up",
            "query_type": "instant",
            "end_time": "now-0s",
        },
        AUTHORIZATION,
    )

    assert response.status_code == 422
    assert json.loads(response.body)["error"]["code"] == "contract_validation_failed"
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("forgery", ["contract", "owner", "upstream"])
async def test_forged_owner_rows_are_unavailable_before_upstream(
    monkeypatch: pytest.MonkeyPatch, forgery: str
) -> None:
    owner = MemoryOwner()
    if forgery == "contract":
        owner.server = owner.server.model_copy(update={"contract_version": "9.9.9"})
    elif forgery == "owner":
        owner.tools["query_prometheus"] = owner.tools["query_prometheus"].model_copy(
            update={"owner_id": "other-owner"}
        )
    else:
        owner.tools["query_prometheus"] = owner.tools["query_prometheus"].model_copy(
            update={"upstream_name": "list_datasources"}
        )
    client = RecordingClient({"data": []})
    service = _service(monkeypatch, owner, client)

    response = await service.invoke(
        "query_prometheus",
        {
            "datasource_uid": "webstore-metrics",
            "expr": "up",
            "query_type": "instant",
            "end_time": "now",
        },
        AUTHORIZATION,
    )

    assert response.status_code == 403
    assert json.loads(response.body)["error"]["code"] == "resource_unavailable"
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        ("timeout", 504, "upstream_timeout"),
        ("unavailable", 503, "upstream_unavailable"),
        ("invalid", 502, "upstream_invalid"),
    ],
)
async def test_upstream_failures_have_closed_public_errors_and_one_call(
    monkeypatch: pytest.MonkeyPatch, error: str, status: int, code: str
) -> None:
    import sre_agent.gateway.mcp as mcp_gateway

    failures = {
        "timeout": mcp_gateway.MCPUpstreamTimeout(),
        "unavailable": mcp_gateway.MCPUpstreamUnavailable(),
        "invalid": mcp_gateway.MCPUpstreamInvalid(),
    }
    client = RecordingClient(error=failures[error])
    service = _service(monkeypatch, MemoryOwner(), client)
    payload = {
        "datasource_uid": "webstore-metrics",
        "expr": "up",
        "query_type": "instant",
        "end_time": "now",
    }

    response = await service.invoke("query_prometheus", payload, AUTHORIZATION)

    assert response.status_code == status
    assert json.loads(response.body)["error"]["code"] == code
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_gateway_enforces_the_thirty_second_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sre_agent.gateway.mcp as mcp_gateway

    class SlowClient(RecordingClient):
        async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
            self.calls.append((tool_name, arguments))
            await asyncio.sleep(0.05)
            return {"data": []}

    monkeypatch.setattr(mcp_gateway, "MCP_TIMEOUT_SECONDS", 0.001)
    client = SlowClient()
    service = _service(monkeypatch, MemoryOwner(), client)
    response = await service.invoke(
        "query_prometheus",
        {
            "datasource_uid": "webstore-metrics",
            "expr": "up",
            "query_type": "instant",
            "end_time": "now",
        },
        AUTHORIZATION,
    )

    assert response.status_code == 504
    assert json.loads(response.body)["error"]["code"] == "upstream_timeout"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_persistent_audit_projection_is_metadata_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingClient({"data": []})
    service = _service(monkeypatch, MemoryOwner(), client)
    service.projector = AuditProjector(b"mcp-test-audit-key")

    response = await service.invoke(
        "query_prometheus",
        {
            "datasource_uid": "webstore-metrics",
            "expr": "up",
            "query_type": "instant",
            "end_time": "now",
        },
        AUTHORIZATION,
    )

    assert response.status_code == 200
    event = service.audit.events[0].model_dump(mode="json")
    assert event["operation"] == "mcp.invoke"
    assert event["resource"]["resource_type"] == "mcp_tool"
    assert event["content_state"] == "absent"
    assert "up" not in str(event)
    assert "data" not in str(event)


@pytest.mark.asyncio
async def test_confined_client_initializes_once_and_counts_one_tools_call_per_invocation() -> None:
    from sre_agent.gateway.mcp import GrafanaMCPClient

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = request.read()
        method = json.loads(payload)["method"]
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
        client = GrafanaMCPClient(
            http_client, "http://grafana-mcp:8000/mcp", "secret-token"
        )
        await client.call_tool("query_prometheus", {})
        await client.call_tool("query_prometheus", {})

    methods = [json.loads(request.content)["method"] for request in requests]
    assert methods == ["initialize", "notifications/initialized", "tools/call", "tools/call"]
    assert methods.count("tools/call") == 2
    assert "tools/list" not in methods
    assert all(request.url == "http://grafana-mcp:8000/mcp" for request in requests)
    assert all(request.headers["authorization"] == "Bearer secret-token" for request in requests)
    assert all(b"secret-token" not in request.content for request in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initialize_payload",
    [
        {"jsonrpc": "2.0", "id": "init", "error": {"code": -32000, "message": "no"}},
        {"jsonrpc": "2.0", "id": "init", "result": "not-an-object"},
    ],
)
async def test_confined_client_rejects_invalid_initialize_before_tools_call(
    initialize_payload: dict[str, Any],
) -> None:
    from sre_agent.gateway.mcp import GrafanaMCPClient, MCPUpstreamInvalid

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        method = json.loads(request.content)["method"]
        assert method == "initialize"
        return httpx.Response(200, json=initialize_payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GrafanaMCPClient(http_client, "http://grafana-mcp:8000/mcp", "secret-token")
        with pytest.raises(MCPUpstreamInvalid):
            await client.call_tool("query_prometheus", {})

    assert [json.loads(request.content)["method"] for request in requests] == ["initialize"]


@pytest.mark.asyncio
async def test_http_router_exposes_only_governed_gateway_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(monkeypatch, MemoryOwner(), RecordingClient())
    app = FastAPI()
    app.include_router(mcp_gateway_router(service))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (
            await client.get("/v1/mcp/discovery", headers={"Authorization": AUTHORIZATION})
        ).status_code == 200
        assert (
            await client.post(
                "/v1/mcp/tools/list_datasources",
                headers={"Authorization": AUTHORIZATION},
                json={},
            )
        ).status_code == 403


def mcp_gateway_router(service: Any) -> Any:
    from sre_agent.gateway.mcp import mcp_router

    return mcp_router(service)


def test_application_does_not_mount_mcp_without_hmac_audit_configuration() -> None:
    from sre_agent.application import create_application

    application = create_application(
        Settings(
            "postgresql://unused",
            grafana_mcp_endpoint="http://grafana-mcp:8000/mcp",
            grafana_mcp_token="test-token",
        ),
        mcp_client=RecordingClient(),
    )

    assert "/v1/mcp/discovery" not in {route.path for route in application.routes}
