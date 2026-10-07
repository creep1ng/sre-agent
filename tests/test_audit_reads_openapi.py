"""The runtime audit routes must describe the published 2.7 contract."""

from pathlib import Path
from typing import Any

import yaml

from sre_agent.application import create_application
from sre_agent.settings import Settings

CONTROL_PLANE = Path("schemas/releases/2.7.0/openapi/control-plane.yaml")
METADATA_SCHEMA = "urn:sre-agent:schema:audit-event-metadata:2.7.0"
AUDIT_LIST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items", "limit", "truncated"],
    "properties": {
        "items": {
            "type": "array",
            "maxItems": 100,
            "items": {"$ref": METADATA_SCHEMA},
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "truncated": {"type": "boolean"},
    },
}


def _runtime_document() -> dict[str, Any]:
    settings = Settings.from_environment(
        {
            "DATABASE_URL": "postgresql://unused",
            "AUDIT_HMAC_KEY": "openapi-test-hmac-key",
        }
    )
    return create_application(settings).openapi()


def _canonical_document() -> dict[str, Any]:
    return yaml.safe_load(CONTROL_PLANE.read_text())


def _resolve_parameter(parameter: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    reference = parameter.get("$ref")
    if reference is None:
        return parameter
    prefix = "#/components/parameters/"
    assert reference.startswith(prefix)
    return document["components"]["parameters"][reference.removeprefix(prefix)]


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_schema(schema: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if reference is not None:
        prefix = "#/components/schemas/"
        if not reference.startswith(prefix):
            return schema
        target = document["components"]["schemas"][reference.removeprefix(prefix)]
        return _merge(
            _resolve_schema(target, document),
            {
                key: _resolve_schema(value, document) if isinstance(value, dict) else value
                for key, value in schema.items()
                if key != "$ref"
            },
        )
    return {
        key: _resolve_schema(value, document) if isinstance(value, dict) else value
        for key, value in schema.items()
    }


def _resolve_response(response: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    reference = response.get("$ref")
    if reference is None:
        return response
    prefix = "#/components/responses/"
    assert reference.startswith(prefix)
    return document["components"]["responses"][reference.removeprefix(prefix)]


def _parameters(
    operation: dict[str, Any], document: dict[str, Any]
) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (item["in"], item["name"]): item
        for parameter in operation.get("parameters", [])
        if (item := _resolve_parameter(parameter, document))
    }


def test_runtime_audit_openapi_matches_published_27_contract() -> None:
    runtime, canonical = _runtime_document(), _canonical_document()
    assert runtime["info"]["x-sre-agent-contract-version"] == canonical["info"]["version"]
    assert (
        runtime["components"]["securitySchemes"]["bearerAuth"]
        == canonical["components"]["securitySchemes"]["bearerAuth"]
    )
    endpoints = {
        ("/v1/audit-events", "get"),
        ("/v1/audit-events/{id}", "get"),
    }
    assert endpoints <= {
        (path, method) for path, operations in runtime["paths"].items() for method in operations
    }
    assert endpoints <= {
        (path, method) for path, operations in canonical["paths"].items() for method in operations
    }

    for path, method in endpoints:
        actual = runtime["paths"][path][method]
        published = canonical["paths"][path][method]
        assert actual["operationId"] == published["operationId"]
        assert actual["summary"] == published["summary"]
        assert actual["tags"] == published["tags"]
        assert actual["security"] == canonical["security"]
        assert actual["x-governed-scope"] == {
            "action": "admin.read",
            "resource_type": "administrative_control",
            "resource_id": "audit",
        }
        parameter_keys = [
            (resolved["in"], resolved["name"])
            for item in actual.get("parameters", [])
            if (resolved := _resolve_parameter(item, runtime))
        ]
        assert len(parameter_keys) == len(set(parameter_keys)), (path, parameter_keys)
        actual_parameters = _parameters(actual, runtime)
        published_parameters = _parameters(published, canonical)
        assert set(actual_parameters) == set(published_parameters)
        for key, canonical_parameter in published_parameters.items():
            actual_parameter = actual_parameters[key]
            assert actual_parameter.get("required", False) == canonical_parameter.get(
                "required", False
            )
            actual_schema = dict(actual_parameter["schema"])
            actual_schema.pop("title", None)
            assert actual_schema == canonical_parameter["schema"]
        assert set(actual["responses"]) == set(published["responses"]), path
        for status, response in published["responses"].items():
            canonical_response = _resolve_response(response, canonical)
            assert actual["responses"][status]["description"] == canonical_response["description"]
            actual_content = actual["responses"][status].get("content", {})
            published_content = canonical_response.get("content", {})
            assert set(actual_content) == set(published_content), (path, status)
            for media_type, published_media in published_content.items():
                actual_media = actual_content[media_type]
                assert set(actual_media) == set(published_media), (path, status, media_type)
                if "schema" in published_media:
                    assert _resolve_schema(actual_media["schema"], runtime) == _resolve_schema(
                        published_media["schema"], canonical
                    ), (path, status, media_type)
            assert actual["responses"][status].get("headers", {}) == canonical_response.get(
                "headers", {}
            )

    listing = runtime["paths"]["/v1/audit-events"]["get"]
    assert listing["description"] == canonical["paths"]["/v1/audit-events"]["get"]["description"]
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
    list_schema = listing["responses"]["200"]["content"]["application/json"]["schema"]
    canonical_list_schema = _resolve_schema(
        canonical["paths"]["/v1/audit-events"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"],
        canonical,
    )
    assert list_schema == canonical_list_schema == AUDIT_LIST_SCHEMA

    detail = runtime["paths"]["/v1/audit-events/{id}"]["get"]
    detail_schema = detail["responses"]["200"]["content"]["application/json"]["schema"]
    assert detail_schema == {"$ref": METADATA_SCHEMA}
    canonical_detail_schema = canonical["paths"]["/v1/audit-events/{id}"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert detail_schema == canonical_detail_schema
