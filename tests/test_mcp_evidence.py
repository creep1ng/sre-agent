"""Deterministic bootstrap and isolated-stack evidence contract for MCP #187 T4."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from sre_agent.persistence.models import (
    GrantRow,
    MCPServerRow,
    MCPToolRow,
    PrincipalRow,
    ResourceRow,
)
from sre_agent.persistence.seeds import MCP_DEMO_GRANTS, bootstrap_mcp_demo
from sre_agent.settings import Settings

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


class MemorySession:
    def __init__(self) -> None:
        self.rows: dict[tuple[type[Any], Any], Any] = {}

    async def get(self, model: type[Any], key: Any) -> Any:
        return self.rows.get((model, key))

    def add(self, row: Any) -> None:
        if isinstance(row, PrincipalRow):
            key = row.principal_id
        elif isinstance(row, MCPServerRow):
            key = row.server_id
        elif isinstance(row, MCPToolRow):
            key = row.tool_id
        elif isinstance(row, GrantRow):
            key = row.grant_id
        elif isinstance(row, ResourceRow):
            key = (row.resource_type, row.resource_id)
        else:
            raise AssertionError(f"unexpected row type: {type(row)!r}")
        self.rows[(type(row), key)] = row

    async def flush(self) -> None:
        return None


def _seed_principals(session: MemorySession) -> None:
    for principal_id, kind in (("demo-human", "human"), ("restricted-harness", "agent")):
        session.add(
            PrincipalRow(
                principal_id=principal_id,
                kind=kind,
                display_name=principal_id,
                status="active",
                created_at=NOW,
                updated_at=NOW,
            )
        )


@pytest.mark.asyncio
async def test_mcp_bootstrap_is_idempotent_and_has_no_restricted_or_open_grants() -> None:
    session = MemorySession()
    _seed_principals(session)

    assert await bootstrap_mcp_demo(session) is True
    assert await bootstrap_mcp_demo(session) is False

    server = session.rows[(MCPServerRow, "grafana-mcp")]
    assert server.status == "active"
    assert server.endpoint == "http://grafana-mcp:8000/mcp"
    assert {key[1] for key in session.rows if key[0] is MCPToolRow} == {
        "query_prometheus",
        "query_elasticsearch",
    }
    assert {key[1] for key in session.rows if key[0] is ResourceRow} == {
        ("mcp_server", "grafana-mcp"),
        ("mcp_tool", "query_prometheus"),
        ("mcp_tool", "query_elasticsearch"),
    }
    grants = [row for (model, _), row in session.rows.items() if model is GrantRow]
    assert {grant.grant_id for grant in grants} == {grant[0] for grant in MCP_DEMO_GRANTS}
    assert all(grant.principal_id == "demo-human" for grant in grants)
    assert all(grant.resource_type != "administrative_control" for grant in grants)


@pytest.mark.asyncio
async def test_mcp_bootstrap_refreshes_missing_and_stale_catalog_projections() -> None:
    session = MemorySession()
    _seed_principals(session)
    await bootstrap_mcp_demo(session)

    server_projection = session.rows[(ResourceRow, ("mcp_server", "grafana-mcp"))]
    server_projection.status = "inactive"
    server_projection.owner_id = "stale-owner"
    del session.rows[(ResourceRow, ("mcp_tool", "query_elasticsearch"))]

    assert await bootstrap_mcp_demo(session) is False

    assert server_projection.status == "active"
    assert server_projection.owner_id == "mcp-platform"
    assert (ResourceRow, ("mcp_tool", "query_elasticsearch")) in session.rows


def test_mcp_overlay_uses_the_generated_token_file_and_external_boundary() -> None:
    document = yaml.safe_load((ROOT / "compose.mcp.yaml").read_text())
    api = document["services"]["api"]
    assert api["env_file"] == [
        "${DEMO_STATE_DIR:?DEMO_STATE_DIR is required}/grafana-mcp.env"
    ]
    assert api["environment"]["GRAFANA_MCP_ENDPOINT"] == "http://grafana-mcp:8000/mcp"
    assert "GRAFANA_MCP_TOKEN" not in api["environment"]
    assert document["networks"]["mcp-boundary"] == {
        "name": "sre-mcp-boundary",
        "external": True,
    }
    assert "mcp-boundary" in api["networks"]
    assert "MCP_GRAFANA_SERVER_TOKEN" not in (ROOT / "compose.mcp.yaml").read_text()


def test_mcp_overlay_waits_for_governed_seed_before_starting_api() -> None:
    document = yaml.safe_load((ROOT / "compose.mcp.yaml").read_text())
    assert document["services"]["api"]["depends_on"]["mcp-seed"] == {
        "condition": "service_completed_successfully"
    }


def test_runbook_allowed_example_matches_published_prometheus_schema() -> None:
    runbook = (ROOT / "docs/governed-grafana-mcp-demo.md").read_text()
    match = re.search(
        r"-d '(\{[^']+\})' \\\n\s+http://127\.0\.0\.1:8000/v1/mcp/tools/query_prometheus",
        runbook,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    schema = json.loads(
        (
            ROOT / "schemas/mcp/1.0.0/json-schema/query-prometheus-input.schema.json"
        ).read_text()
    )
    assert set(payload) == set(schema["required"])
    for field in ("datasource_uid", "query_type"):
        assert payload[field] == schema["properties"][field]["const"]


def test_settings_accept_the_generated_mcp_token_name_without_persisting_it() -> None:
    settings = Settings.from_environment(
        {
            "DATABASE_URL": "postgresql://unused",
            "MCP_GRAFANA_SERVER_TOKEN": "generated-only-token",
        }
    )
    assert settings.grafana_mcp_token == "generated-only-token"
    assert "generated-only-token" not in repr(settings)
