"""PostgreSQL evidence for the idempotent governed MCP demo bootstrap."""

import json
import os
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from sre_agent.gateway import mcp
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import PostgresAuditStore
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import Principal, PrincipalContext
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import (
    GrantRow,
    MCPServerRow,
    MCPToolRow,
    ResourceRow,
)
from sre_agent.persistence.repositories import GrantRepository, OwnerResourceFactReader
from sre_agent.persistence.seeds import MCP_DEMO_GRANTS, bootstrap_mcp_demo

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
SEED_TIME = datetime(2026, 9, 21, 12, tzinfo=UTC)


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, mcp_tools, mcp_servers, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO principals
            (principal_id, kind, display_name, status, created_at, updated_at)
            VALUES
            ('demo-human', 'human', 'Demo human', 'active', %s, %s),
            ('restricted-harness', 'agent', 'Restricted harness', 'active', %s, %s)""",
            (SEED_TIME, SEED_TIME, SEED_TIME, SEED_TIME),
        )
        connection.commit()


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_with_exact_owner_tools_and_grants() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        assert await bootstrap_mcp_demo(session) is True
    async with database.transaction() as session:
        assert await bootstrap_mcp_demo(session) is False
        server = await session.get(MCPServerRow, "grafana-mcp")
        tools = list((await session.scalars(select(MCPToolRow).order_by(MCPToolRow.tool_id))).all())
        resources = list(
            (
                await session.scalars(
                    select(ResourceRow).where(
                        ResourceRow.resource_type.in_(("mcp_server", "mcp_tool"))
                    )
                )
            ).all()
        )
        grants = list(
            (
                await session.scalars(
                    select(GrantRow).where(GrantRow.action.in_(("mcp.discovery", "mcp.invoke")))
                )
            ).all()
        )
    await database.dispose()

    assert server is not None and server.status == "active"
    assert server.endpoint == "http://grafana-mcp:8000/mcp"
    assert [(tool.tool_id, tool.upstream_name) for tool in tools] == [
        ("query_elasticsearch", "query_elasticsearch"),
        ("query_prometheus", "query_prometheus"),
    ]
    assert {(row.resource_type, row.resource_id) for row in resources} == {
        ("mcp_server", "grafana-mcp"),
        ("mcp_tool", "query_prometheus"),
        ("mcp_tool", "query_elasticsearch"),
    }
    assert {grant.grant_id for grant in grants} == {grant[0] for grant in MCP_DEMO_GRANTS}
    assert {grant.principal_id for grant in grants} == {"demo-human"}


@pytest.mark.asyncio
async def test_bootstrap_repairs_missing_and_stale_catalog_projection() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        server = await session.get(MCPServerRow, "grafana-mcp")
        tool = await session.get(MCPToolRow, "query_prometheus")
        assert server is not None and tool is not None
        server_projection = await session.get(ResourceRow, ("mcp_server", "grafana-mcp"))
        missing_projection = await session.get(ResourceRow, ("mcp_tool", "query_elasticsearch"))
        assert server_projection is not None and missing_projection is not None
        server_projection.status = "inactive"
        server_projection.owner_id = "stale-owner"
        missing_grant = await session.get(GrantRow, "grant-demo-human-mcp-query-elasticsearch")
        assert missing_grant is not None
        await session.delete(missing_grant)
        await session.delete(missing_projection)
        await session.flush()

    async with database.transaction() as session:
        assert await bootstrap_mcp_demo(session) is True
        server = await session.get(MCPServerRow, "grafana-mcp")
        tool = await session.get(MCPToolRow, "query_prometheus")
        server_projection = await session.get(ResourceRow, ("mcp_server", "grafana-mcp"))
        repaired_projection = await session.get(ResourceRow, ("mcp_tool", "query_elasticsearch"))
    await database.dispose()

    assert server is not None and server.status == "active"
    assert tool is not None and tool.status == "active"
    assert server_projection is not None
    assert server_projection.status == "active"
    assert server_projection.owner_id == "mcp-platform"
    assert repaired_projection is not None
    assert repaired_projection.status == "active"


@pytest.mark.asyncio
async def test_governed_discovery_uses_real_owner_and_direct_grants_per_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        await bootstrap_mcp_demo(session)
        session.add_all(
            [
                GrantRow(
                    grant_id=f"issue29-restricted-{resource_type}",
                    principal_id="restricted-harness",
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    effect="allow",
                    status="active",
                    created_at=SEED_TIME,
                )
                for action, resource_type, resource_id in (
                    ("mcp.discovery", "mcp_server", "grafana-mcp"),
                    ("mcp.invoke", "mcp_tool", "query_prometheus"),
                )
            ]
        )

    async def authorize(
        sessions: Any,
        authorization: str | None,
        action: str,
        resource_type: str,
        resource_id: str,
    ) -> Any:
        principal_id = {
            "Bearer full": "demo-human",
            "Bearer partial": "restricted-harness",
        }[authorization]
        principal = Principal(
            principal_id=principal_id,
            kind="human" if principal_id == "demo-human" else "agent",
            display_name=principal_id,
            status="active",
            created_at=SEED_TIME,
            updated_at=SEED_TIME,
        )
        context = PrincipalContext(
            principal=principal,
            credential_id="issue29-test-credential",
            authenticated_at=SEED_TIME,
        )
        async with sessions() as session:
            decision = await AuthorizationDecisionEngine(
                OwnerResourceFactReader(session), GrantRepository(session)
            ).evaluate(principal, action, resource_type, resource_id)
        return context, decision

    class NoUpstream:
        calls = 0

        async def call_tool(self, *_args: Any) -> Any:
            self.calls += 1
            raise AssertionError("discovery must not call upstream")

    monkeypatch.setattr(mcp, "authorize_governed_access", authorize)
    upstream = NoUpstream()
    audit = PostgresAuditStore(database.sessions)
    service = mcp.MCPGatewayService(
        database.sessions, upstream, audit=audit, projector=AuditProjector(b"issue29-test-key")
    )
    full = await service.discovery("Bearer full")
    partial = await service.discovery("Bearer partial")
    async with database.transaction() as session:
        grant = await session.get(GrantRow, "issue29-restricted-mcp_tool")
        assert grant is not None
        grant.status = "revoked"
    empty = await service.discovery("Bearer partial")
    await database.dispose()

    assert [response.status_code for response in (full, partial, empty)] == [200, 200, 200]
    assert [
        [tool["tool_id"] for tool in json.loads(response.body)["tools"]]
        for response in (full, partial, empty)
    ] == [
        ["query_prometheus", "query_elasticsearch"],
        ["query_prometheus"],
        [],
    ]
    assert "query_elasticsearch" not in partial.body.decode()
    assert upstream.calls == 0
    with psycopg.connect(DATABASE_URL) as connection:
        persisted = connection.execute(
            "SELECT correlation->>'request_id', response_status, "
            "identity->'principal_ref'->>'digest', "
            "resource->'resource_ref'->>'digest', "
            "policy_decision->>'decision', content_state, "
            "COALESCE(jsonb_typeof(redacted_content), 'null') = 'null' "
            "FROM audit_events WHERE operation = 'mcp.discovery'"
        ).fetchall()
    assert {row[0] for row in persisted} == {
        json.loads(response.body)["request_id"] for response in (full, partial, empty)
    }
    assert all(
        status == 200
        and len(principal_digest) == 64
        and len(resource_digest) == 64
        and decision == "allow"
        and content_state == "absent"
        and no_content
        for (
            _,
            status,
            principal_digest,
            resource_digest,
            decision,
            content_state,
            no_content,
        ) in persisted
    )
