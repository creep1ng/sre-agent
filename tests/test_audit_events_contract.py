"""The published v2.3.0 control-plane contract owns audit read semantics."""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).parents[1]
RELEASE = ROOT / "schemas/releases/2.3.0"
OPENAPI = yaml.safe_load((RELEASE / "openapi/control-plane.yaml").read_text())
SCHEMA_PATHS = sorted((RELEASE / "json-schema").rglob("*.schema.json"))
SCHEMAS = [json.loads(path.read_text()) for path in SCHEMA_PATHS]
BY_ID = {schema["$id"]: schema for schema in SCHEMAS}
AUDIT_METADATA = BY_ID["urn:sre-agent:schema:audit-event-metadata:2.3.0"]


def _resolve_local(document: dict, reference: str) -> bool:
    current = document
    for token in reference.removeprefix("#/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            return False
        current = current[token]
    return True


def _parameters(operation: dict) -> dict[str, dict]:
    resolved = {}
    for parameter in operation.get("parameters", []):
        if "$ref" in parameter:
            name = parameter["$ref"].rsplit("/", 1)[1]
            parameter = OPENAPI["components"]["parameters"][name]
        resolved[parameter["name"]] = parameter
    return resolved


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def test_versioned_audit_read_routes_filters_and_rejections() -> None:
    listing = OPENAPI["paths"]["/v1/audit-events"]["get"]
    detail = OPENAPI["paths"]["/v1/audit-events/{id}"]["get"]
    parameters = _parameters(listing)

    assert OPENAPI["info"]["version"] == "2.3.0"
    assert set(OPENAPI["paths"]) >= {"/v1/audit-events", "/v1/audit-events/{id}"}
    assert set(parameters) == {
        "principal_id",
        "decision",
        "model_alias_id",
        "request_id",
        "incident_id",
        "run_id",
        "task_id",
        "trace_id",
        "from",
        "to",
        "limit",
    }
    assert listing["x-required-query-any-of"] == [
        "principal_id",
        "decision",
        "model_alias_id",
        "request_id",
        "incident_id",
        "run_id",
        "task_id",
        "trace_id",
        "from",
        "to",
    ]
    assert parameters["limit"]["schema"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 100,
    }
    assert listing["x-forbidden-query-parameters"] == [
        "cursor",
        "page",
        "offset",
        "continuation_token",
        "next",
        "content",
        "raw_content",
        "redacted_content",
        "include_content",
    ]
    assert set(listing["responses"]) == {"200", "401", "403", "422", "503"}
    assert set(detail["responses"]) == {"200", "401", "403", "404", "422", "503"}
    assert detail["parameters"] == [{"$ref": "#/components/parameters/Id"}]
    assert listing["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/AuditEventList"
    )
    assert detail["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "urn:sre-agent:schema:audit-event-metadata:2.3.0"
    )


def test_versioned_audit_metadata_projection_is_closed_and_resolves() -> None:
    assert AUDIT_METADATA["unevaluatedProperties"] is False
    for schema in SCHEMAS:
        for item in _walk(schema):
            reference = item.get("$ref")
            if reference is None:
                continue
            if reference.startswith("#"):
                assert _resolve_local(schema, reference), reference
            else:
                assert reference in BY_ID, reference

    forbidden = {
        "prompt",
        "prompts",
        "provider_body",
        "model_output",
        "request_body",
        "response_body",
        "bearer_token",
        "api_key",
    }
    assert (
        not {
            key
            for schema in (AUDIT_METADATA, BY_ID["urn:sre-agent:schema:audit-event:2.3.0"])
            for item in _walk(schema)
            for key in item
        }
        & forbidden
    )


def test_published_metadata_example_validates_against_release_schema() -> None:
    registry = Registry().with_resources(
        [(schema_id, Resource.from_contents(schema)) for schema_id, schema in BY_ID.items()]
    )
    example = json.loads((RELEASE / "examples/audit/metadata-only.example.json").read_text())
    validator = Draft202012Validator(
        AUDIT_METADATA, registry=registry, format_checker=FormatChecker()
    )
    errors = list(validator.iter_errors(example))
    assert errors == []
    assert list(validator.iter_errors({**example, "redacted_content": "sensitive"}))


def test_release_openapi_references_resolve() -> None:
    references = [
        item["$ref"] for item in _walk(OPENAPI) if "$ref" in item and isinstance(item["$ref"], str)
    ]
    for reference in references:
        if reference.startswith("#"):
            assert _resolve_local(OPENAPI, reference), reference
        elif reference.startswith("urn:"):
            assert reference in BY_ID, reference
