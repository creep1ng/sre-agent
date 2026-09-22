"""Static checks for the isolated governed Grafana MCP overlay."""

import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import validate

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def overlay() -> dict[str, object]:
    return yaml.safe_load((ROOT / "compose.mcp.yaml").read_text())


def test_overlay_confines_endpoint_token_and_boundary(overlay: dict[str, object]) -> None:
    services = overlay["services"]
    api = services["api"]
    seed = services["mcp-seed"]

    assert api["env_file"] == ["${DEMO_STATE_DIR:?DEMO_STATE_DIR is required}/grafana-mcp.env"]
    assert api["environment"] == {"GRAFANA_MCP_ENDPOINT": "http://grafana-mcp:8000/mcp"}
    assert seed["environment"] == {"DATABASE_URL": "${DATABASE_URL:?DATABASE_URL is required}"}
    assert "GRAFANA_MCP_TOKEN" not in str(overlay)
    assert "MCP_GRAFANA_SERVER_TOKEN" not in str(overlay)
    assert api["networks"] == ["runtime", "mcp-boundary"]
    assert overlay["networks"]["mcp-boundary"] == {
        "name": "sre-mcp-boundary",
        "external": True,
    }


def test_overlay_orders_mcp_seed_before_api(overlay: dict[str, object]) -> None:
    services = overlay["services"]

    assert services["mcp-seed"]["depends_on"] == {
        "seed": {"condition": "service_completed_successfully"}
    }
    assert services["api"]["depends_on"] == {
        "mcp-seed": {"condition": "service_completed_successfully"}
    }


def test_runbook_allowed_example_matches_prometheus_schema() -> None:
    runbook = (ROOT / "docs/governed-grafana-mcp-demo.md").read_text()
    match = re.search(
        r"-d '(\{[^']+\})' \\\n\s+http://127\.0\.0\.1:8000/v1/mcp/tools/query_prometheus",
        runbook,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    schema = json.loads(
        (ROOT / "schemas/mcp/1.0.0/json-schema/query-prometheus-input.schema.json").read_text()
    )
    validate(payload, schema)
