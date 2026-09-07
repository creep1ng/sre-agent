"""Acceptance tests for the incident authorization vocabulary (issue #145, finding C08).

Each test pins one property the taxonomy must keep, so a failure names what regressed.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from validate_incident_authorization import (  # noqa: E402
    AUTHORIZATION_PATH,
    ENGINE_RESOURCE_TYPES,
    GRANT_ACTION_PATTERN,
    SCENARIOS_PATH,
    check_grants,
    check_names_confer_nothing,
    load_yaml,
    validate,
)


@pytest.fixture(scope="module")
def catalogue() -> dict:
    return load_yaml(AUTHORIZATION_PATH)


@pytest.fixture(scope="module")
def scenarios() -> list:
    return load_yaml(SCENARIOS_PATH)["scenarios"]


def test_every_authorization_check_passes() -> None:
    """The full validator, exactly as CI runs it, reports no problems."""
    assert validate() == []


def test_denial_is_the_default(catalogue: dict) -> None:
    """The incident domain inherits deny-by-default from the shared engine."""
    assert catalogue["default_decision"] == "deny"
    assert all(grant["effect"] == "allow" for grant in catalogue["grants"])


def test_names_and_kinds_confer_no_authority(catalogue: dict, scenarios: list) -> None:
    """Finding C08: authority must never be inferred from a principal's name or kind."""
    assert catalogue["names_confer_roles"] is False
    assert check_names_confer_nothing(catalogue) == []

    proof = [
        scenario
        for scenario in scenarios
        if scenario["principal"] == "admin-human"
        and scenario["expected"]["policy_decision"] == "deny"
    ]
    assert proof, "an administrative-sounding principal must be denied somewhere"


def test_actions_can_actually_be_stored_as_grants(catalogue: dict) -> None:
    """An action outside the Grant pattern could never reach the engine."""
    for action in catalogue["actions"]:
        assert GRANT_ACTION_PATTERN.match(action["name"]), action["name"]


def test_approval_is_separable_from_participation(catalogue: dict, scenarios: list) -> None:
    """Least privilege only means something if approving is its own action."""
    mapping = catalogue["command_action_map"]
    assert mapping["approve_mitigation"] == "run.approve"
    assert mapping["reject_mitigation"] == "run.approve"
    assert mapping["escalate"] != mapping["approve_mitigation"]

    approvers = {
        grant["principal_id"] for grant in catalogue["grants"] if grant["action"] == "run.approve"
    }
    commanders = {
        grant["principal_id"] for grant in catalogue["grants"] if grant["action"] == "run.command"
    }
    assert approvers <= commanders, "approving without being able to participate is incoherent"
    operator = [item for item in scenarios if item["principal"] == "incident-operator"]
    assert {(item["action"], item["expected"]["policy_decision"]) for item in operator} == {
        ("run.command", "allow"),
        ("run.approve", "deny"),
    }


def test_every_command_resolves_to_an_action(catalogue: dict) -> None:
    """The API resolves a command to an action; none may be unmapped."""
    declared = {action["name"] for action in catalogue["actions"]}
    for command, action in catalogue["command_action_map"].items():
        assert action in declared, command


def test_resource_type_extension_records_owner_approval(catalogue: dict) -> None:
    """The approved extension remains traceable until the engine enum consumes it."""
    extension = catalogue["approved_resource_type"]
    assert extension["name"] not in ENGINE_RESOURCE_TYPES
    assert extension["approved_by"] == "gateway owner"
    assert extension["approval_reference"] == "issue #145 comment 5553749536"
    assert extension["rationale"]


def test_resource_is_the_workflow_not_the_run(catalogue: dict) -> None:
    """A per-run resource could not be granted ahead of time; the engine matches exactly."""
    resources = catalogue["resources"]
    assert resources == [
        {"type": "incident_workflow", "id": "incident-response", "status": "active"}
    ]


def test_catalogue_is_contracted_until_persistence_seeds_it(catalogue: dict) -> None:
    """Nothing here exists at runtime yet; HT-INC-06-PERSISTENCE (#146) seeds it."""
    assert catalogue["maturity"] == "contracted"


def test_scenarios_use_the_engine_denial_taxonomy(scenarios: list) -> None:
    """Denials must name a cause the engine can actually produce."""
    causes = {
        scenario["expected"].get("denial_cause")
        for scenario in scenarios
        if scenario["expected"]["policy_decision"] == "deny"
    }
    assert causes <= {
        "principal_inactive",
        "resource_missing",
        "resource_inactive",
        "grant_not_applicable",
    }


def test_authenticated_agent_cannot_borrow_payload_human_identity(scenarios: list) -> None:
    scenario = next(item for item in scenarios if item["id"] == "INC-AUTH-007")
    assert scenario["authenticated_principal"] == "incident-harness"
    assert scenario["payload"]["actor"] == "human"
    assert scenario["payload"]["actor_reference"]["principal_id"] == "demo-human"
    assert scenario["expected"] == {
        "http_status": 403,
        "policy_decision": "deny",
        "denial_cause": "grant_not_applicable",
    }


def test_run_read_does_not_authorize_sensitive_context(
    catalogue: dict, scenarios: list
) -> None:
    scenario = next(item for item in scenarios if item["id"] == "INC-AUTH-008")
    demo_grants = {
        grant["action"]
        for grant in catalogue["grants"]
        if grant["principal_id"] == "demo-human"
    }
    assert "run.read" in demo_grants
    assert "run.read_context" not in demo_grants
    assert scenario["principal"] == "demo-human"
    assert scenario["action"] == "run.read_context"
    assert scenario["request"] == {
        "method": "GET",
        "path": "/v1/incidents/{incident_id}/runs/{run_id}/context",
    }
    assert scenario["expected"] == {
        "http_status": 403,
        "policy_decision": "deny",
        "denial_cause": "grant_not_applicable",
    }


@pytest.mark.parametrize("kind", ["principal", "resource", "grant"])
def test_validator_rejects_inactive_authorization_facts(catalogue: dict, kind: str) -> None:
    mutated = deepcopy(catalogue)
    collection = {"principal": "principals", "resource": "resources", "grant": "grants"}[kind]
    mutated[collection][0]["status"] = "inactive"
    assert check_grants(mutated)


def test_run_endpoints_are_not_implemented_yet() -> None:
    """Out of scope for HT-INC-04: the vocabulary precedes the endpoints."""
    assert not (REPOSITORY_ROOT / "src" / "sre_agent" / "incident" / "run_router.py").exists()
