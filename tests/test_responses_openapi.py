import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from sre_agent.gateway.responses import ResponsesRequest, responses_router
from sre_agent.governance.dto import Consumption
from sre_agent.release import CONTRACT_VERSION

RELEASES = Path("schemas/releases")


def active_responses_contract() -> tuple[Path, dict[str, Any]]:
    release = RELEASES / CONTRACT_VERSION
    assert (release / "manifest.yaml").is_file()
    assert (release / "openapi/responses.yaml").is_file()
    return release, yaml.safe_load((release / "openapi/responses.yaml").read_text())


def runtime_openapi(service: object | None = None) -> dict[str, Any]:
    application = FastAPI()
    application.include_router(responses_router(service))  # type: ignore[arg-type]
    return application.openapi()


def contract_schemas(release: Path) -> dict[str, dict[str, Any]]:
    return {
        document["$id"]: document
        for path in sorted((release / "json-schema").rglob("*.json"))
        if (document := json.loads(path.read_text())).get("$id")
    }


def dereference(
    schema: Any,
    components: dict[str, Any],
    release_schemas: dict[str, dict[str, Any]],
    document: dict[str, Any] | None = None,
) -> Any:
    if isinstance(schema, list):
        return [dereference(item, components, release_schemas, document) for item in schema]
    if not isinstance(schema, dict):
        return schema
    document = document or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        if reference.startswith("#/components/schemas/"):
            resolved = components[reference.removeprefix("#/components/schemas/")]
        elif reference.startswith("#/$defs/"):
            resolved = document["$defs"][reference.removeprefix("#/$defs/")]
        else:
            resolved = release_schemas[reference]
        resolved = dereference(resolved, components, release_schemas, resolved)
        siblings = {
            key: dereference(value, components, release_schemas, document)
            for key, value in schema.items()
            if key not in {"$ref", "description"}
        }
        return resolved | siblings
    normalized = {
        key: dereference(value, components, release_schemas, document)
        for key, value in schema.items()
        if key not in {"$id", "$schema", "$defs", "title", "description", "examples", "default"}
    }
    if "const" in normalized:
        normalized.pop("type", None)
    return normalized


