"""Validate the declarative incident contracts produced by HT-INC-01 (issue #16).

The script is the automated acceptance gate for the workflow definition, the runtime
state schema, and the scenario fixtures. It runs in CI and locally with:

    python scripts/validate_incident_contracts.py

It performs four independent checks:

1. The state schema is a well-formed JSON Schema draft 2020-12 document.
2. The workflow definition is internally consistent: every transition references
   declared states, actors, decision points and outcomes; terminal states have no
   outgoing transitions; every non-terminal state is reachable from the initial one.
3. Positive fixtures validate against the state schema.
4. Negative fixtures are rejected by the state schema, proving the approved scope
   rules are actually enforced rather than merely documented.

The runtime state machine is out of scope here and belongs to HT-INC-02 (issue #26).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPOSITORY_ROOT / "agent"
WORKFLOW_PATH = AGENT_ROOT / "workflows" / "incident-response.yaml"
STATE_SCHEMA_PATH = AGENT_ROOT / "schemas" / "incident-state.schema.yaml"
FIXTURES_ROOT = AGENT_ROOT / "fixtures" / "incidents"

VALID_ACTORS = frozenset({"human", "agent", "system"})


def load_yaml(path: Path) -> Any:
    """Read one YAML document, failing loudly when the file is missing."""
    if not path.exists():
        raise FileNotFoundError(f"required contract file is missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_validator(schema: dict[str, Any]) -> Draft202012Validator:
    """Build a validator that actually enforces `format`.

    jsonschema treats `format` as an annotation unless a FormatChecker is supplied,
    so without this a state carrying `updated_at: definitely-not-a-timestamp` would
    pass CI. The `jsonschema[format]` extra installs the RFC 3339 validators the
    checker needs for `date-time`.
    """
    return Draft202012Validator(schema, format_checker=FormatChecker())


def check_format_enforcement(schema: dict[str, Any]) -> list[str]:
    """Prove at runtime that `date-time` and `uuid` are enforced, not annotated.

    A silently disabled FormatChecker is invisible: every fixture keeps passing. This
    check fails loudly if the installed environment cannot validate the formats the
    contract relies on.
    """
    errors: list[str] = []
    validator = build_validator(schema)

    probes = (
        ("date-time", {"type": "string", "format": "date-time"}, "definitely-not-a-timestamp"),
        ("uuid", {"type": "string", "format": "uuid"}, "not-a-uuid"),
    )
    for name, subschema, invalid in probes:
        probe = Draft202012Validator(subschema, format_checker=validator.format_checker)
        if probe.is_valid(invalid):
            errors.append(
                f"format '{name}' is not being enforced; install the jsonschema[format] "
                "extra so the contract rejects malformed values"
            )
    return errors


def check_state_schema(schema: dict[str, Any]) -> list[str]:
    """Confirm the state contract is a usable JSON Schema document."""
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as error:  # noqa: BLE001 - surfaced verbatim to the operator
        return [f"state schema is not a valid draft 2020-12 document: {error}"]
    return []


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def check_workflow(workflow: dict[str, Any]) -> list[str]:
    """Confirm the workflow definition is internally consistent."""
    errors: list[str] = []

    states: dict[str, Any] = workflow.get("states", {})
    transitions: list[dict[str, Any]] = workflow.get("transitions", [])
    decision_points: dict[str, Any] = workflow.get("decision_points", {})
    initial_state: str = workflow.get("initial_state", "")
    terminal_states: set[str] = set(workflow.get("terminal_states", []))

    if initial_state not in states:
        errors.append(f"initial_state '{initial_state}' is not a declared state")

    for terminal in terminal_states:
        if terminal not in states:
            errors.append(f"terminal state '{terminal}' is not a declared state")

    # Declared terminal flags and the terminal_states list must agree.
    for name, definition in states.items():
        flagged = bool((definition or {}).get("terminal", False))
        listed = name in terminal_states
        if flagged != listed:
            errors.append(
                f"state '{name}' disagrees on terminality: "
                f"terminal flag={flagged}, listed in terminal_states={listed}"
            )

    # Decision points must reference declared states.
    for name, definition in decision_points.items():
        state = (definition or {}).get("state")
        if state not in states:
            errors.append(f"decision point '{name}' references unknown state '{state}'")
        for actor in _as_list((definition or {}).get("actor")):
            if actor not in VALID_ACTORS:
                errors.append(f"decision point '{name}' declares unknown actor '{actor}'")

    transition_ids: set[str] = set()
    reachable: set[str] = {initial_state}

    for transition in transitions:
        identifier = transition.get("id", "<missing id>")

        if identifier in transition_ids:
            errors.append(f"duplicate transition id '{identifier}'")
        transition_ids.add(identifier)

        source = transition.get("from")
        target = transition.get("to")

        if source not in states:
            errors.append(f"transition '{identifier}' leaves unknown state '{source}'")
        if target not in states:
            errors.append(f"transition '{identifier}' enters unknown state '{target}'")

        if source in terminal_states:
            errors.append(
                f"transition '{identifier}' leaves terminal state '{source}'; "
                "terminal states must have no outgoing transitions"
            )

        actors = _as_list(transition.get("actor"))
        if not actors:
            errors.append(f"transition '{identifier}' must declare at least one actor")
        for actor in actors:
            if actor not in VALID_ACTORS:
                errors.append(f"transition '{identifier}' declares unknown actor '{actor}'")

        requires_approval = transition.get("requires_approval")
        if not isinstance(requires_approval, bool):
            errors.append(f"transition '{identifier}' must declare requires_approval as a boolean")

        decision_point = transition.get("decision_point")
        if decision_point is not None:
            definition = decision_points.get(decision_point)
            if definition is None:
                errors.append(
                    f"transition '{identifier}' references unknown "
                    f"decision point '{decision_point}'"
                )
            else:
                declared_outcomes = set(definition.get("outcomes", []))
                for outcome in _as_list(transition.get("on_outcome")):
                    if outcome not in declared_outcomes:
                        errors.append(
                            f"transition '{identifier}' uses outcome '{outcome}' "
                            f"not declared by decision point '{decision_point}'"
                        )
                if definition.get("state") != source:
                    errors.append(
                        f"transition '{identifier}' evaluates decision point "
                        f"'{decision_point}' declared for state "
                        f"'{definition.get('state')}' but leaves '{source}'"
                    )

        # Protected transitions are derived from the workflow contract itself:
        # blocking approval outcomes and closure both require a human approval.
        protected = target == "closed"
        if decision_point in decision_points:
            blocking = bool(decision_points[decision_point].get("blocking", False))
            approves = "approve" in _as_list(transition.get("on_outcome"))
            protected = protected or (blocking and approves)

        if protected:
            if requires_approval is not True:
                errors.append(f"protected transition '{identifier}' must require approval")
            if actors != ["human"]:
                errors.append(f"protected transition '{identifier}' must be human-only")
            if transition.get("records_approval") is not True:
                errors.append(f"protected transition '{identifier}' must record an approval")

    # Reachability: fixed point over the declared transitions.
    changed = True
    while changed:
        changed = False
        for transition in transitions:
            if transition.get("from") in reachable and transition.get("to") not in reachable:
                reachable.add(transition["to"])
                changed = True

    for name in states:
        if name not in reachable:
            errors.append(f"state '{name}' is unreachable from '{initial_state}'")

    # Required behaviour of the approved flow.
    returns_to_investigation = any(
        transition.get("from") == "verifying" and transition.get("to") == "investigating"
        for transition in transitions
    )
    if not returns_to_investigation:
        errors.append("a failed verification cannot return to investigating")

    closing = [transition for transition in transitions if transition.get("to") == "closed"]
    if not closing:
        errors.append("no transition reaches 'closed'")
    for transition in closing:
        if transition.get("from") != "postmortem":
            errors.append(
                f"transition '{transition.get('id')}' closes the session without "
                "passing through 'postmortem'"
            )

    # Every state allowing an agentic step must name the objective it hands the harness.
    for name, definition in states.items():
        definition = definition or {}
        if definition.get("allows_agentic_step") and not definition.get("agent_objective"):
            errors.append(f"state '{name}' allows an agentic step without an agent_objective")

    return errors


def _fixture_paths() -> tuple[list[Path], list[Path]]:
    positive = sorted(
        path
        for path in FIXTURES_ROOT.rglob("*.yaml")
        if "negative" not in path.relative_to(FIXTURES_ROOT).parts
    )
    negative = sorted(FIXTURES_ROOT.rglob("negative/*.yaml"))
    return positive, negative


def check_fixtures(schema: dict[str, Any]) -> list[str]:
    """Positive fixtures must validate; negative fixtures must fail."""
    errors: list[str] = []
    validator = build_validator(schema)
    positive, negative = _fixture_paths()

    if not positive:
        errors.append(f"no positive fixture found under {FIXTURES_ROOT}")
    if not negative:
        errors.append(f"no negative fixture found under {FIXTURES_ROOT}")

    for path in positive:
        problems = sorted(validator.iter_errors(load_yaml(path)), key=lambda item: item.path)
        for problem in problems:
            location = "/".join(str(part) for part in problem.path) or "<root>"
            errors.append(f"positive fixture '{path.name}' failed at {location}: {problem.message}")

    for path in negative:
        if validator.is_valid(load_yaml(path)):
            errors.append(
                f"negative fixture '{path.name}' was accepted; the schema does not "
                "enforce the rule it encodes"
            )

    return errors


def check_workflow_state_alignment(workflow: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """The workflow states and the schema state enum must not drift apart."""
    workflow_states = set(workflow.get("states", {}))
    schema_states = set(schema.get("properties", {}).get("state", {}).get("enum", []))

    errors: list[str] = []
    workflow_version = workflow.get("workflow_version")
    schema_version = schema.get("properties", {}).get("workflow_version", {}).get("const")
    if workflow_version != schema_version:
        errors.append(
            f"workflow_version {workflow_version!r} is incompatible with "
            f"state schema version {schema_version!r}"
        )
    for name in sorted(workflow_states - schema_states):
        errors.append(f"state '{name}' exists in the workflow but not in the state schema enum")
    for name in sorted(schema_states - workflow_states):
        errors.append(f"state '{name}' exists in the state schema enum but not in the workflow")

    workflow_points = set(workflow.get("decision_points", {}))
    schema_points = set(
        schema.get("$defs", {})
        .get("decision", {})
        .get("properties", {})
        .get("decision_point", {})
        .get("enum", [])
    )
    for name in sorted(workflow_points ^ schema_points):
        errors.append(f"decision point '{name}' is declared in only one of the two contracts")

    return errors


def _resolve_schema_path(schema: dict[str, Any], path: str) -> bool:
    """Resolve a dotted `required_inputs` path against the state schema.

    Only the first two segments are resolved: the top-level property, and one level
    inside it. That covers every path the workflow declares today and keeps the check
    readable without reimplementing a JSON Pointer resolver.
    """
    head, _, tail = path.partition(".")
    node = schema.get("properties", {}).get(head)
    if node is None:
        return False
    if not tail:
        return True

    # Follow arrays and local $refs to reach the object that owns the nested key.
    if node.get("type") == "array":
        node = node.get("items", {})
    ref = node.get("$ref") or next(
        (option.get("$ref") for option in node.get("oneOf", []) if option.get("$ref")), None
    )
    if ref and ref.startswith("#/$defs/"):
        node = schema.get("$defs", {}).get(ref.split("/")[-1], {})
    return tail in node.get("properties", {})


def check_decision_point_inputs(workflow: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Every `required_inputs` entry must name something the state actually carries.

    A consumer that reads these as paths would look up a key that does not exist, and
    the divergence is invisible until runtime. Checking them here keeps the workflow
    and the state contract from drifting apart.
    """
    errors: list[str] = []
    for name, definition in workflow.get("decision_points", {}).items():
        for path in (definition or {}).get("required_inputs", []):
            if not _resolve_schema_path(schema, path):
                errors.append(
                    f"decision point '{name}' requires input '{path}', which does not "
                    "resolve against the incident state schema"
                )
    return errors


