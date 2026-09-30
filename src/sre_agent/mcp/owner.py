"""Owner-authoritative lifecycle for governed MCP resources."""

from typing import Any, Protocol

from pydantic import ValidationError

from sre_agent.governance.dto import MCPServer, MCPTool, ResourceCatalogEntry

MCP_CONTRACT_VERSION = "1.0.0"
MCP_SERVER_ID = "grafana-mcp"
MCP_TOOL_IDS = ("query_prometheus", "query_elasticsearch")


class MCPRegistryError(ValueError):
    """A registration or lifecycle request violated the owner contract."""


class MCPOwnerStore(Protocol):
    async def get_server(self, server_id: str) -> MCPServer | None: ...

    async def get_tool(self, tool_id: str) -> MCPTool | None: ...

    async def register_server(self, server: MCPServer) -> MCPServer: ...

    async def update_server(self, server_id: str, **changes: object) -> MCPServer: ...

    async def deactivate_server(self, server_id: str) -> tuple[MCPServer, list[MCPTool]]: ...

    async def register_tool(self, tool: MCPTool) -> MCPTool: ...

    async def update_tool(self, tool_id: str, **changes: object) -> MCPTool: ...


class MCPCatalogProjection(Protocol):
    async def project_mcp_server(self, server: MCPServer) -> ResourceCatalogEntry: ...

    async def project_mcp_tool(self, tool: MCPTool) -> ResourceCatalogEntry: ...


class MCPRegistry:
    """Validate the versioned contract before mutating owner state.

    The owner store is authoritative. The catalog writer is called only after
    an owner mutation and is intentionally limited to projection methods.
    """

    def __init__(self, owner_store: MCPOwnerStore, catalog: MCPCatalogProjection) -> None:
        self._owner = owner_store
        self._catalog = catalog

    _SERVER_MUTABLE_FIELDS = frozenset(
        {"status", "endpoint", "display_name", "visibility", "description", "tags"}
    )
    _TOOL_MUTABLE_FIELDS = frozenset(
        {"status", "display_name", "visibility", "description", "tags"}
    )

    async def register_server(self, raw: Any) -> MCPServer:
        server = self._server(raw)
        self._require_server_identity(server)
        stored = await self._owner.register_server(server)
        await self._catalog.project_mcp_server(stored)
        return stored

    async def update_server(self, server_id: str, **changes: object) -> MCPServer:
        current = await self._required_server(server_id)
        self._reject_identity_changes(changes, "server_id", "owner_id", "contract_version")
        self._reject_unknown_changes(changes, self._SERVER_MUTABLE_FIELDS, "server")
        self._server({**current.model_dump(), **changes})
        stored = await self._owner.update_server(server_id, **changes)
        await self._catalog.project_mcp_server(stored)
        return stored

    async def deactivate_server(self, server_id: str) -> MCPServer:
        await self._required_server(server_id)
        server, tools = await self._owner.deactivate_server(server_id)
        await self._catalog.project_mcp_server(server)
        for tool in tools:
            await self._catalog.project_mcp_tool(tool)
        return server

    async def register_tool(self, raw: Any) -> MCPTool:
        tool = self._tool(raw)
        self._require_tool_identity(tool)
        server = await self._required_server(tool.server_id)
        if tool.owner_id != server.owner_id:
            raise MCPRegistryError("tool owner must match its server owner")
        stored = await self._owner.register_tool(tool)
        await self._catalog.project_mcp_tool(stored)
        return stored

    async def update_tool(self, tool_id: str, **changes: object) -> MCPTool:
        current = await self._required_tool(tool_id)
        self._reject_identity_changes(
            changes, "tool_id", "server_id", "owner_id", "contract_version", "upstream_name"
        )
        self._reject_unknown_changes(changes, self._TOOL_MUTABLE_FIELDS, "tool")
        self._tool({**current.model_dump(), **changes})
        stored = await self._owner.update_tool(tool_id, **changes)
        server = await self._required_server(stored.server_id)
        if stored.owner_id != server.owner_id:
            raise MCPRegistryError("tool owner must match its server owner")
        await self._catalog.project_mcp_tool(stored)
        return stored

    async def deactivate_tool(self, tool_id: str) -> MCPTool:
        tool = await self._required_tool(tool_id)
        return await self.update_tool(tool.tool_id, status="inactive")

    async def _required_server(self, server_id: str) -> MCPServer:
        server = await self._owner.get_server(server_id)
        if server is None:
            raise MCPRegistryError("MCP server is not registered")
        return server

    async def _required_tool(self, tool_id: str) -> MCPTool:
        tool = await self._owner.get_tool(tool_id)
        if tool is None:
            raise MCPRegistryError("MCP tool is not registered")
        return tool

    @staticmethod
    def _server(raw: Any) -> MCPServer:
        try:
            return MCPServer.model_validate(raw)
        except ValidationError as error:
            raise MCPRegistryError("invalid MCP server registration") from error

    @staticmethod
    def _tool(raw: Any) -> MCPTool:
        try:
            return MCPTool.model_validate(raw)
        except ValidationError as error:
            raise MCPRegistryError("invalid MCP tool registration") from error

    @staticmethod
    def _require_server_identity(server: MCPServer) -> None:
        if server.server_id != MCP_SERVER_ID:
            raise MCPRegistryError("MCP server is outside the governed contract")
        if server.contract_version != MCP_CONTRACT_VERSION:
            raise MCPRegistryError("MCP server contract version is unsupported")

    @staticmethod
    def _require_tool_identity(tool: MCPTool) -> None:
        if tool.server_id != MCP_SERVER_ID:
            raise MCPRegistryError("MCP tool server relation is outside the governed contract")
        if tool.tool_id not in MCP_TOOL_IDS or tool.upstream_name != tool.tool_id:
            raise MCPRegistryError("MCP tool is outside the governed contract")
        if tool.contract_version != MCP_CONTRACT_VERSION:
            raise MCPRegistryError("MCP tool contract version is unsupported")

    @staticmethod
    def _reject_identity_changes(changes: dict[str, object], *fields: str) -> None:
        if any(field in changes for field in fields):
            raise MCPRegistryError("MCP resource identity is immutable")

    @staticmethod
    def _reject_unknown_changes(
        changes: dict[str, object], allowed: frozenset[str], resource: str
    ) -> None:
        unknown = set(changes).difference(allowed)
        if unknown:
            raise MCPRegistryError(f"unknown MCP {resource} field: {sorted(unknown)[0]}")
