"""Issue #188 B1: audit events contract gates (OpenAPI + schemas + examples)."""

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
OPENAPI = yaml.safe_load((ROOT / "agent/api/audit-events.openapi.yaml").read_text())
SCHEMAS = {
    name: yaml.safe_load((ROOT / f"agent/schemas/{name}.schema.yaml").read_text())
    for name in ("audit-metadata", "audit-events-page")
}
ENVELOPE = json.loads(
    (ROOT / "schemas/releases/2.0.0/json-schema/http/error-envelope.schema.json").read_text()
)
URN = r"urn:sre-agent:schema:[a-z][a-z0-9-]*:[0-9]+\.[0-9]+\.[0-9]+"
APPROVED_FIELDS = {
    "event_id",
    "occurred_at",
    "operation",
    "action",
    "stage",
    "outcome",
    "reason_code",
    "authorization_denial_cause",
    "response_status",
    "retryable",
    "latency_ms",
    "correlation",
    "identity",
    "resource",
    "model_alias_ref",
    "policy_decision",
    "routing",
}
FORBIDDEN = {
    "consumption",
    "redacted_content",
    "prompts",
    "responses",
    "headers",
    "tool_arguments",
    "tool_calls",
    "content",
}


def _walk(node, refs):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            _walk(value, refs)
    elif isinstance(node, list):
        for value in node:
            _walk(value, refs)


def _resolve(doc, pointer):
    current = doc
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False
    return True


def _params():
    found = {}
    for entry in OPENAPI["paths"]["/v1/audit/events"]["get"]["parameters"]:
        if "$ref" in entry:
            node = OPENAPI
            for token in entry["$ref"][1:].split("/")[1:]:
                node = node[token]
            entry = node
        if "name" in entry:
            found[entry["name"]] = entry
    return found


def _forbidden(node, where, errors):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORBIDDEN:
                errors.append(f"forbidden field '{key}' at {where}")
            _forbidden(value, f"{where}.{key}", errors)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _forbidden(value, f"{where}[{index}]", errors)


def test_contract_schemas_paths_and_window() -> None:
    for name, schema in SCHEMAS.items():
        Draft202012Validator.check_schema(schema)
        assert re.fullmatch(URN, schema["$id"]), name
    assert OPENAPI["openapi"].split(".")[0] == "3"
    assert {"/v1/audit/events", "/v1/audit/events/{event_id}"} <= set(OPENAPI["paths"])
    params = _params()
    assert params["from"]["required"] is True and params["to"]["required"] is True
    assert params["limit"]["schema"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 50,
    }
    listing = set(OPENAPI["paths"]["/v1/audit/events"]["get"]["responses"])
    assert listing == {"200", "401", "403", "422", "503"}
    detail = set(OPENAPI["paths"]["/v1/audit/events/{event_id}"]["get"]["responses"])
    assert detail == {"200", "401", "403", "404", "503"}


def test_contract_refs_resolve() -> None:
    known = {s["$id"] for s in SCHEMAS.values()} | {ENVELOPE["$id"]}
    refs: list[str] = []
    _walk(OPENAPI, refs)
    for ref in refs:
        if ref.startswith("#"):
            assert _resolve(OPENAPI, ref[1:]), ref
        elif ref.startswith("urn:"):
            assert ref in known, ref
        else:
            assert (ROOT / "agent/api" / ref[2:]).exists(), ref


def test_metadata_projection_is_closed() -> None:
    assert set(SCHEMAS["audit-metadata"]["properties"]) == APPROVED_FIELDS
    errors: list[str] = []
    for name, schema in SCHEMAS.items():
        _forbidden(schema, f"schema:{name}", errors)
    assert errors == []


def test_contract_examples_validate() -> None:
    by_id = {s["$id"]: s for s in SCHEMAS.values()}
    by_id[ENVELOPE["$id"]] = ENVELOPE
    registry = Registry().with_resources(
        [(sid, Resource.from_contents(s)) for sid, s in by_id.items()]
    )
    cases = {
        "events-page.json": "urn:sre-agent:schema:audit-events-page:1.0.0",
        "event-detail.json": "urn:sre-agent:schema:audit-metadata:1.0.0",
        "error-422.json": "urn:sre-agent:schema:error-envelope:2.0.0",
        "error-503.json": "urn:sre-agent:schema:error-envelope:2.0.0",
    }
    errors: list[str] = []
    for filename, schema_id in cases.items():
        document = json.loads((ROOT / "agent/api/examples/audit-read" / filename).read_text())
        validator = Draft202012Validator(
            by_id[schema_id], registry=registry, format_checker=FormatChecker()
        )
        for problem in validator.iter_errors(document["value"]):
            errors.append(f"{filename}: {problem.message}")
        _forbidden(document["value"], f"example:{filename}", errors)
    assert errors == []
