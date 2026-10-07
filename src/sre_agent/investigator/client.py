"""Gateway ports over HTTP with a gateway principal key: `POST {base_url}/v1/responses`,
`GET {base_url}/v1/skills/{skill_id}/{version}/resolve` (issue #32) and
`POST {base_url}/v1/bok/collections/{collection_id}/versions/{version}/search` (issue #34).

The client holds no provider or MCP secret. It reads the part of each contract it uses with
its own models, so the investigator never imports gateway code.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from sre_agent.investigator.ports import BoKFragment, GatewayError, GatewayReply, ResolvedSkill

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


class _Fragment(BaseModel):
    """A search result as #332 serves it; the loop checks its version and locator."""

    collection_id: str
    version: str
    document_id: str
    section_id: str
    chunk_index: int
    title: str
    source_ref: str
    content: str


class _Search(BaseModel):
    results: list[_Fragment]


class _Code(BaseModel):
    code: Annotated[str, Field(pattern=r"^[a-z_]{1,64}$")]


class _Failure(BaseModel):
    error: _Code


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
            raise GatewayError("denied", status)
        if status >= 500:
            raise GatewayError("transient", status)
        if status != 200:
            raise GatewayError("rejected", status)
        try:
            reply = _Response.model_validate_json(response.content)
        except ValidationError:
            raise GatewayError("rejected", status) from None
        text = "\n".join(part.text for message in reply.output for part in message.content)
        return GatewayReply(text=text, request_id=reply.request_id)

    async def resolve(self, skill_id: str, version: str) -> ResolvedSkill:
        """One exact Skill version and its direct dependencies, as the gateway authorizes them.

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
        if status in (401, 403, 404):
            raise GatewayError("denied", status)
        if status >= 500:
            raise GatewayError("transient", status)
        if status != 200:
            raise GatewayError("rejected", status)
        try:
            body = _Resolution.model_validate_json(response.content)
        except ValidationError:
            raise GatewayError("rejected", status) from None
        pinned = [(item.skill_id, item.version) for item in body.skill.manifest.dependencies]
        served = [(item.skill_id, item.version) for item in body.dependencies]
        if (
            (body.skill.skill_id, body.skill.version) != (skill_id, version)
            or served != pinned
            or any(item.manifest.dependencies for item in body.dependencies)
        ):
            raise GatewayError("rejected", status)
        dependencies = [_skill(item, body.request_id) for item in body.dependencies]
        return _skill(body.skill, body.request_id, *dependencies)

    async def search(
        self, collection_id: str, version: str, query: str, limit: int
    ) -> list[BoKFragment]:
        """One search in an exact BoK collection version, classified as `BoKSource` says."""
        headers = {"Authorization": f"Bearer {self._settings.api_key.get_secret_value()}"}
        url = f"{self._settings.base_url.rstrip('/')}/v1/bok/collections/{collection_id}"
        body = {"query": query, "limit": limit}
        try:
            response = await self._http.post(
                f"{url}/versions/{version}/search", json=body, headers=headers
            )
        except httpx.TimeoutException:
            raise GatewayError("transient", code="timeout") from None
        except httpx.HTTPError:
            raise GatewayError("transient", code="network") from None
        status = response.status_code
        if status in (401, 403):
            raise GatewayError("denied", status)
        if status >= 500:
            try:
                code: str | None = _Failure.model_validate_json(response.content).error.code
            except ValidationError:
                code = None
            raise GatewayError("transient", status, code=code)
        if status != 200:
            raise GatewayError("rejected", status)
        try:
            found = _Search.model_validate_json(response.content)
        except ValidationError:
            raise GatewayError("rejected", status) from None
        return [BoKFragment(**item.model_dump()) for item in found.results]

    async def aclose(self) -> None:
        await self._http.aclose()
