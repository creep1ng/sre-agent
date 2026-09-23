from datetime import UTC, datetime

import pytest

from sre_agent.governance.dto import MCPServer, MCPTool, ResourceCatalogEntry
from sre_agent.mcp.owner import MCP_CONTRACT_VERSION, MCP_SERVER_ID, MCP_TOOL_IDS, MCPRegistry

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


class MemoryOwner:
    def __init__(self) -> None:
        self.servers: dict[str, MCPServer] = {}
        self.tools: dict[str, MCPTool] = {}

    async def get_server(self, key: str) -> MCPServer | None:
        return self.servers.get(key)

    async def get_tool(self, key: str) -> MCPTool | None:
        return self.tools.get(key)

    async def register_server(self, value: MCPServer) -> MCPServer:
        self.servers[value.server_id] = value
        return value

    async def update_server(self, key: str, **changes: object) -> MCPServer:
        value = self.servers[key].model_copy(update={**changes, "updated_at": NOW})
        self.servers[key] = value
        return value

    async def deactivate_server(self, key: str) -> tuple[MCPServer, list[MCPTool]]:
        server = await self.update_server(key, status="inactive")
        tools = [
            await self.update_tool(tool.tool_id, status="inactive")
            for tool in tuple(self.tools.values())
            if tool.server_id == key
        ]
        return server, tools

    async def register_tool(self, value: MCPTool) -> MCPTool:
        self.tools[value.tool_id] = value
        return value

    async def update_tool(self, key: str, **changes: object) -> MCPTool:
        value = self.tools[key].model_copy(update={**changes, "updated_at": NOW})
        self.tools[key] = value
        return value


class MemoryCatalog:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], ResourceCatalogEntry] = {}

    async def project_mcp_server(self, value: MCPServer) -> ResourceCatalogEntry:
        entry = ResourceCatalogEntry(
            resource_type="mcp_server",
            resource_id=value.server_id,
            owner_id=value.owner_id,
            status=value.status,
            source="mcp",
            source_ref=f"mcp-owner/{value.server_id}",
            discoverability=value.discoverability,
        )
        self.entries[(entry.resource_type, entry.resource_id)] = entry
        return entry

    async def project_mcp_tool(self, value: MCPTool) -> ResourceCatalogEntry:
        entry = ResourceCatalogEntry(
            resource_type="mcp_tool",
            resource_id=value.tool_id,
            owner_id=value.owner_id,
            status=value.status,
            source="mcp",
            source_ref=f"mcp-owner/{value.server_id}/{value.tool_id}",
            discoverability=value.discoverability,
        )
        self.entries[(entry.resource_type, entry.resource_id)] = entry
        return entry


def _server(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "server_id": MCP_SERVER_ID,
        "owner_id": "mcp-platform",
        "contract_version": MCP_CONTRACT_VERSION,
        "status": "registered",
        "endpoint": "http://grafana-mcp:8000/mcp",
        "display_name": "Grafana MCP",
        "visibility": "private",
        "description": "Governed Grafana MCP.",
        "tags": ["grafana", "mcp"],
        "created_at": NOW,
        "updated_at": NOW,
    }
    value.update(changes)
    return value


def _tool(tool_id: str = "query_prometheus", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "tool_id": tool_id,
        "server_id": MCP_SERVER_ID,
        "owner_id": "mcp-platform",
        "contract_version": MCP_CONTRACT_VERSION,
        "status": "registered",
        "upstream_name": tool_id,
        "display_name": tool_id,
        "visibility": "private",
        "description": "Read-only Grafana data.",
        "tags": ["grafana", "mcp"],
        "created_at": NOW,
        "updated_at": NOW,
    }
    value.update(changes)
    return value


def _registry() -> tuple[MCPRegistry, MemoryOwner, MemoryCatalog]:
    owner = MemoryOwner()
    catalog = MemoryCatalog()
    return MCPRegistry(owner, catalog), owner, catalog


@pytest.mark.asyncio
async def test_registration_projects_server_tool_relation_and_provenance() -> None:
    registry, owner, catalog = _registry()
    server = await registry.register_server(_server(status="active"))
    tool = await registry.register_tool(_tool(server_id=server.server_id, owner_id=server.owner_id))

    assert owner.tools[tool.tool_id].server_id == MCP_SERVER_ID
    assert catalog.entries[("mcp_server", MCP_SERVER_ID)].source_ref == ("mcp-owner/grafana-mcp")
    assert catalog.entries[("mcp_tool", tool.tool_id)].owner_id == "mcp-platform"


@pytest.mark.asyncio
async def test_updates_are_owner_first_and_identity_is_immutable() -> None:
    registry, owner, catalog = _registry()
    await registry.register_server(_server(status="registered"))
    await registry.register_tool(_tool())

    await registry.update_server(MCP_SERVER_ID, status="active", display_name="Governed Grafana")
    await registry.update_tool("query_prometheus", status="active")

    assert owner.servers[MCP_SERVER_ID].display_name == "Governed Grafana"
    assert catalog.entries[("mcp_server", MCP_SERVER_ID)].status == "active"
    with pytest.raises(ValueError, match="identity is immutable"):
        await registry.update_tool("query_prometheus", server_id="other-server")


@pytest.mark.asyncio
async def test_server_deactivation_cascades_to_tools_and_catalog() -> None:
    registry, owner, catalog = _registry()
    await registry.register_server(_server(status="active"))
    for tool_id in MCP_TOOL_IDS:
        await registry.register_tool(_tool(tool_id, status="active"))

    await registry.deactivate_server(MCP_SERVER_ID)

    assert owner.servers[MCP_SERVER_ID].status == "inactive"
    assert all(owner.tools[key].status == "inactive" for key in MCP_TOOL_IDS)
    assert all(catalog.entries[("mcp_tool", key)].status == "inactive" for key in MCP_TOOL_IDS)


@pytest.mark.asyncio
async def test_unknown_tool_or_server_relation_is_rejected_without_projection() -> None:
    registry, owner, catalog = _registry()
    with pytest.raises(ValueError, match="outside the governed contract"):
        await registry.register_tool(_tool("not_governed", server_id=MCP_SERVER_ID))
    assert not owner.tools
    assert not catalog.entries
