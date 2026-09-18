"""Ports of the investigator loop: the gateway and the evidence provider (ADR-007)."""

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
    """No model answer: `denied` (401, 403), `transient` (network, timeout, 5xx) or `rejected`."""

    def __init__(
        self, kind: Literal["denied", "transient", "rejected"], status: int | None = None
    ) -> None:
        super().__init__(f"gateway {kind}" + (f" ({status})" if status else ""))
        self.kind = kind
        self.status = status


class Gateway(Protocol):
    async def respond(
        self, *, input: str, incident_id: str, run_id: str, task_id: str
    ) -> GatewayReply: ...


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
