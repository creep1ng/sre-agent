"""Validate the incident query contract (HT-INC-RUNTIME-B, issue #189).

Automated acceptance gate for the read surface consumed by the war room.
Runs in CI and locally with:

    python scripts/validate_incident_queries.py

Checks:
1. The incident detail/snapshot schemas are well-formed JSON Schema draft
   2020-12 documents with immutable URN ids.
2. The queries OpenAPI document is parseable, declares its three paths, and
   every $ref resolves (URN registry plus local example files).
3. Positive examples validate against their schema; error examples carry a
   value validating against the shared 2.0.0 error envelope.
4. The projection policy registers the new safe schemas (fail closed).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT = REPOSITORY_ROOT / "agent"
OPENAPI_PATH = AGENT / "api" / "incident-queries.openapi.yaml"
EXAMPLES = AGENT / "api" / "examples" / "queries"
PROJECTION_PATH = AGENT / "api" / "projection-policy.v1.yaml"
ERROR_ENVELOPE_PATH = (
    REPOSITORY_ROOT
    / "schemas"
    / "releases"
    / "2.0.0"
    / "json-schema"
    / "http"
    / "error-envelope.schema.json"
)
RUN_EVENT_SCHEMA_PATH = AGENT / "schemas" / "run-event.schema.yaml"
URN_REFERENCE = re.compile(r"^urn:sre-agent:schema:[a-z][a-z0-9-]*:[0-9]+\.[0-9]+\.[0-9]+$")

SCHEMAS = {
    "incident-detail": AGENT / "schemas" / "incident-detail.schema.yaml",
    "incident-snapshot": AGENT / "schemas" / "incident-snapshot.schema.yaml",
}

# Stable retrieval base so relative file references between schemas resolve.
SCHEMA_BASE = "https://sre-agent.local/agent/schemas/"

REQUIRED_PATHS = {
    "/v1/incidents/{incident_id}",
    "/v1/incidents/{incident_id}/timeline",
    "/v1/incidents/{incident_id}/snapshot",
}

POSITIVE = {
    "detail.json": "incident-detail",
    "timeline-page.json": "run-event",
    "snapshot.json": "incident-snapshot",
}

ERROR_EXAMPLES = {
    "error-401.json",
    "error-403.json",
    "error-404.json",
    "error-422.json",
    "error-503.json",
}


def load_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"required contract file is missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry(schemas: dict[str, dict]) -> Registry:
    resources: list[tuple[str, Resource]] = []
    for name, schema in schemas.items():
        schema_id = schema.get("$id", "")
        resources.append((schema_id, Resource.from_contents(schema)))
        if name in SCHEMAS:
            base = f"{SCHEMA_BASE}{SCHEMAS[name].name}"
            resources.append((base, Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def check_schemas() -> tuple[dict[str, dict], list[str]]:
    errors: list[str] = []
    schemas: dict[str, dict] = {}
    for name, path in SCHEMAS.items():
        try:
            schema = load_yaml(path)
            Draft202012Validator.check_schema(schema)
        except Exception as error:  # noqa: BLE001
            errors.append(f"schema '{name}' is not valid draft 2020-12: {error}")
            continue
        schema_id = schema.get("$id", "")
        if not URN_REFERENCE.fullmatch(schema_id):
            errors.append(f"schema '{name}' has malformed immutable $id {schema_id!r}")
            continue
        schemas[name] = schema
    run_event = load_yaml(RUN_EVENT_SCHEMA_PATH)
    schemas["run-event"] = run_event
    try:
        envelope = load_json(ERROR_ENVELOPE_PATH)
        Draft202012Validator.check_schema(envelope)
    except Exception as error:  # noqa: BLE001
        errors.append(f"shared error envelope is invalid: {error}")
        return schemas, errors
    schemas["error-envelope"] = envelope
    return schemas, errors


def _iter_refs(node: Any) -> list[str]:
    if isinstance(node, dict):
        refs = [value for key, value in node.items() if key == "$ref" and isinstance(value, str)]
        return refs + [ref for value in node.values() for ref in _iter_refs(value)]
    if isinstance(node, list):
        return [ref for value in node for ref in _iter_refs(value)]
    return []


def check_openapi(registry: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    try:
        doc = load_yaml(OPENAPI_PATH)
    except FileNotFoundError as error:
        return [str(error)]
    if doc.get("openapi", "").split(".")[0] != "3":
        errors.append("openapi document is not version 3.x")
    for path in sorted(REQUIRED_PATHS - set(doc.get("paths", {}))):
        errors.append(f"openapi is missing required path '{path}'")
    by_id = {
        schema["$id"]: name
        for name, schema in registry.items()
        if isinstance(schema.get("$id"), str)
    }
    for ref in _iter_refs(doc):
        if ref.startswith("#/"):
            continue
        if ref.startswith("urn:"):
            if ref not in by_id:
                errors.append(f"openapi references unknown schema '{ref}'")
        elif ref.startswith("./examples/"):
            if not (AGENT / "api" / ref[2:]).exists():
                errors.append(f"openapi references missing example '{ref}'")
        else:
            errors.append(f"openapi uses unsupported reference '{ref}'")
    return errors


def check_examples(registry: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    resolved = dict(registry)
    snapshot = json.loads(json.dumps(resolved["incident-snapshot"]))
    snapshot["properties"]["incident"]["$ref"] = f"{SCHEMA_BASE}incident-detail.schema.yaml"
    resolved["incident-snapshot"] = snapshot
    validators = {
        name: Draft202012Validator(
            schema, registry=_registry(resolved), format_checker=FormatChecker()
        )  # noqa: E501
        for name, schema in resolved.items()
        if name in ("incident-detail", "incident-snapshot", "run-event", "error-envelope")
    }
    for filename, schema_name in POSITIVE.items():
        path = EXAMPLES / filename
        if not path.exists():
            errors.append(f"positive example '{filename}' is missing")
            continue
        problems = sorted(
            validators[schema_name].iter_errors(load_json(path)), key=lambda item: item.path
        )
        for problem in problems:
            location = "/".join(str(part) for part in problem.path) or "<root>"
            errors.append(f"positive example '{filename}' failed at {location}: {problem.message}")
    for filename in sorted(ERROR_EXAMPLES):
        path = EXAMPLES / filename
        if not path.exists():
            errors.append(f"error example '{filename}' is missing")
            continue
        document = load_json(path)
        problems = sorted(
            validators["error-envelope"].iter_errors(document.get("value")),
            key=lambda item: item.path,
        )
        for problem in problems:
            location = "/".join(str(part) for part in problem.path) or "<root>"
            errors.append(f"error example '{filename}' failed at {location}: {problem.message}")
    return errors


def check_projection_registration() -> list[str]:
    policy = load_yaml(PROJECTION_PATH)
    listed = set(policy.get("safe_projection", {}).get("schemas", []))
    missing = {
        "agent/schemas/incident-detail.schema.yaml",
        "agent/schemas/incident-snapshot.schema.yaml",
    } - listed
    if missing:
        return [f"projection policy does not register safe schemas: {sorted(missing)}"]
    return []


def validate() -> list[str]:
    schemas, errors = check_schemas()
    if not errors:
        errors.extend(check_openapi(schemas))
        errors.extend(check_examples(schemas))
    errors.extend(check_projection_registration())
    return errors


def main() -> int:
    try:
        errors = validate()
    except FileNotFoundError as error:
        print(f"incident queries: {error}", file=sys.stderr)
        return 1
    if errors:
        print(f"incident queries: {len(errors)} problem(s) found", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("incident queries: OK (2 schemas, 3 paths, 3 positive and 5 error examples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
