"""Ports of the investigator loop: the gateway, its Skills and the evidence provider (ADR-007)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from pydantic import JsonValue


@dataclass(frozen=True)
class GatewayReply:
    text: str
    request_id: UUID


class GatewayError(Exception):
    """No answer: `denied` (401, 403), `transient` (network, timeout, 5xx) or `rejected`;
    `code` keeps the producer's reason when there is one, such as `index_unavailable`."""

    def __init__(
        self,
        kind: Literal["denied", "transient", "rejected"],
        status: int | None = None,
        detail: str | None = None,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(detail or f"gateway {kind}" + (f" ({status})" if status else ""))
        self.kind = kind
        self.status = status
        self.code = code


class Gateway(Protocol):
    async def respond(
        self, *, input: str, incident_id: str, run_id: str, task_id: str
    ) -> GatewayReply: ...


@dataclass(frozen=True)
class ResolvedSkill:
    """One exact Skill version the gateway authorized, with its direct dependencies."""

    skill_id: str
    version: str
    content_sha256: str
    display_name: str
    instructions: str
    dependencies: tuple[ResolvedSkill, ...]
    request_id: UUID

    @property
    def ref(self) -> str:
        return f"{self.skill_id}@{self.version}"


class SkillSource(Protocol):
    """Raises GatewayError: `denied` for 401, 403 and the producer's non-enumerable 404."""

    async def resolve(self, skill_id: str, version: str) -> ResolvedSkill: ...


@dataclass(frozen=True)
class BoKFragment:
    """One chunk a BoK search returned (issue #34), with the locator that reads it again."""

    collection_id: str
    version: str
    document_id: str
    section_id: str
    chunk_index: int
    title: str
    source_ref: str
    content: str


class BoKSource(Protocol):
    """Raises GatewayError: `denied` for 401 and 403, `transient` for a 5xx, network error or
    timeout, with the producer's reason in `code`, and `rejected` for any other answer."""

    async def search(
        self, collection_id: str, version: str, query: str, limit: int
    ) -> list[BoKFragment]: ...


@dataclass(frozen=True)
class ToolResult:
    source: str
    summary: str
    datasource_uid: str | None = None
    query: str | None = None
    time_window: str | None = None


class EvidenceUnavailable(Exception):
    """The provider could not serve the requested tool."""


class EvidenceProvider(Protocol):
    async def collect(self, tool: str, arguments: Mapping[str, JsonValue]) -> ToolResult: ...
