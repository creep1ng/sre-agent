from typing import Any

import pytest

from sre_agent.application import create_application
from sre_agent.gateway.responses import AuditStore
from sre_agent.settings import Settings


class StubMCPClient:
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        return {"data": []}


class RecordingAudit:
    async def append(self, event: Any) -> None:
        del event


def test_settings_read_fixed_mcp_endpoint_and_token_without_repr_leak() -> None:
    settings = Settings.from_environment(
        {
            "DATABASE_URL": "postgresql://unused",
            "GRAFANA_MCP_ENDPOINT": "http://grafana-mcp:8000/mcp",
            "GRAFANA_MCP_TOKEN": "fixed-secret-token",
        }
    )

    assert settings.grafana_mcp_endpoint == "http://grafana-mcp:8000/mcp"
    assert settings.grafana_mcp_token == "fixed-secret-token"
    assert "fixed-secret-token" not in repr(settings)


def test_application_does_not_mount_mcp_without_hmac_audit() -> None:
    application = create_application(
        Settings(
            "postgresql://unused",
            grafana_mcp_endpoint="http://grafana-mcp:8000/mcp",
            grafana_mcp_token="fixed-secret-token",
        ),
        mcp_client=StubMCPClient(),
    )

    assert "/v1/mcp/discovery" not in {route.path for route in application.routes}


def test_application_rejects_endpoint_without_fixed_token() -> None:
    with pytest.raises(RuntimeError, match="GRAFANA_MCP_TOKEN"):
        create_application(
            Settings(
                "postgresql://unused",
                grafana_mcp_endpoint="http://grafana-mcp:8000/mcp",
                audit_hmac_key="mcp-audit-key",
            )
        )


def test_application_mounts_mcp_only_with_hmac_and_audit_store() -> None:
    audit: AuditStore = RecordingAudit()
    application = create_application(
        Settings(
            "postgresql://unused",
            audit_hmac_key="mcp-audit-key",
            grafana_mcp_endpoint="http://grafana-mcp:8000/mcp",
            grafana_mcp_token="fixed-secret-token",
        ),
        mcp_client=StubMCPClient(),
        audit_store=audit,
    )

    assert {route.path for route in application.routes} >= {
        "/v1/mcp/discovery",
        "/v1/mcp/tools/{tool_id}",
    }
