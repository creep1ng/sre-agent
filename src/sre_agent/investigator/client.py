"""Gateway ports over HTTP with a gateway principal key: `POST {base_url}/v1/responses` and
`GET {base_url}/v1/skills/{skill_id}/{version}/resolve` (issue #32).

The client holds no provider or MCP secret. It reads the part of each contract it uses with
its own models, so the investigator never imports gateway code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import UUID

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    SecretStr,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from sre_agent.investigator.contract import Capability
from sre_agent.investigator.ports import (
    EvidenceUnavailable,
    GatewayError,
    GatewayReply,
    ResolvedSkill,
    ToolResult,
)

URL = "INVESTIGATOR_GATEWAY_URL"
KEY = "INVESTIGATOR_GATEWAY_API_KEY"
ALIAS = "INVESTIGATOR_MODEL_ALIAS"


class GatewaySettings(BaseModel):
    """The three values that connect the harness to the gateway, and nothing else."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: Annotated[str, Field(pattern=r"^https?://[^\s/]+(/[^\s]*)?$")]
    api_key: SecretStr
    model_alias: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    timeout_seconds: Annotated[float, Field(gt=0, le=180)] = 45.0

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> GatewaySettings:
        missing = [name for name in (URL, KEY, ALIAS) if not environment.get(name)]
        if missing:
            raise ValueError("missing configuration: " + ", ".join(missing))
        return cls(
            base_url=environment[URL], api_key=environment[KEY], model_alias=environment[ALIAS]
        )


class _Text(BaseModel):
    type: Literal["output_text"]
    text: str


class _Message(BaseModel):
    type: Literal["message"]
    role: Literal["assistant"]
    content: Annotated[list[_Text], Field(min_length=1)]


class _Response(BaseModel):
    status: Literal["completed"]
    output: Annotated[list[_Message], Field(min_length=1)]
    request_id: UUID


class _Pinned(BaseModel):
    skill_id: str
    version: str


class _Manifest(BaseModel):
    display_name: str
    instructions: str
    dependencies: list[_Pinned]


class _SkillVersion(_Pinned):
    manifest: _Manifest
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _Resolution(BaseModel):
    skill: _SkillVersion
    dependencies: list[_SkillVersion]
    request_id: UUID


def _skill(item: _SkillVersion, request_id: UUID, *dependencies: ResolvedSkill) -> ResolvedSkill:
    return ResolvedSkill(
        item.skill_id, item.version, item.content_sha256, item.manifest.display_name,
        item.manifest.instructions, dependencies, request_id,
    )  # fmt: skip


class _Pinned(BaseModel):
    skill_id: str
    version: str


class _Manifest(BaseModel):
    display_name: str
    instructions: str
    dependencies: list[_Pinned]


class _SkillVersion(_Pinned):
    manifest: _Manifest
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _Resolution(BaseModel):
    skill: _SkillVersion
    dependencies: list[_SkillVersion]
    request_id: UUID


def _skill(item: _SkillVersion, request_id: UUID, *dependencies: ResolvedSkill) -> ResolvedSkill:
    return ResolvedSkill(
        item.skill_id, item.version, item.content_sha256, item.manifest.display_name,
        item.manifest.instructions, dependencies, request_id,
    )  # fmt: skip


class GatewayClient:
    def __init__(self, settings: GatewaySettings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=settings.timeout_seconds)

    async def respond(
        self, *, input: str, incident_id: str, run_id: str, task_id: str
    ) -> GatewayReply:
        body = {
            "model": self._settings.model_alias,
            "input": input,
            "incident_id": incident_id,
            "run_id": run_id,
            "task_id": task_id,
        }
        headers = {"Authorization": f"Bearer {self._settings.api_key.get_secret_value()}"}
        url = self._settings.base_url.rstrip("/") + "/v1/responses"
        try:
            response = await self._http.post(url, json=body, headers=headers)
        except httpx.HTTPError:
            raise GatewayError("transient") from None
        status = response.status_code
        if status in (401, 403):
            raise GatewayError("denied", status, request_id=_response_request_id(response))
        if status >= 500:
            raise GatewayError("transient", status, request_id=_response_request_id(response))
        if status != 200:
            raise GatewayError("rejected", status, request_id=_response_request_id(response))
        try:
            reply = _Response.model_validate_json(response.content)
        except ValidationError:
            raise GatewayError(
                "rejected", status, request_id=_response_request_id(response)
            ) from None
        text = "\n".join(part.text for message in reply.output for part in message.content)
        return GatewayReply(text=text, request_id=reply.request_id)

    async def resolve(self, skill_id: str, version: str) -> ResolvedSkill:
        """Resolve one exact Skill version and its authorized direct dependencies.

        The producer's single 404 (missing, inactive or not granted) is `denied`; a body that is
        not the version asked for, with exactly the dependencies it pins, is `rejected`.
        """
        headers = {"Authorization": f"Bearer {self._settings.api_key.get_secret_value()}"}
        url = f"{self._settings.base_url.rstrip('/')}/v1/skills/{skill_id}/{version}/resolve"
        try:
            response = await self._http.get(url, headers=headers)
        except httpx.HTTPError:
            raise GatewayError("transient") from None
        status = response.status_code
        request_id = _response_request_id(response)
        if status in (401, 403, 404):
            raise GatewayError("denied", status, request_id=request_id)
        if status >= 500:
            raise GatewayError("transient", status, request_id=request_id)
        if status != 200:
            raise GatewayError("rejected", status, request_id=request_id)
        try:
            body = _Resolution.model_validate_json(response.content)
        except ValidationError:
            raise GatewayError("rejected", status, request_id=request_id) from None
        pinned = [(item.skill_id, item.version) for item in body.skill.manifest.dependencies]
        served = [(item.skill_id, item.version) for item in body.dependencies]
        if (
            (body.skill.skill_id, body.skill.version) != (skill_id, version)
            or served != pinned
            or any(item.manifest.dependencies for item in body.dependencies)
        ):
            raise GatewayError("rejected", status, request_id=request_id)
        dependencies = [_skill(item, body.request_id) for item in body.dependencies]
        return _skill(body.skill, body.request_id, *dependencies)

    async def aclose(self) -> None:
        await self._http.aclose()


