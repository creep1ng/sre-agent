import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from sre_agent.gateway.responses import ResponsesRequest, responses_router

RELEASES = Path("schemas/releases")


def latest_responses_contract() -> tuple[Path, dict[str, Any]]:
    versions = sorted(
        (path for path in RELEASES.iterdir() if (path / "openapi/responses.yaml").exists()),
        key=lambda path: tuple(int(part) for part in path.name.split(".")),
    )
    release = versions[-1]
    return release, yaml.safe_load((release / "openapi/responses.yaml").read_text())


def runtime_openapi(service: object | None = None) -> dict[str, Any]:
    application = FastAPI()
    application.include_router(responses_router(service))  # type: ignore[arg-type]
    return application.openapi()


def dereference(schema: Any, components: dict[str, Any]) -> Any:
    if isinstance(schema, list):
        return [dereference(item, components) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/components/schemas/")
        resolved = dereference(components[name], components)
        siblings = {
            key: dereference(value, components)
            for key, value in schema.items()
            if key not in {"$ref", "description"}
        }
        return resolved | siblings
    normalized = {
        key: dereference(value, components)
        for key, value in schema.items()
        if key not in {"$id", "$schema", "title", "description", "examples", "default"}
    }
    if "const" in normalized:
        normalized.pop("type", None)
    return normalized


def contract_schema(release: Path, reference: str) -> dict[str, Any]:
    name = reference.removeprefix("urn:sre-agent:schema:").rsplit(":", 1)[0]
    return json.loads((release / f"json-schema/http/{name}.schema.json").read_text())


def test_runtime_operation_documents_the_complete_responses_contract() -> None:
    release, contract = latest_responses_contract()
    runtime = runtime_openapi()
    operation = runtime["paths"]["/v1/responses"]["post"]
    canonical = contract["paths"]["/v1/responses"]["post"]
    components = runtime["components"]["schemas"]

    assert operation["operationId"] == canonical["operationId"]
    assert operation["summary"] == canonical["summary"]
    assert operation["requestBody"]["required"] is True
    assert set(operation["responses"]) == {"200", "401", "403", "422", "502", "503", "504"}

    runtime_request = operation["requestBody"]["content"]["application/json"]["schema"]
    contract_request = canonical["requestBody"]["content"]["application/json"]["schema"]
    assert dereference(runtime_request, components) == dereference(
        contract_schema(release, contract_request["$ref"]), components
    )

    runtime_success = operation["responses"]["200"]["content"]["application/json"]["schema"]
    contract_success = canonical["responses"]["200"]["content"]["application/json"]["schema"]
    assert dereference(runtime_success, components) == dereference(
        contract_schema(release, contract_success["$ref"]), components
    )

    for status in {"401", "403", "422", "502", "503", "504"}:
        runtime_error = operation["responses"][status]["content"]["application/json"]["schema"]
        canonical_response = contract["components"]["responses"][
            canonical["responses"][status]["$ref"].rsplit("/", 1)[-1]
        ]
        contract_error = canonical_response["content"]["application/json"]["schema"]
        assert dereference(runtime_error, components) == dereference(
            contract_schema(release, contract_error["$ref"]), components
        )


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
