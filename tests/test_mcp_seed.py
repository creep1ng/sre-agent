"""PostgreSQL evidence for the idempotent governed MCP demo bootstrap."""

import os
from datetime import UTC, datetime

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from sre_agent.persistence.database import Database
from sre_agent.persistence.models import (
    GrantRow,
    MCPServerRow,
    MCPToolRow,
    ResourceRow,
)
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