class _DiscoveryTool(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resource_type: Literal["mcp_tool"]
    tool_id: str
    action: Literal["mcp.invoke"]
    input_schema: dict[str, JsonValue]


class _Discovery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: UUID
    tools: list[_DiscoveryTool]


class _PrometheusResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    result_type: Literal["matrix", "vector", "scalar", "string", "indeterminate"]
    result: (
        Annotated[list[dict[str, Any]], Field(max_length=1000)]
        | tuple[
            StrictInt | FiniteFloat,
            Annotated[str, Field(strict=True, max_length=256)],
        ]
    )
    warnings: Annotated[
        list[Annotated[str, Field(strict=True, max_length=500)]], Field(max_length=16)
    ]

    @field_validator("result", mode="before")
    @classmethod
    def _parse_scalar_sample(cls, value: Any) -> Any:
        if (
            isinstance(value, list)
            and len(value) == 2
            and type(value[0]) in (int, float)
            and isinstance(value[1], str)
        ):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _result_type_matches_shape(self) -> _PrometheusResult:
        if isinstance(self.result, tuple):
            if self.result_type not in {"indeterminate", "scalar", "string"}:
                raise ValueError(
                    "scalar sample pairs require a scalar, string, or indeterminate type"
                )
        elif self.result_type not in {"matrix", "vector"}:
            raise ValueError("matrix and vector results require a list of objects")
        return self


class _ElasticsearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total: int
    documents: list[dict[str, Any]]
    warnings: list[str]


class MCPGatewayClient:
    """Use only the configured gateway identity and its currently visible tools."""

    def __init__(self, settings: GatewaySettings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=settings.timeout_seconds)

    async def discover(self) -> tuple[list[Capability], UUID]:
        response = await self._send("GET", "/v1/mcp/discovery")
        if response.status_code != 200:
            self._raise_error(response)
        try:
            discovery = _Discovery.model_validate(response.json())
        except (ValueError, ValidationError):
            raise EvidenceUnavailable(
                "MCP discovery response was invalid",
                kind="rejected",
                request_id=_response_request_id(response),
            ) from None
        return (
            [
                Capability(
                    resource_type=tool.resource_type,
                    resource_id=tool.tool_id,
                    action="invoke",
                    input_schema=tool.input_schema,
                )
                for tool in discovery.tools
            ],
            discovery.request_id,
        )

    async def collect(self, tool: str, arguments: Mapping[str, JsonValue]) -> ToolResult:
        response = await self._send("POST", f"/v1/mcp/tools/{tool}", json=dict(arguments))
        if response.status_code != 200:
            self._raise_error(response)
        try:
            payload = response.json()
            request_id = _mcp_response_request_id(response)
            if request_id is None:
                raise ValueError("MCP response correlation header is missing or invalid")
            if tool == "query_prometheus":
                prometheus_result = _PrometheusResult.model_validate_json(response.content)
                summary = prometheus_result.model_dump_json()
            elif tool == "query_elasticsearch":
                elasticsearch_result = _ElasticsearchResult.model_validate(payload)
                summary = elasticsearch_result.model_dump_json()
            else:
                raise ValueError("unsupported tool")
        except (ValueError, ValidationError):
            raise EvidenceUnavailable(
                "MCP tool response was invalid",
                kind="rejected",
                status=response.status_code,
                request_id=_mcp_response_request_id(response),
            ) from None
        datasource_uid = arguments.get("datasource_uid")
        query = arguments.get("expr", arguments.get("query"))
        start, end = arguments.get("start_time"), arguments.get("end_time")
        time_window = f"{start}/{end}" if start is not None else end
        return ToolResult(
            source="grafana-mcp",
            summary=summary[:8000] or "Governed MCP query returned an empty result.",
            datasource_uid=datasource_uid if isinstance(datasource_uid, str) else None,
            query=query if isinstance(query, str) else None,
            time_window=time_window if isinstance(time_window, str) else None,
            request_id=request_id,
        )

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = self._settings.base_url.rstrip("/") + path
        headers = {"Authorization": f"Bearer {self._settings.api_key.get_secret_value()}"}
        try:
            return await self._http.request(
                method, url, headers=headers, timeout=self._settings.timeout_seconds, **kwargs
            )
        except httpx.HTTPError:
            raise EvidenceUnavailable("MCP gateway transport failed", kind="transient") from None

    @staticmethod
    def _raise_error(response: httpx.Response) -> None:
        status = response.status_code
        kind: Literal["denied", "transient", "rejected"]
        if status in (401, 403):
            kind = "denied"
        elif status >= 500:
            kind = "transient"
        else:
            kind = "rejected"
        raise EvidenceUnavailable(
            "MCP gateway did not return a result",
            kind=kind,
            status=status,
            request_id=_response_request_id(response),
        )


def _response_request_id(response: httpx.Response) -> UUID | None:
    try:
        value = response.json().get("request_id")
        return UUID(value) if isinstance(value, str) else None
    except (AttributeError, ValueError):
        return None


def _mcp_response_request_id(response: httpx.Response) -> UUID | None:
    value = response.headers.get("X-Request-ID")
    try:
        return UUID(value) if value is not None else None
    except ValueError:
        return None
