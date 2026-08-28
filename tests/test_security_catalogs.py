import re
import tomllib
from pathlib import Path

import yaml

from sre_agent.persistence.seeds import PRINCIPALS

ROOT = Path(__file__).parents[1]
GRANTS_PATH = ROOT / "docs/security/demo-grants.v1.yaml"
SCENARIOS_PATH = ROOT / "docs/security/scenarios.v1.yaml"
SCENARIO_FIELDS = {
    "id",
    "maturity",
    "threat",
    "preconditions",
    "credential_state",
    "principal",
    "action",
    "resource",
    "request",
    "expected",
    "automation",
}
EXPECTED_FIELDS = {
    "http_status",
    "code",
    "policy_decision",
    "upstream_calls",
    "tool_calls",
    "audit",
}


def test_dependency_declares_pyyaml_in_dev_extra() -> None:
    with (ROOT / "pyproject.toml").open("rb") as manifest:
        dev_dependencies = tomllib.load(manifest)["project"]["optional-dependencies"]["dev"]

    assert "pyyaml==6.0.3" in dev_dependencies, (
        "catalog_drift: PyYAML must be a direct dev dependency"
    )


def load_catalog(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text())
    assert isinstance(payload, dict), f"catalog_drift: {path.name} must be a mapping"
    return payload


def test_catalog_structure_has_versioned_top_level_fields() -> None:
    grants = load_catalog(GRANTS_PATH)
    scenarios = load_catalog(SCENARIOS_PATH)

    assert grants["schema_version"] == "v1"
    assert grants["default_decision"] == "deny"
    assert grants["names_confer_roles"] is False
    assert set(grants) == {
        "schema_version",
        "default_decision",
        "names_confer_roles",
        "principals",
        "resources",
        "grants",
    }
    assert scenarios["catalog_version"] == "v1"
    assert set(scenarios) == {"catalog_version", "scenarios"}


def test_seed_and_grant_catalog_matches_the_seeded_matrix() -> None:
    grants = load_catalog(GRANTS_PATH)

    principals = {(item["id"], item["kind"], item["status"]) for item in grants["principals"]}
    expected_principals = {(principal_id, kind, "active") for principal_id, kind, _ in PRINCIPALS}
    assert principals == expected_principals, (
        "catalog_drift: principals must match persistence seeds"
    )
    assert grants["resources"] == [{"type": "llm_model", "id": "triage-agent", "status": "active"}]
    assert grants["grants"] == [
        {
            "id": "grant-incident-harness-invoke-triage-agent",
            "principal_id": "incident-harness",
            "action": "invoke",
            "resource_type": "llm_model",
            "resource_id": "triage-agent",
            "effect": "allow",
            "status": "active",
        }
    ], "catalog_drift: exactly one active incident-harness invoke allow is required"


def test_scenario_structure_enforces_nested_fields_and_maturity_rules() -> None:
    scenarios = load_catalog(SCENARIOS_PATH)["scenarios"]

    assert scenarios, "catalog_drift: scenarios must contain current and future evidence"
    ids = [scenario["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids)), "catalog_drift: scenario IDs must be unique"
    for scenario in scenarios:
        assert set(scenario) == SCENARIO_FIELDS, "catalog_drift: required scenario fields changed"
        assert type(scenario["id"]) is str and re.fullmatch(r"SEC-[0-9]{3}", scenario["id"])
        assert scenario["maturity"] in {"current", "contracted_future", "future"}
        assert set(scenario["request"]) == {"method", "path", "content_redaction"}
        assert type(scenario["request"]["content_redaction"]) is str
        assert set(scenario["expected"]) == EXPECTED_FIELDS
        assert type(scenario["expected"]["http_status"]) is int
        assert type(scenario["expected"]["upstream_calls"]) is int
        assert type(scenario["expected"]["tool_calls"]) is int
        assert type(scenario["expected"]["audit"]) is str
        automation = scenario["automation"]
        if scenario["maturity"] == "current":
            assert automation["status"] == "executable"
            assert type(automation["test_locator"]) is str and automation["test_locator"]
        else:
            assert automation["status"] == "non_executable"
            assert set(automation) == {"status", "evidence_required"}
            assert type(automation["evidence_required"]) is str and automation["evidence_required"]
