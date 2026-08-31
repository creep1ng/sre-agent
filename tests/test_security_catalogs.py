import ast
import re
import tomllib
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from sre_agent.persistence.seeds import PRINCIPALS

ROOT = Path(__file__).parents[1]
GRANTS_PATH = ROOT / "docs/security/demo-grants.v1.yaml"
SCENARIOS_PATH = ROOT / "docs/security/scenarios.v1.yaml"
THREAT_MODEL_PATH = ROOT / "docs/security/threat-model.md"
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


def assert_valid_scenario_outcome(scenario: dict[str, object]) -> None:
    expected = scenario["expected"]
    if expected["policy_decision"] == "allow":
        observed = (expected["http_status"], expected["code"], expected["audit"])
        assert observed == (200, "ok", "on")
    elif expected["policy_decision"] == "deny":
        observed = (
            expected["http_status"],
            expected["code"],
            expected["upstream_calls"],
            expected["audit"],
        )
        assert observed == (403, "resource_unavailable", 0, "on")
    else:
        assert expected["policy_decision"] == "not_evaluated"
        assert scenario["maturity"] == "contracted_future"
        observed = (
            expected["http_status"],
            expected["code"],
            expected["upstream_calls"],
            expected["audit"],
        )
        assert observed == (200, "not_evaluated", 0, "off")


def test_scenario_outcomes_reject_contradictory_policy_and_audit_claims() -> None:
    scenarios = load_catalog(SCENARIOS_PATH)["scenarios"]
    deferred = [scenario for scenario in scenarios if scenario["maturity"] != "current"]
    future = [scenario for scenario in scenarios if scenario["maturity"] == "future"]

    assert deferred, "catalog_drift: deferred scenarios must remain explicit"
    assert future, "catalog_drift: future scenarios must remain explicit"
    for scenario in scenarios:
        assert_valid_scenario_outcome(scenario)


def test_not_evaluated_outcome_rejects_denial_http_and_code_mutation() -> None:
    scenario = next(
        item
        for item in load_catalog(SCENARIOS_PATH)["scenarios"]
        if item["id"] == "SEC-004"
    )
    contradictory = deepcopy(scenario)
    contradictory["expected"] |= {"http_status": 403, "code": "resource_unavailable"}

    with pytest.raises(AssertionError):
        assert_valid_scenario_outcome(contradictory)


def test_threat_model_states_current_and_future_security_boundaries() -> None:
    threat_model = THREAT_MODEL_PATH.read_text()

    required_evidence = (
        "schemas/adrs/ADR-004-grants.md",
        "schemas/adrs/ADR-005-audit-redaction.md",
        "schemas/adrs/ADR-006-sanitized-audit-content.md",
    )
    required_boundaries = (
        "Assets",
        "Trust boundaries",
        "Current controls",
        "Future and contracted controls",
        "Residual risks",
        "Exclusions",
        "metadata-only audit",
        "No runtime redactor is implemented",
    )
    assert all(item in threat_model for item in required_evidence)
    assert all(item in threat_model for item in required_boundaries)


def test_semantic_catalog_entries_resolve_runtime_evidence_without_future_claims() -> None:
    scenarios = load_catalog(SCENARIOS_PATH)["scenarios"]
    current = [scenario for scenario in scenarios if scenario["maturity"] == "current"]
    by_id = {scenario["id"]: scenario for scenario in scenarios}

    for scenario in current:
        file_name, function_name = scenario["automation"]["test_locator"].split("::")
        functions = {
            node.name
            for node in ast.parse((ROOT / file_name).read_text()).body
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        }
        assert function_name in functions, (
            f"catalog_drift: unresolved test locator {file_name}::{function_name}"
        )
    for identifier in ("SEC-002", "SEC-003"):
        expected = by_id[identifier]["expected"]
        assert expected["http_status"] == 403
        assert expected["code"] == "resource_unavailable"
        assert expected["upstream_calls"] == 0
    future = [scenario for scenario in scenarios if scenario["maturity"] != "current"]
    assert all(item["automation"]["status"] == "non_executable" for item in future)
    assert all("test_locator" not in item["automation"] for item in future)
    assert "Runtime evidence locators" in THREAT_MODEL_PATH.read_text()


def test_threat_model_links_catalogs_and_authoritative_evidence() -> None:
    threat_model = THREAT_MODEL_PATH.read_text()
    targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", threat_model)
    resolved = {(THREAT_MODEL_PATH.parent / target).resolve() for target in targets}

    assert GRANTS_PATH.resolve() in resolved
    assert SCENARIOS_PATH.resolve() in resolved
    assert all(target.exists() for target in resolved)
    assert threat_model.count("## ") >= 6, "catalog_drift: threat model must remain scannable"