def normalize_equivalent_schema_shapes(schema: Any) -> Any:
    """Normalize equivalent Pydantic and JSON Schema scalar encodings."""
    if isinstance(schema, list):
        return [normalize_equivalent_schema_shapes(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    normalized = {key: normalize_equivalent_schema_shapes(value) for key, value in schema.items()}
    if "enum" in normalized:
        normalized.pop("type", None)

    alternatives = normalized.get("anyOf")
    if isinstance(alternatives, list) and len(alternatives) == 2:
        value_schema = next((item for item in alternatives if item != {"type": "null"}), None)
        if value_schema is not None and {"type": "null"} in alternatives:
            if "enum" in value_schema:
                normalized["enum"] = [*value_schema["enum"], None]
                normalized.pop("anyOf")
            elif "const" in value_schema:
                normalized["enum"] = [value_schema["const"], None]
                normalized.pop("anyOf")
            elif set(value_schema) <= {"type", "minimum", "maxLength", "pattern"}:
                normalized.pop("anyOf")
                normalized.update(value_schema)
                normalized["type"] = [value_schema["type"], "null"]
    return normalized


def contract_schema(release: Path, reference: str) -> dict[str, Any]:
    name = reference.removeprefix("urn:sre-agent:schema:").rsplit(":", 1)[0]
    return json.loads((release / f"json-schema/http/{name}.schema.json").read_text())


def test_runtime_operation_documents_the_complete_responses_contract() -> None:
    release, contract = active_responses_contract()
    runtime = runtime_openapi()
    operation = runtime["paths"]["/v1/responses"]["post"]
    canonical = contract["paths"]["/v1/responses"]["post"]
    components = runtime["components"]["schemas"]
    release_schemas = contract_schemas(release)

    assert operation["operationId"] == canonical["operationId"]
    assert operation["summary"] == canonical["summary"]
    assert operation["security"] == [{"bearerAuth": []}]
    assert runtime["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert operation["requestBody"]["required"] is True
    assert set(operation["responses"]) == {"200", "401", "403", "422", "502", "503", "504"}

    runtime_request = operation["requestBody"]["content"]["application/json"]["schema"]
    contract_request = canonical["requestBody"]["content"]["application/json"]["schema"]
    assert normalize_equivalent_schema_shapes(
        dereference(runtime_request, components, release_schemas)
    ) == normalize_equivalent_schema_shapes(
        dereference(contract_schema(release, contract_request["$ref"]), components, release_schemas)
    )

    runtime_success = operation["responses"]["200"]["content"]["application/json"]["schema"]
    contract_success = canonical["responses"]["200"]["content"]["application/json"]["schema"]
    assert normalize_equivalent_schema_shapes(
        dereference(runtime_success, components, release_schemas)
    ) == normalize_equivalent_schema_shapes(
        dereference(contract_schema(release, contract_success["$ref"]), components, release_schemas)
    )

    for status in {"401", "403", "422", "502", "503", "504"}:
        runtime_error = operation["responses"][status]["content"]["application/json"]["schema"]
        canonical_response = contract["components"]["responses"][
            canonical["responses"][status]["$ref"].rsplit("/", 1)[-1]
        ]
        contract_error = canonical_response["content"]["application/json"]["schema"]
        assert normalize_equivalent_schema_shapes(
            dereference(runtime_error, components, release_schemas)
        ) == normalize_equivalent_schema_shapes(
            dereference(
                contract_schema(release, contract_error["$ref"]),
                components,
                release_schemas,
            )
        )


def test_runtime_consumption_enforces_contract_semantics_missing_from_json_schema() -> None:
    complete = {
        "availability": "complete",
        "source": "openrouter",
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
        "billed_usd": "0.001",
        "currency": "USD",
        "precision": "exact",
        "pricing_context": {
            "observed_at": datetime(2026, 9, 10, tzinfo=UTC),
            "price_version": "openrouter-2026-09-10",
        },
    }
    assert Consumption.model_validate(complete)
    invalid = (
        {**complete, "currency": None, "precision": None, "pricing_context": None},
        {**complete, "availability": "complete", "total_tokens": None},
        {
            **complete,
            "availability": "partial",
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "billed_usd": None,
            "currency": None,
            "precision": None,
            "pricing_context": None,
        },
        {
            **complete,
            "availability": "unavailable",
            "input_tokens": 1,
            "output_tokens": None,
            "total_tokens": None,
            "billed_usd": None,
            "currency": None,
            "precision": None,
            "pricing_context": None,
        },
        {**complete, "unexpected": True},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            Consumption.model_validate(payload)


def test_runtime_operation_declares_bearer_security_and_governed_scope() -> None:
    operation = runtime_openapi()["paths"]["/v1/responses"]["post"]

    assert operation["security"] == [{"bearerAuth": []}]
    assert operation["x-governed-scope"] == {
        "action": "invoke",
        "resource_type": "llm_model",
        "resource_id": "body.model",
    }


def test_runtime_openapi_examples_are_present_and_safe() -> None:
    document = runtime_openapi()
    operation = document["paths"]["/v1/responses"]["post"]
    components = document["components"]["schemas"]

    assert components["ResponsesRequest"]["examples"]
    assert components["ResponsesResponse"]["examples"]
    assert components["ErrorEnvelope"]["examples"]
    rendered = json.dumps(
        [
            components["ResponsesRequest"]["examples"],
            components["ResponsesResponse"]["examples"],
            components["ErrorEnvelope"]["examples"],
            *[
                response["content"]["application/json"]["example"]
                for status, response in operation["responses"].items()
                if status != "200"
            ],
        ]
    )
    assert all(secret not in rendered for secret in ("Authorization", "Bearer ", "sk-"))


class RecordingService:
    def __init__(self) -> None:
        self.raw: object | None = None

    async def create(self, raw: object, _authorization: str | None) -> JSONResponse:
        self.raw = raw
        status = 422 if raw is None else 200
        return JSONResponse({"accepted": raw is not None}, status_code=status)


@pytest.mark.asyncio
async def test_typed_body_keeps_invalid_requests_inside_the_responses_service() -> None:
    service = RecordingService()
    application = FastAPI()
    application.include_router(responses_router(service))  # type: ignore[arg-type]

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invalid = await client.post("/v1/responses", json={"model": "triage-agent"})
        assert invalid.status_code == 422
        assert service.raw is None

        valid = await client.post(
            "/v1/responses",
            json={"model": "triage-agent", "input": "Synthetic test input."},
        )
        assert valid.status_code == 200
        assert isinstance(service.raw, ResponsesRequest)
