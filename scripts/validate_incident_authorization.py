"""Validate the incident authorization vocabulary and grant matrix (issue #145, C08).

Automated gate for the taxonomy published ahead of the run endpoints. Runs in CI and
locally with:

    python scripts/validate_incident_authorization.py

The point of this script is that the catalogue cannot quietly drift into something the
shared authorization engine could never evaluate, and cannot quietly start conferring
authority by name.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_PATH = REPOSITORY_ROOT / "agent" / "api" / "authorization.v1.yaml"
SCENARIOS_PATH = REPOSITORY_ROOT / "agent" / "api" / "authorization-scenarios.v1.yaml"
SEEDED_GRANTS_PATH = REPOSITORY_ROOT / "docs" / "security" / "demo-grants.v1.yaml"

# governance.dto.Grant constrains action with this pattern. Anything outside it could
# never be stored as a grant, so the vocabulary must respect it.
GRANT_ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{1,63}$")

# governance.dto.ResourceType today. The catalogue proposes an addition rather than
# silently assuming one, so the proposal must be declared explicitly.
ENGINE_RESOURCE_TYPES = frozenset(
    {"llm_model", "mcp_server", "mcp_tool", "skill", "bok_collection"}
)

# governance.authorization.AuthorizationDenialCause.
DENIAL_CAUSES = frozenset(
    {"principal_inactive", "resource_missing", "resource_inactive", "grant_not_applicable"}
)

COMMANDS = frozenset(
    {
        "approve_mitigation",
        "reject_mitigation",
        "request_changes",
        "propose_disposition",
        "escalate",
        "cancel_run",
    }
)


def load_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"required catalogue is missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check_vocabulary(catalogue: dict[str, Any]) -> list[str]:
    """Actions must be storable as grants and the resource type must be declared."""
    errors: list[str] = []

    if catalogue.get("default_decision") != "deny":
        errors.append("default_decision must be 'deny'")
    if catalogue.get("names_confer_roles") is not False:
        errors.append("names_confer_roles must be false: authority comes from grants")

    for action in catalogue.get("actions", []):
        name = action.get("name", "")
        if not GRANT_ACTION_PATTERN.match(name):
            errors.append(
                f"action '{name}' cannot be stored as a grant: it violates the "
                "governance.dto.Grant action pattern"
            )

    proposal = catalogue.get("proposed_resource_type") or {}
    proposed = proposal.get("name")
    if proposed is None:
        errors.append("proposed_resource_type must be declared while the engine enum lacks it")
    elif proposed in ENGINE_RESOURCE_TYPES:
        errors.append(
            f"resource type '{proposed}' already exists in the engine enum; the "
            "catalogue should consume it instead of proposing it"
        )
    elif not proposal.get("requires_approval_from"):
        errors.append("a proposed resource type must name who approves the extension")

    declared = {resource.get("type") for resource in catalogue.get("resources", [])}
    for resource_type in declared - ENGINE_RESOURCE_TYPES - {proposed}:
        errors.append(
            f"resource type '{resource_type}' is neither in the engine enum nor the proposal"
        )

    return errors


def check_command_mapping(catalogue: dict[str, Any]) -> list[str]:
    """Every command resolves to exactly one declared action, and none is orphaned."""
    errors: list[str] = []
    mapping: dict[str, str] = catalogue.get("command_action_map", {})
    action_names = {action["name"] for action in catalogue.get("actions", [])}

    for command in sorted(COMMANDS - set(mapping)):
        errors.append(f"command '{command}' resolves to no action")
    for command in sorted(set(mapping) - COMMANDS):
        errors.append(f"command_action_map declares unknown command '{command}'")
    for command, action in mapping.items():
        if action not in action_names:
            errors.append(f"command '{command}' maps to undeclared action '{action}'")

    # Approving and rejecting a mitigation are the human gate; both must sit behind the
    # same dedicated action, otherwise participation would imply approval.
    for command in ("approve_mitigation", "reject_mitigation"):
        if mapping.get(command) != "run.approve":
            errors.append(f"command '{command}' must be authorized by run.approve")

    return errors


def check_grants(catalogue: dict[str, Any]) -> list[str]:
    """Grants must be exact, active, and reference declared principals and resources."""
    errors: list[str] = []
    principals = {principal["id"] for principal in catalogue.get("principals", [])}
    resources = {(resource["type"], resource["id"]) for resource in catalogue.get("resources", [])}
    action_names = {action["name"] for action in catalogue.get("actions", [])}

    seen: set[tuple[str, str, str, str]] = set()
    for grant in catalogue.get("grants", []):
        identity = (
            grant.get("principal_id"),
            grant.get("action"),
            grant.get("resource_type"),
            grant.get("resource_id"),
        )
        if identity in seen:
            errors.append(f"duplicate grant for {identity}")
        seen.add(identity)

        if grant.get("principal_id") not in principals:
            errors.append(f"grant '{grant.get('id')}' references an undeclared principal")
        if grant.get("action") not in action_names:
            errors.append(f"grant '{grant.get('id')}' references an undeclared action")
        if (grant.get("resource_type"), grant.get("resource_id")) not in resources:
            errors.append(f"grant '{grant.get('id')}' references an undeclared resource")
        if grant.get("effect") != "allow":
            errors.append(
                f"grant '{grant.get('id')}' is not an allow; the engine only matches "
                "active allow grants and denial is the default"
            )

    return errors


def check_names_confer_nothing(catalogue: dict[str, Any]) -> list[str]:
    """An administrative-sounding principal must hold no grant it did not earn.

    This is the executable form of `names_confer_roles: false`. Without it the flag is
    a comment, and a later edit could hand admin-human authority by habit.
    """
    granted = {grant.get("principal_id") for grant in catalogue.get("grants", [])}
    if "admin-human" in granted:
        return [
            "admin-human holds a grant in this catalogue; the scenario that proves "
            "names confer no authority depends on it holding none"
        ]
    return []


def check_scenarios(catalogue: dict[str, Any], scenarios: dict[str, Any]) -> list[str]:
    """Scenarios must agree with the matrix they claim to exercise."""
    errors: list[str] = []
    action_names = {action["name"] for action in catalogue.get("actions", [])}
    allowed = {
        (grant["principal_id"], grant["action"], grant["resource_type"], grant["resource_id"])
        for grant in catalogue.get("grants", [])
    }
    known_resources = {
        (resource["type"], resource["id"]) for resource in catalogue.get("resources", [])
    }

    entries = scenarios.get("scenarios", [])
    if not entries:
        errors.append("no authorization scenarios declared")

    identifiers: set[str] = set()
    for scenario in entries:
        identifier = scenario.get("id", "<missing id>")
        if identifier in identifiers:
            errors.append(f"duplicate scenario id '{identifier}'")
        identifiers.add(identifier)

        action = scenario.get("action")
        if action not in action_names:
            errors.append(f"scenario '{identifier}' uses undeclared action '{action}'")

        resource = scenario.get("resource", {})
        key = (
            scenario.get("principal"),
            action,
            resource.get("type"),
            resource.get("id"),
        )
        expected = scenario.get("expected", {})
        decision = expected.get("policy_decision")
        cause = expected.get("denial_cause")

        if decision == "allow":
            if key not in allowed:
                errors.append(f"scenario '{identifier}' expects allow but no matching grant exists")
            if cause is not None:
                errors.append(f"scenario '{identifier}' allows and still names a denial cause")
        elif decision == "deny":
            if key in allowed:
                errors.append(f"scenario '{identifier}' expects deny but a matching grant exists")
            if cause not in DENIAL_CAUSES:
                errors.append(
                    f"scenario '{identifier}' denies with cause '{cause}', which is outside "
                    "the engine's closed denial taxonomy"
                )
            if (
                cause == "resource_missing"
                and (
                    resource.get("type"),
                    resource.get("id"),
                )
                in known_resources
            ):
                errors.append(
                    f"scenario '{identifier}' claims a missing resource that the catalogue declares"
                )
        elif decision != "not_evaluated":
            errors.append(f"scenario '{identifier}' has an unknown policy_decision '{decision}'")

    if not any(
        scenario.get("principal") == "admin-human"
        and scenario.get("expected", {}).get("policy_decision") == "deny"
        for scenario in entries
    ):
        errors.append("no scenario proves that an administrative name confers no authority")

    return errors


def check_seeded_catalogue_untouched() -> list[str]:
    """The seeded matrix belongs to persistence and must not gain contracted grants.

    docs/security/demo-grants.v1.yaml is asserted against the database seeds. Adding
    incident grants there would break that assertion and claim, falsely, that these
    grants already exist at runtime.
    """
    seeded = load_yaml(SEEDED_GRANTS_PATH)
    stray = [
        grant
        for grant in seeded.get("grants", [])
        if str(grant.get("resource_type", "")).startswith("incident")
    ]
    if stray:
        return [
            "the seeded grant catalogue now contains incident grants; contracted grants "
            "belong in agent/api/authorization.v1.yaml until persistence seeds them"
        ]
    return []


def validate() -> list[str]:
    catalogue = load_yaml(AUTHORIZATION_PATH)
    scenarios = load_yaml(SCENARIOS_PATH)
    return [
        *check_vocabulary(catalogue),
        *check_command_mapping(catalogue),
        *check_grants(catalogue),
        *check_names_confer_nothing(catalogue),
        *check_scenarios(catalogue, scenarios),
        *check_seeded_catalogue_untouched(),
    ]


def main() -> int:
    try:
        errors = validate()
    except FileNotFoundError as error:
        print(f"incident authorization: {error}", file=sys.stderr)
        return 1

    if errors:
        print(f"incident authorization: {len(errors)} problem(s) found", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    catalogue = load_yaml(AUTHORIZATION_PATH)
    scenarios = load_yaml(SCENARIOS_PATH)
    print(
        "incident authorization: OK "
        f"({len(catalogue['actions'])} actions, {len(catalogue['grants'])} grants, "
        f"{len(scenarios['scenarios'])} scenarios; "
        f"proposed resource type: {catalogue['proposed_resource_type']['name']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
