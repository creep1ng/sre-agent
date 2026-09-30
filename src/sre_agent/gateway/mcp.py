"""Governed gateway boundary for the two-tool Grafana MCP contract."""

import json
from asyncio import Lock, wait_for
from time import monotonic
from typing import Annotated, Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
    """A fixed-endpoint client; endpoint and token never come from a request.

    The client initializes one streamable-HTTP session lazily, never performs
    ``tools/list``, and sends exactly one ``tools/call`` RPC per gateway
    invocation. The contract's upstream counter counts that RPC, not the
    session's one-time ``initialize`` and ``notifications/initialized`` calls.
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
        self._client, self._endpoint, self._token = client, endpoint, token
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
            initialize_response = await self._post_rpc(
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
                isinstance(initialize_response, dict)
                and initialize_response.get("jsonrpc") == "2.0"
                and "error" not in initialize_response
                and isinstance(initialize_response.get("result"), dict)
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
                self._endpoint,
                headers=headers,
                json=request,
                timeout=self._timeout,
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
            # A notification commonly has an empty 202 response and is valid.
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
    """Test-friendly metadata projection used when no persistent projector is supplied."""

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
    """Authenticate, authorize, then consult owner state before any MCP call."""

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
        request_id, started = uuid4(), monotonic()
        operation = "mcp.discovery"
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, operation, "mcp_server", MCP_SERVER_ID
            )
        except AuthenticationFailed:
            return await self._finish(
                request_id, started, 401, operation, None, None, "authentication", MCP_SERVER_ID
            )
        if evaluation.decision.decision != "allow":
            return await self._finish(
                request_id,
                started,
                403,
                operation,
                context,
                evaluation,
                "authorization",
                MCP_SERVER_ID,
            )
        server, tools = await self._active_contract()
        if server is None or tools is None:
            return await self._finish(
                request_id,
                started,
                403,
                operation,
                context,
                evaluation,
                "authorization",
                MCP_SERVER_ID,
            )
        payload = {
            "contract_version": "1.0.0",
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
        return await self._finish(
            request_id,
            started,
            200,
            operation,
            context,
            evaluation,
            "response",
            MCP_SERVER_ID,
            payload=payload,
        )

    async def invoke(
        self, tool_id: str, raw: Any, authorization: str | None
    ) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        operation = "mcp.invoke"
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, operation, "mcp_tool", tool_id
            )
        except AuthenticationFailed:
            return await self._finish(
                request_id,
                started,
                401,
                operation,
                None,
                None,
                "authentication",
                MCP_SERVER_ID,
                tool_id,
            )
        if evaluation.decision.decision != "allow":
            return await self._finish(
                request_id,
                started,
                403,
                operation,
                context,
                evaluation,
                "authorization",
                MCP_SERVER_ID,
                tool_id,
            )
        server, tools = await self._active_contract(tool_id)
        tool = tools[0] if tools else None
        if server is None or tool is None:
            return await self._finish(
                request_id,
                started,
                403,
                operation,
                context,
                evaluation,
                "authorization",
                MCP_SERVER_ID,
                tool_id,
            )
        try:
            arguments = self._validate_input(tool_id, raw)
        except ValidationError:
            return await self._finish(
                request_id,
                started,
                422,
                operation,
                context,
                evaluation,
                "validation",
                MCP_SERVER_ID,
                tool_id,
                reason="contract_validation_failed",
            )
        try:
            upstream = await wait_for(
                self.client.call_tool(tool.upstream_name, arguments), MCP_TIMEOUT_SECONDS
            )
            payload = self._map_result(tool_id, upstream)
        except TimeoutError:
            return await self._finish(
                request_id,
                started,
                504,
                operation,
                context,
                evaluation,
                "upstream",
                MCP_SERVER_ID,
                tool_id,
                reason="upstream_timeout",
                retryable=True,
            )
        except MCPUpstreamTimeout:
            return await self._finish(
                request_id,
                started,
                504,
                operation,
                context,
                evaluation,
                "upstream",
                MCP_SERVER_ID,
                tool_id,
                reason="upstream_timeout",
                retryable=True,
            )
        except MCPUpstreamUnavailable:
            return await self._finish(
                request_id,
                started,
                503,
                operation,
                context,
                evaluation,
                "upstream",
                MCP_SERVER_ID,
                tool_id,
                reason="upstream_unavailable",
                retryable=True,
            )
        except MCPUpstreamInvalid:
            return await self._finish(
                request_id,
                started,
                502,
                operation,
                context,
                evaluation,
                "upstream",
                MCP_SERVER_ID,
                tool_id,
                reason="upstream_invalid",
            )
        return await self._finish(
            request_id,
            started,
            200,
            operation,
            context,
            evaluation,
            "response",
            MCP_SERVER_ID,
            tool_id,
            payload=payload,
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
                tools = []
                for governed_tool_id in MCP_TOOL_IDS:
                    tool = await owner.get_tool(governed_tool_id)
                    if (
                        tool is None
                        or tool.status != "active"
                        or tool.contract_version != MCP_CONTRACT_VERSION
                        or tool.server_id != server.server_id
                        or tool.owner_id != server.owner_id
                        or tool.tool_id != governed_tool_id
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
            result_type = result.get("resultType", "vector")
            if result_type not in {"matrix", "vector", "scalar", "string"}:
                raise MCPUpstreamInvalid
            try:
                return PrometheusResult(
                    result_type=result_type,
                    result=result["result"],
                    warnings=result.get("warnings", []),
                ).model_dump(mode="json")
            except ValidationError as error:
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
                payload = json.loads(texts[0])
            except ValueError as error:
                raise MCPUpstreamInvalid from error
        return payload

    async def _finish(
        self,
        request_id: UUID,
        started: float,
        status: int,
        operation: str,
        context: PrincipalContext | None,
        evaluation: AuthorizationEvaluation | None,
        stage: str,
        server_id: str,
        tool_id: str | None = None,
        *,
        payload: dict[str, Any] | None = None,
        reason: str | None = None,
        retryable: bool = False,
    ) -> JSONResponse:
        audit_recorded = await self._record(
            request_id,
            started,
            status,
            operation,
            context,
            evaluation,
            stage,
            server_id,
            tool_id,
            reason,
            retryable,
        )
        if not audit_recorded:
            return JSONResponse(
                {
                    "error": {
                        "code": "audit_unavailable",
                        "message": "Audit unavailable.",
                    },
                    "request_id": str(request_id),
                    "retryable": True,
                },
                status_code=503,
            )
        if payload is not None:
            return JSONResponse(payload, status_code=status)
        code, message = {
            401: ("authentication_failed", "Authentication failed."),
            403: ("resource_unavailable", "Resource unavailable."),
            422: ("contract_validation_failed", "Request validation failed."),
            502: ("upstream_invalid", "Upstream response was invalid."),
            503: (
                "audit_unavailable" if reason == "audit_unavailable" else "upstream_unavailable",
                "Audit unavailable."
                if reason == "audit_unavailable"
                else "Upstream provider unavailable.",
            ),
            504: ("upstream_timeout", "Upstream provider timed out."),
        }[status]
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return JSONResponse(
            {
                "error": {"code": code, "message": message},
                "request_id": str(request_id),
                "retryable": retryable,
            },
            status_code=status,
            headers=headers,
        )

    async def _record(
        self,
        request_id: UUID,
        started: float,
        status: int,
        operation: str,
        context: PrincipalContext | None,
        evaluation: AuthorizationEvaluation | None,
        stage: str,
        server_id: str,
        tool_id: str | None,
        reason: str | None,
        retryable: bool,
    ) -> bool:
        if self.audit is None:
            return False
        latency_ms = max(0, int((monotonic() - started) * 1000))
        try:
            if self.projector is not None:
                event = self.projector.mcp_event(
                    request_id,
                    status,
                    latency_ms,
                    stage,
                    operation=operation,
                    context=context,
                    decision=evaluation.decision if evaluation else None,
                    resource_ref=("mcp_tool", tool_id) if tool_id else ("mcp_server", server_id),
                    reason=reason,
                    retryable=retryable,
                )
            else:
                event = MCPAuditRecord(
                    operation=operation,
                    request_id=request_id,
                    status=status,
                    server_id=server_id,
                    tool_id=tool_id,
                    principal_kind=context.principal.kind if context else None,
                    decision=evaluation.decision.decision if evaluation else None,
                    latency_ms=latency_ms,
                )
            await self.audit.append(event)
        except Exception:
            # Audit contents are never allowed to carry arguments or results;
            # an audit sink failure suppresses the ordinary result.
            return False
        return True


def mcp_router(service: MCPGatewayService) -> APIRouter:
    router = APIRouter()
    bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")

    @router.get(
        "/v1/mcp/discovery",
        responses={
            401: {"description": "Authentication failed."},
            403: {"description": "Resource unavailable."},
        },
        openapi_extra={
            "x-governed-scope": {
                "action": "mcp.discovery",
                "resource_type": "mcp_server",
                "resource_id": MCP_SERVER_ID,
            }
        },
    )
    async def discovery(
        request: Request,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)] = None,
    ) -> JSONResponse:
        return await service.discovery(request.headers.get("authorization"))

    @router.post(
        "/v1/mcp/tools/{tool_id}",
        responses={403: {"description": "Resource unavailable."}},
        openapi_extra={
            "x-governed-scope": {
                "action": "mcp.invoke",
                "resource_type": "mcp_tool",
                "resource_id": "path.tool_id",
            },
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
        },
    )
    async def invoke(
        request: Request,
        tool_id: str,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)] = None,
    ) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.invoke(tool_id, body, request.headers.get("authorization"))

    return router
