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
        r"-d '(\{[^']+\})' \\\n\s+\"\$API_BASE_URL/v1/mcp/tools/query_prometheus\"",
        runbook,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    schema = json.loads(
        (ROOT / "schemas/mcp/1.0.0/json-schema/query-prometheus-input.schema.json").read_text()
    )
    validate(payload, schema)


def test_runbook_preserves_exact_grafana_mcp_image_digest() -> None:
    runbook = (ROOT / "docs/governed-grafana-mcp-demo.md").read_text()
    image = (
        "grafana/mcp-grafana:1.3.0@sha256:"
        "5114852743e450fe5186b6c1712419843eb4bd295e47e64c452c3aa0fab3c42e"
    )

    assert image in runbook


def test_runbook_uses_current_checkout_and_existing_mcp_checks() -> None:
    runbook = (ROOT / "docs/governed-grafana-mcp-demo.md").read_text()

    assert "python scripts/demo_env.py up" in runbook
    assert "scripts/bootstrap-worktree.py" in runbook
    assert "tests/test_mcp_discovery.py" in runbook
    assert "tests/test_mcp_gateway.py" not in runbook
    assert "tests/test_mcp_evidence.py" not in runbook
    assert "UPSTREAM_ROOT" not in runbook


def test_demo_payment_healthcheck_allows_instrumented_node_startup() -> None:
    class DemoLoader(yaml.SafeLoader):
        pass

    DemoLoader.add_constructor("!reset", lambda loader, node: loader.construct_sequence(node))
    demo_overlay = yaml.load((ROOT / "compose.demo.yaml").read_text(), Loader=DemoLoader)
    payment = demo_overlay["services"]["payment"]

    assert payment["ports"] == []
    assert payment["healthcheck"]["timeout"] == "20s"
    assert "environment" not in payment
