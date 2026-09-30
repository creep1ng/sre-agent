"""Owner-issued MCP identities and catalog projection contract (#187 T2)."""

from datetime import UTC, datetime

import pytest

from sre_agent.governance.dto import MCPServer, MCPTool, ResourceCatalogEntry
from sre_agent.mcp.owner import (
    MCP_CONTRACT_VERSION,
    MCP_SERVER_ID,
    MCP_TOOL_IDS,
    MCPRegistry,
)
from sre_agent.persistence.repositories import CatalogRepository

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


class MemoryOwnerStore:
    def __init__(self) -> None:
        self.servers: dict[str, MCPServer] = {}
        self.tools: dict[str, MCPTool] = {}

    async def get_server(self, server_id: str) -> MCPServer | None:
        return self.servers.get(server_id)

    async def get_tool(self, tool_id: str) -> MCPTool | None:
        return self.tools.get(tool_id)

    async def register_server(self, server: MCPServer) -> MCPServer:
        if server.server_id in self.servers:
            raise ValueError("server already registered")
        self.servers[server.server_id] = server
        return server

    async def update_server(self, server_id: str, **changes: object) -> MCPServer:
        current = self.servers[server_id]
        updated = current.model_copy(update={**changes, "updated_at": NOW})
        self.servers[server_id] = updated
        return updated

    async def deactivate_server(self, server_id: str) -> tuple[MCPServer, list[MCPTool]]:
        server = await self.update_server(server_id, status="inactive")
        tools = []
        for tool in self.tools.values():
            if tool.server_id == server_id:
                tools.append(await self.update_tool(tool.tool_id, status="inactive"))
        return server, tools

    async def register_tool(self, tool: MCPTool) -> MCPTool:
        if tool.server_id not in self.servers:
            raise ValueError("server relation is absent")
        if tool.tool_id in self.tools:
            raise ValueError("tool already registered")
        self.tools[tool.tool_id] = tool
        return tool

    async def update_tool(self, tool_id: str, **changes: object) -> MCPTool:
        current = self.tools[tool_id]
        updated = current.model_copy(update={**changes, "updated_at": NOW})
        self.tools[tool_id] = updated
        return updated


class MemoryCatalogProjection:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], ResourceCatalogEntry] = {}

    async def project_mcp_server(self, server: MCPServer) -> ResourceCatalogEntry:
        entry = ResourceCatalogEntry(
            resource_type="mcp_server",
            resource_id=server.server_id,
            owner_id=server.owner_id,
            status=server.status,
            source="mcp",
            source_ref=f"mcp-owner/{server.server_id}",
            discoverability=server.discoverability,
        )
        self.entries[(entry.resource_type, entry.resource_id)] = entry
        return entry

    async def project_mcp_tool(self, tool: MCPTool) -> ResourceCatalogEntry:
        entry = ResourceCatalogEntry(
            resource_type="mcp_tool",
            resource_id=tool.tool_id,
            owner_id=tool.owner_id,
            status=tool.status,
            source="mcp",
            source_ref=f"mcp-owner/{tool.server_id}/{tool.tool_id}",
            discoverability=tool.discoverability,
        )
        self.entries[(entry.resource_type, entry.resource_id)] = entry
        return entry


class ProjectionSession:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], object] = {}

    async def get(self, _model: object, key: tuple[str, str]) -> object | None:
        return self.rows.get(key)

    def add(self, row: object) -> None:
        self.rows[(row.resource_type, row.resource_id)] = row  # type: ignore[attr-defined]

    async def flush(self) -> None:
        return None


def _registry() -> tuple[MCPRegistry, MemoryOwnerStore, MemoryCatalogProjection]:
    owner = MemoryOwnerStore()
    catalog = MemoryCatalogProjection()
    return MCPRegistry(owner, catalog), owner, catalog


