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

SCHEMAS = {
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
}
NEGATIVE = {
    "start-foreign-version.json": "run-start-request",
    "command-by-agent.json": "run-command",
    "state-unknown-status.json": "run-state",
    "command-without-actor-identity.json": "run-command",
    "event-leaks-raw-turn-as-task.json": "run-event",
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

    # Replay the documented example against the rule and the schema patterns.
    example = derivation.get("example", {})
    turn_id, task_id = example.get("turn_id", ""), example.get("task_id", "")
    if not turn_id.startswith("turn_") or turn_id[len("turn_") :] != task_id:
        errors.append(
            f"the documented example does not follow the rule: {turn_id!r} -> {task_id!r}"
        )
    if task_id.startswith("turn_"):
        errors.append("the derived task_id still carries the turn_ prefix")

    # Both identifiers must exist in the schemas that carry them.
    event_props = schemas["run-event"]["$defs"]["event"]["properties"]
    for field in ("turn_id", "task_id"):
        if field not in event_props:
            errors.append(f"run-event does not carry '{field}'")
    if "turn_id" not in schemas["run-command"]["properties"]:
        errors.append("run-command does not carry 'turn_id'")

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
        errors.extend(check_transport_decision())
        errors.extend(check_correlation_mapping(schemas))
        errors.extend(check_actor_identity(schemas))
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
