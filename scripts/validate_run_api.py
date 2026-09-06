"""Validate the incident run API contract (HT-INC-04, issue #145).

Automated acceptance gate for the run API. Runs in CI and locally with:

    python scripts/validate_run_api.py

Checks:
1. Every request/response schema is a well-formed JSON Schema draft 2020-12 document.
2. The OpenAPI document is parseable, declares the four required paths, and every
   local $ref resolves.
3. Positive examples validate against their schema; negative examples are rejected.
4. `format` is actually enforced (date-time, uuid), not merely annotated.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT = REPOSITORY_ROOT / "agent"
OPENAPI_PATH = AGENT / "api" / "incident-runs.openapi.yaml"
EXAMPLES = AGENT / "api" / "examples"
CORRELATION_PATH = AGENT / "api" / "correlation-mapping.v1.yaml"
TRANSPORT_ADR_PATH = REPOSITORY_ROOT / "docs" / "adrs" / "ADR-008-run-events-transport.md"
AUTHORIZATION_PATH = AGENT / "api" / "authorization.v1.yaml"
PROJECTION_PATH = AGENT / "api" / "projection-policy.v1.yaml"

SCHEMAS = {
    "run-context": AGENT / "schemas" / "run-context.schema.yaml",
    "run-start-request": AGENT / "schemas" / "run-start-request.schema.yaml",
    "run-state": AGENT / "schemas" / "run-state.schema.yaml",
    "run-command": AGENT / "schemas" / "run-command.schema.yaml",
    "run-event": AGENT / "schemas" / "run-event.schema.yaml",
}

REQUIRED_PATHS = {
    "/v1/incidents/{incident_id}/runs",
    "/v1/incidents/{incident_id}/runs/{run_id}",
    "/v1/incidents/{incident_id}/runs/{run_id}/commands",
    "/v1/incidents/{incident_id}/runs/{run_id}/events",
}

# Which schema each example validates against.
POSITIVE = {
    "start-request.json": "run-start-request",
    "run-state-running.json": "run-state",
    "run-state-awaiting.json": "run-state",
    "command-approve.json": "run-command",
    "events-page.json": "run-event",
    "run-context.json": "run-context",
}
NEGATIVE = {
    "start-foreign-version.json": "run-start-request",
    "command-by-agent.json": "run-command",
    "state-unknown-status.json": "run-state",
    "command-without-actor-identity.json": "run-command",
    "event-leaks-raw-turn-as-task.json": "run-event",
    "context-leaks-raw-turn.json": "run-context",
}


def load_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"required contract file is missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def build_validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def check_schemas() -> tuple[dict[str, dict], list[str]]:
    errors: list[str] = []
    schemas: dict[str, dict] = {}
    for name, path in SCHEMAS.items():
        schema = load_yaml(path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:  # noqa: BLE001
            errors.append(f"schema '{name}' is not valid draft 2020-12: {error}")
            continue
        schemas[name] = schema
    return schemas, errors


def check_format_enforcement() -> list[str]:
    checker = FormatChecker()
    errors: list[str] = []
    for name, subschema, bad in (
        ("date-time", {"type": "string", "format": "date-time"}, "not-a-timestamp"),
        ("uuid", {"type": "string", "format": "uuid"}, "not-a-uuid"),
    ):
        if Draft202012Validator({**subschema}, format_checker=checker).is_valid(bad):
            errors.append(f"format '{name}' is not enforced; install the jsonschema[format] extra")
    return errors


def _declared_property_names(node: Any, found: set[str]) -> None:
    """Collect every property name a schema declares, at any depth.

    The walk descends into the property subschemas as well as their names. Without that
    it stops one level short, and a sensitive field nested inside an object property
    would never be seen: exactly the blind spot the safe projection cannot afford.
    """
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            found.update(properties)
            for subschema in properties.values():
                _declared_property_names(subschema, found)
        for key, value in node.items():
            if key != "properties":
                _declared_property_names(value, found)
    elif isinstance(node, list):
        for item in node:
            _declared_property_names(item, found)


def check_safe_projection() -> list[str]:
    """Audit finding C07: prove the public snapshot cannot carry sensitive content.

    The policy is an allow-list because a deny-list fails open: a field added later leaks
    until somebody remembers to ban it. Walking the schemas here makes the policy fail
    closed instead, the same way the compose allow-list keeps a provider credential out of
    a client image (docs/architecture.md).
    """
    errors: list[str] = []
    policy = load_yaml(PROJECTION_PATH)
    safe = policy["safe_projection"]
    allowed = set(safe["allowed_fields"])
    forbidden = set(policy["forbidden_in_safe_projection"])

    overlap = allowed & forbidden
    if overlap:
        errors.append(f"fields are both allowed and forbidden: {sorted(overlap)}")

    for relative in safe["schemas"]:
        path = REPOSITORY_ROOT / relative
        if not path.exists():
            errors.append(f"safe projection schema '{relative}' does not exist")
            continue
        declared: set[str] = set()
        _declared_property_names(load_yaml(path), declared)

        for name in sorted(declared & forbidden):
            errors.append(
                f"'{relative}' declares '{name}', which the projection policy forbids in "
                "a safe projection"
            )
        for name in sorted(declared - allowed - forbidden):
            errors.append(
                f"'{relative}' declares '{name}', which is not registered in the "
                "projection allow-list; register it or move it behind the context endpoint"
            )

    # The sensitive context must be a separate surface with its own action.
    context = policy["sensitive_context"]
    if context["authorized_by"] == safe["authorized_by"]:
        errors.append(
            "the sensitive context is authorized by the same action as the safe "
            "projection; C07 requires them to be separable"
        )
    if not (REPOSITORY_ROOT / context["schema"]).exists():
        errors.append(f"sensitive context schema '{context['schema']}' does not exist")

    api = load_yaml(OPENAPI_PATH)
    context_path = "/v1/incidents/{incident_id}/runs/{run_id}/context"
    if context_path not in api["paths"]:
        errors.append("the OpenAPI does not expose the sensitive context endpoint")

    return errors


def check_transport_decision() -> list[str]:
    """The polling/SSE decision is a deliverable of the issue, not an implicit choice.

    The contract encodes polling in `GET .../events`; without the ADR beside it a reader
    cannot tell whether streaming was rejected or simply forgotten.
    """
    errors: list[str] = []
    if not TRANSPORT_ADR_PATH.exists():
        return [f"the transport decision record is missing: {TRANSPORT_ADR_PATH}"]

    adr = TRANSPORT_ADR_PATH.read_text(encoding="utf-8")
    if "Status: Accepted" not in adr:
        errors.append("the transport ADR is not marked Accepted")
    if "SSE" not in adr:
        errors.append("the transport ADR does not record the alternative it rejected")

    api = OPENAPI_PATH.read_text(encoding="utf-8")
    if "text/event-stream" in api:
        errors.append("the API declares a streaming media type while the ADR decides polling")
    return errors


def check_correlation_mapping(schemas: dict[str, Any]) -> list[str]:
    """Audit finding C05: turn_id is domain-internal and must never reach the gateway.

    The mapping document is only a promise until something asserts it, so the derivation
    is replayed here and the identifiers that may cross the boundary are pinned.
    """
    errors: list[str] = []
    mapping = load_yaml(CORRELATION_PATH)

    crossing = {item["name"] for item in mapping["identifiers"] if item.get("crosses_to_gateway")}
    if "turn_id" in crossing:
        errors.append("turn_id is marked as crossing to the gateway; C05 forbids it")
    for required in ("incident_id", "run_id", "task_id"):
        if required not in crossing:
            errors.append(f"'{required}' must be declared as crossing to the gateway")

    derivation = mapping["derivation"]
    if derivation.get("from") != "turn_id" or derivation.get("to") != "task_id":
        errors.append("the derivation must map turn_id to task_id")

    # Replay every documented example, including an all-numeric suffix, against the
    # deterministic total rule and both destination schemas.
    event_task = schemas["run-event"]["$defs"]["event"]["properties"]["task_id"]
    incident_task = load_yaml(AGENT / "schemas" / "incident-state.schema.yaml")["properties"][
        "task_id"
    ]
    for name in ("example", "numeric_suffix_example"):
        example = derivation.get(name, {})
        turn_id, task_id = example.get("turn_id", ""), example.get("task_id", "")
        expected = f"task_{turn_id.removeprefix('turn_')}"
        if not turn_id.startswith("turn_") or task_id != expected:
            errors.append(
                f"the documented {name} does not follow the rule: {turn_id!r} -> {task_id!r}"
            )
        for schema_name, task_schema in (
            ("run-event", event_task),
            ("incident-state", incident_task),
        ):
            if not build_validator(task_schema).is_valid(task_id):
                errors.append(f"derived task_id {task_id!r} is invalid in {schema_name}")

    # Both identifiers must exist in the schemas that carry them.
    event_props = schemas["run-event"]["$defs"]["event"]["properties"]
    for field in ("turn_id", "task_id"):
        if field not in event_props:
            errors.append(f"run-event does not carry '{field}'")
    if "turn_id" not in schemas["run-command"]["properties"]:
        errors.append("run-command does not carry 'turn_id'")

    return errors


def check_authorization_contract(schemas: dict[str, Any]) -> list[str]:
    """Command assertions must match the canonical authorization vocabulary."""
    errors: list[str] = []
    vocabulary = load_yaml(AUTHORIZATION_PATH)
    command = schemas["run-command"]
    authorization = command["properties"].get("authorization", {})
    props = authorization.get("properties", {})
    resource_props = props.get("resource", {}).get("properties", {})

    expected_action = vocabulary.get("command_action_map", {}).get("approve_mitigation")
    resource = next(
        (item for item in vocabulary.get("resources", []) if item.get("id") == "incident-response"),
        {},
    )
    if props.get("action", {}).get("const") != expected_action:
        errors.append("run-command approval action differs from authorization.v1.yaml")
    if resource_props.get("type", {}).get("const") != resource.get("type"):
        errors.append("run-command resource type differs from authorization.v1.yaml")
    if resource_props.get("id", {}).get("const") != resource.get("id"):
        errors.append("run-command resource id differs from authorization.v1.yaml")
    return errors


def check_actor_identity(schemas: dict[str, Any]) -> list[str]:
    """Audit finding C06: record the concrete actor, not only its type.

    The type is kept so existing consumers keep working; the reference is added beside
    it. A command is always attributable, so its reference is required.
    """
    errors: list[str] = []

    command = schemas["run-command"]
    if "actor" not in command["properties"]:
        errors.append("run-command dropped the actor type; C06 must be additive")
    if "actor_reference" not in command.get("required", []):
        errors.append("run-command must require actor_reference: a command is attributable")

    reference = command["properties"].get("actor_reference", {})
    for field in ("reference_version", "principal_id"):
        if field not in reference.get("required", []):
            errors.append(f"actor_reference must require '{field}'")
    if "const" not in reference.get("properties", {}).get("reference_version", {}):
        errors.append("actor_reference must pin its version with const")

    event_actor = schemas["run-event"]["$defs"]["event"]["properties"].get("actor", {})
    if "type" not in event_actor.get("required", []):
        errors.append("run-event actor must still require its type")
    if "reference" not in event_actor.get("properties", {}):
        errors.append("run-event actor must be able to carry a concrete reference")

    return errors


def check_openapi() -> list[str]:
    errors: list[str] = []
    doc = load_yaml(OPENAPI_PATH)

    if doc.get("openapi", "").split(".")[0] != "3":
        errors.append("openapi document is not version 3.x")

    declared = set(doc.get("paths", {}))
    for path in REQUIRED_PATHS - declared:
        errors.append(f"openapi is missing required path '{path}'")

    # Every local component $ref must resolve.
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    import re

    for ref in re.findall(r"#/components/([a-zA-Z]+)/([A-Za-z0-9]+)", text):
        section, name = ref
        if name not in doc.get("components", {}).get(section, {}):
            errors.append(f"openapi $ref '#/components/{section}/{name}' does not resolve")

    return errors


def check_examples(schemas: dict[str, dict]) -> list[str]:
    errors: list[str] = []

    for filename, schema_name in POSITIVE.items():
        path = EXAMPLES / filename
        if not path.exists():
            errors.append(f"positive example '{filename}' is missing")
            continue
        problems = list(build_validator(schemas[schema_name]).iter_errors(load_json(path)))
        for problem in problems:
            errors.append(f"positive example '{filename}' failed: {problem.message}")

    for filename, schema_name in NEGATIVE.items():
        path = EXAMPLES / "negative" / filename
        if not path.exists():
            errors.append(f"negative example '{filename}' is missing")
            continue
        if build_validator(schemas[schema_name]).is_valid(load_json(path)):
            errors.append(
                f"negative example '{filename}' was accepted; the schema does not "
                "enforce the rule it encodes"
            )

    return errors


def validate() -> list[str]:
    schemas, schema_errors = check_schemas()
    errors = [*schema_errors, *check_format_enforcement(), *check_openapi()]
    if schemas:
        errors.extend(check_safe_projection())
        errors.extend(check_transport_decision())
        errors.extend(check_correlation_mapping(schemas))
        errors.extend(check_actor_identity(schemas))
        errors.extend(check_authorization_contract(schemas))
        errors.extend(check_examples(schemas))
    return errors


def main() -> int:
    try:
        errors = validate()
    except FileNotFoundError as error:
        print(f"run api: {error}", file=sys.stderr)
        return 1

    if errors:
        print(f"run api: {len(errors)} problem(s) found", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    doc = load_yaml(OPENAPI_PATH)
    print(
        f"run api: OK ({len(doc.get('paths', {}))} paths, {len(SCHEMAS)} schemas, "
        f"{len(POSITIVE)} positive and {len(NEGATIVE)} negative examples)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