@pytest.mark.asyncio
async def test_owner_registers_exact_contract_and_projects_relation() -> None:
    registry, owner, catalog = _registry()

    server = await registry.register_server(
        {
            "server_id": MCP_SERVER_ID,
            "owner_id": "mcp-platform",
            "contract_version": MCP_CONTRACT_VERSION,
            "status": "active",
            "endpoint": "http://grafana-mcp:8000/mcp",
            "display_name": "Grafana MCP",
            "visibility": "private",
            "description": "Governed Grafana read-only MCP.",
            "tags": ["grafana", "mcp"],
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    tool = await registry.register_tool(
        {
            "tool_id": "query_prometheus",
            "server_id": server.server_id,
            "owner_id": server.owner_id,
            "contract_version": MCP_CONTRACT_VERSION,
            "status": "active",
            "upstream_name": "query_prometheus",
            "display_name": "Query Prometheus",
            "visibility": "private",
            "description": "Read Prometheus metrics.",
            "tags": ["grafana", "prometheus"],
            "created_at": NOW,
            "updated_at": NOW,
        }
    )

    assert server.server_id == MCP_SERVER_ID
    assert tool.server_id == server.server_id
    assert set(owner.tools) == {"query_prometheus"}
    assert catalog.entries[("mcp_server", MCP_SERVER_ID)].source_ref == (
        "mcp-owner/grafana-mcp"
    )
    assert catalog.entries[("mcp_tool", "query_prometheus")].owner_id == "mcp-platform"


@pytest.mark.asyncio
async def test_catalog_repository_exposes_owner_projection_methods() -> None:
    session = ProjectionSession()
    repository = CatalogRepository(session)  # type: ignore[arg-type]
    server = MCPServer(
        server_id=MCP_SERVER_ID,
        owner_id="mcp-platform",
        contract_version=MCP_CONTRACT_VERSION,
        status="active",
        endpoint="http://grafana-mcp:8000/mcp",
        display_name="Grafana MCP",
        visibility="private",
        description="",
        tags=[],
        created_at=NOW,
        updated_at=NOW,
    )
    tool = MCPTool(
        tool_id="query_prometheus",
        server_id=MCP_SERVER_ID,
        owner_id="mcp-platform",
        contract_version=MCP_CONTRACT_VERSION,
        status="active",
        upstream_name="query_prometheus",
        display_name="Prometheus",
        visibility="private",
        description="",
        tags=[],
        created_at=NOW,
        updated_at=NOW,
    )

    server_entry = await repository.project_mcp_server(server)
    tool_entry = await repository.project_mcp_tool(tool)

    assert server_entry.source_ref == "mcp-owner/grafana-mcp"
    assert tool_entry.source_ref == "mcp-owner/grafana-mcp/query_prometheus"


@pytest.mark.asyncio
async def test_owner_rejects_unknown_tool_and_server_mismatch_without_projection() -> None:
    registry, owner, catalog = _registry()
    with pytest.raises(ValueError, match="outside the governed contract"):
        await registry.register_tool(
            {
                "tool_id": "list_datasources",
                "server_id": MCP_SERVER_ID,
                "owner_id": "mcp-platform",
                "contract_version": MCP_CONTRACT_VERSION,
                "status": "active",
                "upstream_name": "list_datasources",
                "display_name": "Not governed",
                "visibility": "private",
                "description": "",
                "tags": [],
                "created_at": NOW,
                "updated_at": NOW,
            }
        )
    assert not owner.tools
    assert not catalog.entries
    assert set(MCP_TOOL_IDS) == {"query_prometheus", "query_elasticsearch"}


@pytest.mark.asyncio
async def test_server_deactivation_deactivates_tools_and_projection() -> None:
    registry, _owner, catalog = _registry()
    await registry.register_server(
        {
            "server_id": MCP_SERVER_ID,
            "owner_id": "mcp-platform",
            "contract_version": MCP_CONTRACT_VERSION,
            "status": "active",
            "endpoint": "http://grafana-mcp:8000/mcp",
            "display_name": "Grafana MCP",
            "visibility": "private",
            "description": "",
            "tags": [],
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    for tool_id in MCP_TOOL_IDS:
        await registry.register_tool(
            {
                "tool_id": tool_id,
                "server_id": MCP_SERVER_ID,
                "owner_id": "mcp-platform",
                "contract_version": MCP_CONTRACT_VERSION,
                "status": "active",
                "upstream_name": tool_id,
                "display_name": tool_id,
                "visibility": "private",
                "description": "",
                "tags": [],
                "created_at": NOW,
                "updated_at": NOW,
            }
        )

    await registry.deactivate_server(MCP_SERVER_ID)

    assert catalog.entries[("mcp_server", MCP_SERVER_ID)].status == "inactive"
    assert all(
        catalog.entries[("mcp_tool", tool_id)].status == "inactive" for tool_id in MCP_TOOL_IDS
    )


@pytest.mark.asyncio
async def test_updates_are_owner_first_and_identity_is_immutable() -> None:
    registry, owner, catalog = _registry()
    await registry.register_server(
        {
            "server_id": MCP_SERVER_ID,
            "owner_id": "mcp-platform",
            "contract_version": MCP_CONTRACT_VERSION,
            "status": "registered",
            "endpoint": "http://grafana-mcp:8000/mcp",
            "display_name": "Grafana MCP",
            "visibility": "private",
            "description": "",
            "tags": [],
            "created_at": NOW,
            "updated_at": NOW,
        }
    )

    updated = await registry.update_server(
        MCP_SERVER_ID,
        status="active",
        display_name="Grafana MCP (governed)",
    )

    assert owner.servers[MCP_SERVER_ID].display_name == "Grafana MCP (governed)"
    assert catalog.entries[("mcp_server", MCP_SERVER_ID)].status == "active"
    assert catalog.entries[("mcp_server", MCP_SERVER_ID)].discoverability.display_name == (
        updated.display_name
    )
    with pytest.raises(ValueError, match="identity is immutable"):
        await registry.update_server(MCP_SERVER_ID, owner_id="spoofed-owner")

    before = owner.servers[MCP_SERVER_ID]
    with pytest.raises(ValueError, match="invalid MCP server registration"):
        await registry.update_server(MCP_SERVER_ID, status="not-a-lifecycle-state")
    assert owner.servers[MCP_SERVER_ID] == before

    with pytest.raises(ValueError, match="unknown MCP server field"):
        await registry.update_server(MCP_SERVER_ID, unexpected="must-be-rejected")
    assert owner.servers[MCP_SERVER_ID] == before


@pytest.mark.asyncio
async def test_tool_update_and_deactivation_keep_the_server_relation() -> None:
    registry, owner, catalog = _registry()
    await registry.register_server(
        {
            "server_id": MCP_SERVER_ID,
            "owner_id": "mcp-platform",
            "contract_version": MCP_CONTRACT_VERSION,
            "status": "active",
            "endpoint": "http://grafana-mcp:8000/mcp",
            "display_name": "Grafana MCP",
            "visibility": "private",
            "description": "",
            "tags": [],
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    await registry.register_tool(
        {
            "tool_id": "query_prometheus",
            "server_id": MCP_SERVER_ID,
            "owner_id": "mcp-platform",
            "contract_version": MCP_CONTRACT_VERSION,
            "status": "registered",
            "upstream_name": "query_prometheus",
            "display_name": "Prometheus",
            "visibility": "private",
            "description": "",
            "tags": [],
            "created_at": NOW,
            "updated_at": NOW,
        }
    )

    await registry.update_tool("query_prometheus", status="active", display_name="Prometheus query")
    await registry.deactivate_tool("query_prometheus")

    assert owner.tools["query_prometheus"].server_id == MCP_SERVER_ID
    assert catalog.entries[("mcp_tool", "query_prometheus")].status == "inactive"
    assert catalog.entries[("mcp_tool", "query_prometheus")].owner_id == "mcp-platform"

    with pytest.raises(ValueError, match="identity is immutable"):
        await registry.update_tool("query_prometheus", upstream_name="spoofed-tool")
    assert owner.tools["query_prometheus"].upstream_name == "query_prometheus"

    before = owner.tools["query_prometheus"]
    with pytest.raises(ValueError, match="invalid MCP tool registration"):
        await registry.update_tool("query_prometheus", status="not-a-lifecycle-state")
    assert owner.tools["query_prometheus"] == before
    with pytest.raises(ValueError, match="unknown MCP tool field"):
        await registry.update_tool("query_prometheus", unexpected="must-be-rejected")
    assert owner.tools["query_prometheus"] == before
