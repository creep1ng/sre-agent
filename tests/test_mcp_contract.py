"""Executable contract checks for the governed Grafana MCP surface (#187)."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]
CONTRACT_DIR = ROOT / "schemas" / "mcp" / "1.0.0"
CONTRACT_PATH = CONTRACT_DIR / "grafana-mcp.yaml"
TOOL_IDS = ("query_prometheus", "query_elasticsearch")


def load_contract() -> dict[str, object]:
    payload = yaml.safe_load(CONTRACT_PATH.read_text())
    assert isinstance(payload, dict)
    return payload


def load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    assert isinstance(payload, dict)
    return payload


def test_contract_pins_exact_tools_actions_resources_errors_and_timeout() -> None:
    contract = load_contract()

    assert contract["contract_version"] == "1.0.0"
    assert contract["protocol"] == "mcp"
    assert contract["server"] == {
        "resource_type": "mcp_server",
        "resource_id": "grafana-mcp",
    }
    tools = contract["tools"]
    assert [tool["tool_id"] for tool in tools] == list(TOOL_IDS)
    assert all(tool["resource_type"] == "mcp_tool" for tool in tools)
    assert all(tool["server_id"] == "grafana-mcp" for tool in tools)
    assert contract["actions"] == {
        "discovery": {
            "name": "mcp.discovery",
            "resource_type": "mcp_server",
            "resource_id": "grafana-mcp",
        },
        "invoke": {
            "name": "mcp.invoke",
            "resource_type": "mcp_tool",
        },
    }
    assert contract["timeout"] == {
        "seconds": 30,
        "status": 504,
        "error_code": "upstream_timeout",
    }
    assert [error["code"] for error in contract["public_errors"]] == [
        "authentication_failed",
        "resource_unavailable",
        "contract_validation_failed",
        "upstream_unavailable",
        "upstream_timeout",
        "upstream_invalid",
        "audit_unavailable",
    ]


@pytest.mark.parametrize(
    "tool_id",
    TOOL_IDS,
)
def test_tool_input_and_result_schemas_accept_contract_examples(tool_id: str) -> None:
    contract = load_contract()
    tool = next(item for item in contract["tools"] if item["tool_id"] == tool_id)
    input_schema = load_json(CONTRACT_DIR / tool["input_schema"])
    result_schema = load_json(CONTRACT_DIR / tool["result_schema"])
    input_example = load_json(CONTRACT_DIR / tool["input_example"])
    result_example = load_json(CONTRACT_DIR / tool["result_example"])

    Draft202012Validator(input_schema, format_checker=FormatChecker()).validate(input_example)
    Draft202012Validator(result_schema, format_checker=FormatChecker()).validate(result_example)


def test_negative_input_fixtures_are_executable() -> None:
    contract = load_contract()
    schemas = {
        item["tool_id"]: load_json(CONTRACT_DIR / item["input_schema"])
        for item in contract["tools"]
    }
    fixtures = sorted((CONTRACT_DIR / "fixtures" / "negative").glob("*.json"))
    assert fixtures
    for fixture_path in fixtures:
        fixture = load_json(fixture_path)
        assert fixture["status"] == "negative", fixture_path
        assert fixture["version"] == "1.0.0", fixture_path
        if fixture["rule"] == "scenario":
            assert fixture["data"]["expected"]["status"] in {401, 403, 404, 422, 503, 504}
            continue
        tool_id = fixture["tool_id"]
        errors = list(Draft202012Validator(schemas[tool_id]).iter_errors(fixture["data"]))
        assert errors, f"fixture unexpectedly validates: {fixture_path}"


def test_non_enumeration_scenarios_are_closed_and_zero_effect() -> None:
    contract = load_contract()
    scenarios = contract["non_enumeration_scenarios"]
    assert {scenario["id"] for scenario in scenarios} == {
        "missing-credential",
        "discovery-denied",
        "unknown-server",
        "unknown-tool",
        "invalid-input",
    }
    for scenario in scenarios:
        expected = scenario["expected"]
        assert expected["error_code"] in {
            "authentication_failed",
            "resource_unavailable",
            "contract_validation_failed",
        }
        assert expected["upstream_calls"] == 0
        assert expected["enumerates"] is False


def test_timeout_and_failure_scenarios_pin_single_call_and_public_errors() -> None:
    contract = load_contract()
    scenarios = {scenario["id"]: scenario for scenario in contract["failure_scenarios"]}
    assert set(scenarios) == {"upstream-timeout", "upstream-failure", "allowed-invocation"}
    assert scenarios["upstream-timeout"]["expected"] == {
        "status": 504,
        "error_code": "upstream_timeout",
        "upstream_calls": 1,
    }
    assert scenarios["upstream-failure"]["expected"] == {
        "status": 503,
        "error_code": "upstream_unavailable",
        "upstream_calls": 1,
    }
    assert scenarios["allowed-invocation"]["expected"] == {
        "status": 200,
        "error_code": None,
        "upstream_calls": 1,
    }
