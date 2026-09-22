from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from sre_agent.persistence.projections import project_catalog_entry


def _mcp_tool_row(**overrides: object) -> SimpleNamespace:
    values = {
        "resource_type": "mcp_tool",
        "resource_id": "grafana.alerts.query",
        "owner_id": "admin",
        "status": "registered",
        "source": "mcp",
        "source_ref": "grafana",
        "display_name": "Grafana alerts query",
        "visibility": "private",
        "description": "Read alert metadata.",
        "tags": ["grafana", "mcp"],
        "concrete_model": "secret/provider-model",
        "router": "secret-router",
        "inference_provider": "secret-provider",
        "raw_key": "secret",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_mcp_projection_preserves_provenance_without_routing_details() -> None:
    projected = project_catalog_entry(_mcp_tool_row())

    assert projected.resource_type == "mcp_tool"
    assert projected.owner_id == "admin"
    assert projected.source == "mcp"
    assert projected.source_ref == "grafana"
    assert projected.discoverability.tags == ["grafana", "mcp"]
    assert "concrete_model" not in projected.model_fields_set
    assert "router" not in projected.model_fields_set
    assert "inference_provider" not in projected.model_fields_set


@pytest.mark.parametrize("source", ("model_alias", "skill"))
def test_mcp_projection_rejects_non_mcp_provenance(source: str) -> None:
    with pytest.raises(ValidationError, match="catalog source"):
        project_catalog_entry(_mcp_tool_row(source=source))


def test_mcp_projection_rejects_unpublished_status() -> None:
    with pytest.raises(ValidationError, match="catalog status"):
        project_catalog_entry(_mcp_tool_row(status="draft"))
