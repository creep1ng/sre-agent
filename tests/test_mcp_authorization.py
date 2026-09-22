"""Owner-authoritative authorization facts for governed MCP resources."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from sre_agent.gateway import authentication
from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationDenialCause,
)
from sre_agent.governance.dto import Grant, Principal, PrincipalContext, Resource
from sre_agent.persistence.models import MCPServerRow, MCPToolRow, ResourceRow
from sre_agent.persistence.repositories import OwnerResourceFactReader

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


class MemorySession:
    def __init__(self, rows: dict[tuple[type[Any], str], Any]) -> None:
        self.rows = rows
        self.gets: list[tuple[type[Any], str]] = []

    async def get(self, model: type[Any], key: str) -> Any:
        self.gets.append((model, key))
        return self.rows.get((model, key))


class MemoryGrantReader:
    def __init__(self, grant: Grant) -> None:
        self.grant = grant

    async def find_active(
        self, principal_id: str, action: str, resource_type: str, resource_id: str
    ) -> Grant | None:
        resource = self.grant.resource
        if (
            self.grant.principal_id == principal_id
            and self.grant.action == action
            and resource.resource_type == resource_type
            and resource.resource_id == resource_id
        ):
            return self.grant
        return None


def _principal() -> Principal:
    return Principal(
        principal_id="demo-human",
        kind="human",
        display_name="Demo human",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def _grant(resource_type: str, resource_id: str) -> Grant:
    return Grant(
        grant_id="grant-demo-mcp",
        principal_id="demo-human",
        action="mcp.invoke",
        resource=Resource(resource_type=resource_type, resource_id=resource_id),
        effect="allow",
        status="active",
        created_at=NOW,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resource_type", "model", "resource_id", "owner_row"),
    [
        (
            "mcp_server",
            MCPServerRow,
            "grafana-mcp",
            SimpleNamespace(server_id="grafana-mcp", status="active"),
        ),
        (
            "mcp_tool",
            MCPToolRow,
            "query_prometheus",
            SimpleNamespace(tool_id="query_prometheus", status="active"),
        ),
    ],
)
async def test_active_owner_state_wins_over_inactive_catalog_shadow(
    resource_type: str,
    model: type[Any],
    resource_id: str,
    owner_row: Any,
) -> None:
    session = MemorySession(
        {
            (model, resource_id): owner_row,
            (ResourceRow, resource_id): SimpleNamespace(status="inactive"),
        }
    )
    evaluation = await AuthorizationDecisionEngine(
        OwnerResourceFactReader(session), MemoryGrantReader(_grant(resource_type, resource_id))
    ).evaluate(_principal(), "mcp.invoke", resource_type, resource_id)  # type: ignore[arg-type]

    assert evaluation.decision.decision == "allow"
    assert session.gets == [(model, resource_id)]


@pytest.mark.asyncio
async def test_inactive_owner_state_denies_even_with_active_catalog_shadow() -> None:
    resource_id = "grafana-mcp"
    session = MemorySession(
        {
            (MCPServerRow, resource_id): SimpleNamespace(server_id=resource_id, status="inactive"),
            (ResourceRow, resource_id): SimpleNamespace(status="active"),
        }
    )
    evaluation = await AuthorizationDecisionEngine(
        OwnerResourceFactReader(session), MemoryGrantReader(_grant("mcp_server", resource_id))
    ).evaluate(_principal(), "mcp.invoke", "mcp_server", resource_id)

    assert evaluation.decision.decision == "deny"
    assert evaluation.denial_cause == AuthorizationDenialCause.RESOURCE_INACTIVE
    assert session.gets == [(MCPServerRow, resource_id)]


@pytest.mark.asyncio
async def test_absent_owner_denies_even_when_catalog_row_exists() -> None:
    resource_id = "query_prometheus"
    session = MemorySession({(ResourceRow, resource_id): SimpleNamespace(status="active")})
    evaluation = await AuthorizationDecisionEngine(
        OwnerResourceFactReader(session), MemoryGrantReader(_grant("mcp_tool", resource_id))
    ).evaluate(_principal(), "mcp.invoke", "mcp_tool", resource_id)

    assert evaluation.decision.decision == "deny"
    assert evaluation.denial_cause == AuthorizationDenialCause.RESOURCE_MISSING
    assert session.gets == [(MCPToolRow, resource_id)]


@pytest.mark.asyncio
async def test_authorize_governed_access_uses_owner_reader_for_mcp_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []

    class CapturingEngine:
        def __init__(self, resources: Any, grants: Any) -> None:
            del grants
            captured.append(resources)

        async def evaluate(self, *_args: Any) -> object:
            return object()

    @asynccontextmanager
    async def sessions() -> Any:
        yield object()

    async def context(*_args: Any) -> PrincipalContext:
        return PrincipalContext(
            principal=_principal(), credential_id="credential-demo-human", authenticated_at=NOW
        )

    monkeypatch.setattr(authentication, "AuthorizationDecisionEngine", CapturingEngine)
    monkeypatch.setattr(authentication, "_authorization_context", context)

    await authentication.authorize_governed_access(
        sessions, "Bearer ignored", "mcp.invoke", "mcp_tool", "query_prometheus"
    )

    assert isinstance(captured[0], OwnerResourceFactReader)
