import os
from datetime import UTC, datetime

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from sre_agent.governance.dto import MCPServer, MCPTool
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import MCPOwnerRepository

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


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
    command.upgrade(config, "20260822_01")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO audit_events (
              event_id, occurred_at, operation, action, stage, outcome, reason_code,
              response_status, retryable, correlation, redaction, content_state,
              authoritative_acceptance, ordinary_result, exporter_result)
            VALUES ('00000000-0000-4000-8000-000000000000', now(), 'audit.accept',
              'persist', 'audit', 'success', NULL, 200, false, '{}', '{}', 'absent',
              'accepted', 'released', 'not_attempted')"""
        )
        connection.commit()
    command.upgrade(config, "head")


def server(server_id: str = "mcp-server", owner_id: str = "mcp-owner") -> MCPServer:
    return MCPServer(
        server_id=server_id,
        owner_id=owner_id,
        contract_version="1.0.0",
        status="registered",
        endpoint="http://grafana-mcp:8000/mcp",
        display_name="Grafana MCP",
        visibility="private",
        description="Governed Grafana MCP.",
        tags=["grafana", "mcp"],
        created_at=NOW,
        updated_at=NOW,
    )


def tool(
    tool_id: str = "query_prometheus",
    server_id: str = "mcp-server",
    owner_id: str = "mcp-owner",
) -> MCPTool:
    return MCPTool(
        tool_id=tool_id,
        server_id=server_id,
        owner_id=owner_id,
        contract_version="1.0.0",
        status="registered",
        upstream_name=tool_id,
        display_name=tool_id,
        visibility="private",
        description="Read-only Grafana data.",
        tags=["grafana", "mcp"],
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_owner_repository_registers_and_round_trips_relation() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        repository = MCPOwnerRepository(session)
        await repository.register_server(server())
        await repository.register_tool(tool())

    async with database.transaction() as session:
        repository = MCPOwnerRepository(session)
        stored_server = await repository.get_server("mcp-server")
        stored_tool = await repository.get_tool("query_prometheus")
        assert stored_server == server()
        assert stored_tool == tool()
        assert stored_tool is not None and stored_tool.server_id == stored_server.server_id
    await database.dispose()


@pytest.mark.asyncio
async def test_owner_repository_updates_and_deactivates_server_tools() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        repository = MCPOwnerRepository(session)
        await repository.register_server(server("mcp-updatable"))
        await repository.register_tool(tool("query-updatable", "mcp-updatable"))
        updated_server = await repository.update_server(
            "mcp-updatable", status="active", display_name="Governed Grafana"
        )
        updated_tool = await repository.update_tool(
            "query-updatable", status="active", display_name="Query Prometheus"
        )
        assert updated_server.status == "active"
        assert updated_tool.status == "active"

        inactive_server, inactive_tools = await repository.deactivate_server("mcp-updatable")
        assert inactive_server.status == "inactive"
        assert [item.status for item in inactive_tools] == ["inactive"]

    async with database.transaction() as session:
        repository = MCPOwnerRepository(session)
        assert (await repository.get_server("mcp-updatable")).status == "inactive"
        assert (await repository.get_tool("query-updatable")).status == "inactive"
    await database.dispose()


@pytest.mark.asyncio
async def test_owner_repository_rejects_missing_or_cross_owner_relations() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        repository = MCPOwnerRepository(session)
        await repository.register_server(server("mcp-related"))
        with pytest.raises(ValueError, match="server relation is absent"):
            await repository.register_tool(tool("missing-server", "mcp-missing"))
        with pytest.raises(ValueError, match="owner must match"):
            await repository.register_tool(tool("wrong-owner", "mcp-related", "other-owner"))
        with pytest.raises(ValueError, match="immutable"):
            await repository.update_server("mcp-related", owner_id="other-owner")
    await database.dispose()
