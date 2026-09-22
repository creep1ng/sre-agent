"""Confined streamable-HTTP transport for the governed Grafana MCP."""

import json
from asyncio import Lock, wait_for
from time import monotonic
from typing import Annotated, Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.gateway.responses import AuditStore
from sre_agent.governance.authorization import AuthorizationEvaluation
from sre_agent.governance.dto import MCPServer, MCPTool, PrincipalContext
from sre_agent.mcp.owner import MCP_CONTRACT_VERSION, MCP_SERVER_ID, MCP_TOOL_IDS
from sre_agent.persistence.repositories import MCPOwnerRepository

MCP_TIMEOUT_SECONDS = 30.0
_TIME_PATTERN = r"^(now|now-[1-9][0-9]*[smhd])$"


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


class PrometheusQuery(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    datasource_uid: str = Field(pattern=r"^webstore-metrics$")
    expr: str = Field(min_length=1, max_length=4096)
    query_type: str = Field(pattern=r"^instant$")
    end_time: str = Field(pattern=_TIME_PATTERN)


class ElasticsearchQuery(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    datasource_uid: str = Field(pattern=r"^webstore-logs$")
    index: str = Field(pattern=r"^otel-logs-\*$")
    query: str = Field(min_length=1, max_length=4096)
    start_time: str = Field(pattern=r"^now-[1-9][0-9]*[smhd]$")
    end_time: str = Field(pattern=r"^now$")
    limit: int = Field(ge=1, le=100)


class PrometheusResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    result_type: str = Field(pattern=r"^(matrix|vector|scalar|string)$")
    result: list[dict[str, Any]] = Field(max_length=1000)
    warnings: list[Annotated[str, Field(max_length=500)]] = Field(max_length=16)


class ElasticsearchResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    total: int = Field(ge=0)
    documents: list[dict[str, Any]] = Field(max_length=100)
    warnings: list[Annotated[str, Field(max_length=500)]] = Field(max_length=16)


class MCPAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str
    request_id: UUID
    status: int
    server_id: str
    tool_id: str | None
    principal_kind: str | None
    decision: str | None
    latency_ms: int
    content_state: str = "absent"
    arguments_recorded: bool = False
    result_recorded: bool = False


class _OwnerRepository(Protocol):
    async def get_server(self, server_id: str) -> MCPServer | None: ...

    async def get_tool(self, tool_id: str) -> MCPTool | None: ...


class MCPGatewayService:
    """Authenticate and authorize discovery before reading the owner contract."""

    def __init__(
        self,
        sessions: Any,
        client: MCPUpstreamClient,
        *,
        audit: AuditStore | None = None,
        projector: AuditProjector | None = None,
        owner_repository_factory: Any = MCPOwnerRepository,
    ) -> None:
        self.sessions = sessions
        self.client = client
        self.audit = audit
        self.projector = projector
        self.owner_repository_factory = owner_repository_factory

    async def discovery(self, authorization: str | None) -> JSONResponse:
        request_id = str(uuid4())
        started = monotonic()
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, "mcp.discovery", "mcp_server", MCP_SERVER_ID
            )
        except AuthenticationFailed:
            return JSONResponse(
                {
                    "error": {"code": "authentication_failed", "message": "Authentication failed."},
                    "request_id": request_id,
                    "retryable": False,
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if evaluation.decision.decision != "allow":
            return await self._audited(
                UUID(request_id),
                started,
                self._unavailable(request_id),
                operation="mcp.discovery",
                stage="authorization",
                context=context,
                evaluation=evaluation,
                reason="no_matching_grant",
            )
        server, tools = await self._active_contract()
        if server is None or tools is None:
            return self._unavailable(request_id)
        return await self._audited(
            UUID(request_id),
            started,
            JSONResponse(
                {
                    "contract_version": MCP_CONTRACT_VERSION,
                    "server": {
                        "resource_type": "mcp_server",
                        "server_id": server.server_id,
                        "display_name": server.display_name,
                        "description": server.description,
                        "visibility": server.visibility,
                        "tags": server.tags,
                    },
                    "tools": [
                        {
                            "resource_type": "mcp_tool",
                            "tool_id": tool.tool_id,
                            "server_id": tool.server_id,
                            "display_name": tool.display_name,
                            "description": tool.description,
                            "visibility": tool.visibility,
                            "tags": tool.tags,
                            "action": "mcp.invoke",
                        }
                        for tool in tools
                    ],
                }
            ),
            operation="mcp.discovery",
            stage="response",
            context=context,
            evaluation=evaluation,
        )

    async def invoke(self, tool_id: str, raw: Any, authorization: str | None) -> JSONResponse:
        request_id = str(uuid4())
        started = monotonic()
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, "mcp.invoke", "mcp_tool", tool_id
            )
        except AuthenticationFailed:
            return JSONResponse(
                {
                    "error": {"code": "authentication_failed", "message": "Authentication failed."},
                    "request_id": request_id,
                    "retryable": False,
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if evaluation.decision.decision != "allow":
            return await self._audited(
                UUID(request_id),
                started,
                self._unavailable(request_id),
                operation="mcp.invoke",
                stage="authorization",
                context=context,
                evaluation=evaluation,
                tool_id=tool_id,
                reason="no_matching_grant",
            )
        _, tools = await self._active_contract(tool_id)
        tool = tools[0] if tools else None
        if tool is None:
            return self._unavailable(request_id)
        try:
            arguments = self._validate_input(tool_id, raw)
        except ValidationError:
            return await self._audited(
                UUID(request_id),
                started,
                self._error(request_id, 422, "contract_validation_failed", False),
                operation="mcp.invoke",
                stage="validation",
                reason="contract_validation_failed",
                tool_id=tool_id,
            )
        try:
            result = await wait_for(
                self.client.call_tool(tool.upstream_name, arguments), MCP_TIMEOUT_SECONDS
            )
            return await self._audited(
                UUID(request_id),
                started,
                JSONResponse(self._map_result(tool_id, result)),
                operation="mcp.invoke",
                stage="response",
                context=context,
                evaluation=evaluation,
                tool_id=tool_id,
            )
        except (TimeoutError, MCPUpstreamTimeout):
            return await self._audited(
                UUID(request_id),
                started,
                self._error(request_id, 504, "upstream_timeout", True),
                operation="mcp.invoke",
                stage="upstream",
                context=context,
                evaluation=evaluation,
                reason="upstream_timeout",
                tool_id=tool_id,
            )
        except MCPUpstreamUnavailable:
            return await self._audited(
                UUID(request_id),
                started,
                self._error(request_id, 503, "upstream_unavailable", True),
                operation="mcp.invoke",
                stage="upstream",
                context=context,
                evaluation=evaluation,
                reason="upstream_unavailable",
                tool_id=tool_id,
            )
        except MCPUpstreamInvalid:
            return await self._audited(
                UUID(request_id),
                started,
                self._error(request_id, 502, "upstream_invalid", False),
                operation="mcp.invoke",
                stage="upstream",
                context=context,
                evaluation=evaluation,
                reason="upstream_invalid",
                tool_id=tool_id,
            )

    async def _active_contract(
        self, tool_id: str | None = None
    ) -> tuple[MCPServer | None, list[MCPTool] | None]:
        try:
            async with self.sessions() as session:
                owner: _OwnerRepository = self.owner_repository_factory(session)
                server = await owner.get_server(MCP_SERVER_ID)
                if (
                    server is None
                    or server.status != "active"
                    or server.contract_version != MCP_CONTRACT_VERSION
                ):
                    return None, None
                if tool_id is not None:
                    tool = await owner.get_tool(tool_id)
                    if (
                        tool is None
                        or tool.status != "active"
                        or tool.contract_version != MCP_CONTRACT_VERSION
                        or tool.server_id != server.server_id
                        or tool.owner_id != server.owner_id
                        or tool.tool_id != tool_id
                        or tool.upstream_name != tool.tool_id
                        or tool.tool_id not in MCP_TOOL_IDS
                    ):
                        return server, None
                    return server, [tool]
                tools: list[MCPTool] = []
                for tool_id in MCP_TOOL_IDS:
                    tool = await owner.get_tool(tool_id)
                    if (
                        tool is None
                        or tool.status != "active"
                        or tool.contract_version != MCP_CONTRACT_VERSION
                        or tool.server_id != server.server_id
                        or tool.owner_id != server.owner_id
                        or tool.tool_id != tool_id
                        or tool.upstream_name != tool.tool_id
                    ):
                        return server, None
                    tools.append(tool)
                return server, tools
        except Exception:
            return None, None

    @staticmethod
    def _validate_input(tool_id: str, raw: Any) -> dict[str, Any]:
        if tool_id == "query_prometheus":
            request = PrometheusQuery.model_validate(raw)
            return {
                "datasourceUid": request.datasource_uid,
                "expr": request.expr,
                "queryType": request.query_type,
                "endTime": request.end_time,
            }
        if tool_id == "query_elasticsearch":
            request = ElasticsearchQuery.model_validate(raw)
            return {
                "datasourceUid": request.datasource_uid,
                "index": request.index,
                "query": request.query,
                "startTime": request.start_time,
                "endTime": request.end_time,
                "limit": request.limit,
            }
        raise ValidationError.from_exception_data("MCP tool", [])

    @classmethod
    def _map_result(cls, tool_id: str, raw: Any) -> dict[str, Any]:
        payload = cls._unwrap_upstream(raw)
        if tool_id == "query_prometheus":
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                payload = payload["data"]
            if not isinstance(payload, dict):
                raise MCPUpstreamInvalid
            if "result" in payload:
                result = payload
            elif "data" in payload:
                result = {
                    "result": payload["data"],
                    "resultType": payload.get("resultType", "vector"),
                }
            else:
                raise MCPUpstreamInvalid
            try:
                return PrometheusResult(
                    result_type=result.get("resultType", "vector"),
                    result=result["result"],
                    warnings=result.get("warnings", []),
                ).model_dump(mode="json")
            except (KeyError, ValidationError) as error:
                raise MCPUpstreamInvalid from error
        if tool_id == "query_elasticsearch":
            if isinstance(payload, list):
                result = {"total": len(payload), "documents": payload, "warnings": []}
            elif isinstance(payload, dict):
                documents = payload.get("documents", payload.get("hits", []))
                result = {
                    "total": payload.get(
                        "total", len(documents) if isinstance(documents, list) else 0
                    ),
                    "documents": documents,
                    "warnings": payload.get("warnings", []),
                }
            else:
                raise MCPUpstreamInvalid
            try:
                return ElasticsearchResult.model_validate(result).model_dump(mode="json")
            except ValidationError as error:
                raise MCPUpstreamInvalid from error
        raise MCPUpstreamInvalid

    @staticmethod
    def _unwrap_upstream(raw: Any) -> Any:
        payload = raw
        if isinstance(payload, dict) and "error" in payload:
            raise MCPUpstreamInvalid
        if isinstance(payload, dict) and "result" in payload and "jsonrpc" in payload:
            payload = payload["result"]
        if isinstance(payload, dict) and payload.get("isError") is True:
            raise MCPUpstreamInvalid
        if isinstance(payload, dict) and isinstance(payload.get("content"), list):
            texts = [item.get("text") for item in payload["content"] if isinstance(item, dict)]
            if not texts or not isinstance(texts[0], str):
                raise MCPUpstreamInvalid
            try:
                return json.loads(texts[0])
            except ValueError as error:
                raise MCPUpstreamInvalid from error
        return payload

    @staticmethod
    def _unavailable(request_id: str) -> JSONResponse:
        return MCPGatewayService._error(request_id, 403, "resource_unavailable", False)

    @staticmethod
    def _error(request_id: str, status: int, code: str, retryable: bool) -> JSONResponse:
        return JSONResponse(
            {
                "error": {"code": code, "message": code.replace("_", " ").capitalize() + "."},
                "request_id": request_id,
                "retryable": retryable,
            },
            status_code=status,
        )

    async def _audited(
        self,
        request_id: UUID,
        started: float,
        response: JSONResponse,
        *,
        operation: str,
        stage: str,
        context: PrincipalContext | None = None,
        evaluation: AuthorizationEvaluation | None = None,
        server_id: str = MCP_SERVER_ID,
        tool_id: str | None = None,
        reason: str | None = None,
    ) -> JSONResponse:
        if self.audit is None:
            return response
        try:
            if self.projector is None:
                event = MCPAuditRecord(
                    operation=operation,
                    request_id=request_id,
                    status=response.status_code,
                    server_id=server_id,
                    tool_id=tool_id,
                    principal_kind=context.principal.kind if context else None,
                    decision=evaluation.decision.decision if evaluation else None,
                    latency_ms=max(0, int((monotonic() - started) * 1000)),
                )
            else:
                event = self.projector.mcp_event(
                    request_id,
                    response.status_code,
                    max(0, int((monotonic() - started) * 1000)),
                    stage,
                    operation=operation,
                    context=context,
                    decision=evaluation.decision if evaluation else None,
                    authorization_denial_cause=(evaluation.denial_cause if evaluation else None),
                    resource_ref=("mcp_tool", tool_id) if tool_id else ("mcp_server", server_id),
                    reason=reason,
                )
            await self.audit.append(event)
        except Exception:
            return JSONResponse(
                {
                    "error": {"code": "audit_unavailable", "message": "Audit unavailable."},
                    "request_id": str(request_id),
                    "retryable": True,
                },
                status_code=503,
            )
        return response