def check_process_stage_mapping(workflow: dict[str, Any]) -> list[str]:
    """Enforce the deliverable "mapeo estados operativos <-> fases del flujo".

    While the mapping is declared pending, empty lists are tolerated. Once it is
    declared complete, every phase in the range must be covered by at least one
    state, and no state may claim a phase outside the range. Several states may
    share a phase (e.g. dismissed and linked both belong to alert management).
    """
    errors: list[str] = []

    status = workflow.get("process_stage_mapping_status")
    if status not in {"pending_reconciliation", "complete"}:
        errors.append(
            "process_stage_mapping_status must be 'pending_reconciliation' or 'complete', "
            f"found {status!r}"
        )
        return errors

    stage_range = workflow.get("process_stage_range", [0, 11])
    expected = set(range(stage_range[0], stage_range[1] + 1))

    claimed: dict[int, list[str]] = {}
    for name, definition in workflow.get("states", {}).items():
        for stage in (definition or {}).get("process_stages") or []:
            if not isinstance(stage, int) or stage not in expected:
                errors.append(
                    f"state '{name}' claims process stage {stage!r}, outside "
                    f"{stage_range[0]}-{stage_range[1]}"
                )
                continue
            claimed.setdefault(stage, []).append(name)

    if status == "complete":
        missing = sorted(expected - set(claimed))
        if missing:
            errors.append(
                "process_stage_mapping_status is 'complete' but these stages are "
                f"unmapped: {missing}"
            )

    return errors


def validate() -> list[str]:
    """Run every check and return the accumulated errors."""
    workflow = load_yaml(WORKFLOW_PATH)
    schema = load_yaml(STATE_SCHEMA_PATH)

    return [
        *check_state_schema(schema),
        *check_format_enforcement(schema),
        *check_workflow(workflow),
        *check_decision_point_inputs(workflow, schema),
        *check_process_stage_mapping(workflow),
        *check_workflow_state_alignment(workflow, schema),
        *check_fixtures(schema),
    ]


def main() -> int:
    try:
        errors = validate()
    except FileNotFoundError as error:
        print(f"incident contracts: {error}", file=sys.stderr)
        return 1

    if errors:
        print(f"incident contracts: {len(errors)} problem(s) found", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    workflow = load_yaml(WORKFLOW_PATH)
    positive, negative = _fixture_paths()
    mapping = workflow.get("process_stage_mapping_status")
    print(
        "incident contracts: OK "
        f"({len(workflow.get('states', {}))} states, "
        f"{len(workflow.get('transitions', []))} transitions, "
        f"{len(workflow.get('decision_points', {}))} decision points, "
        f"{len(positive)} positive and {len(negative)} negative fixtures; "
        f"process stage mapping: {mapping})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
