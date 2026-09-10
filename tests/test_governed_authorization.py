"""Architecture and runtime evidence for the four current governed operations."""

import asyncio
import os
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import PrincipalRepository
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
AUDIT_KEY = "issue202-unit3-audit-key"
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
UNKNOWN_KEY = "sre_unknown_0123456789abcdefghijklmnop"
INCIDENT_KEY = "sre_inci_0123456789abcdefghijklmnop"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": INCIDENT_KEY,
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}


@pytest.fixture(scope="module", autouse=True)
def governed_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            assert await seed(database, SeedSettings.from_environment(SEED_ENV))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult(
            response_id="resp_unit3abc",
            model=request.model,
            text="controlled output",
            provider=request.provider,
        )


def _application(provider: RecordingProvider | None = None) -> Any:
    return create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY),
        llm_provider=provider or RecordingProvider(),
    )


def _governed_operations(document: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in document["paths"].items()
        if path.startswith("/v1/")
        for method, operation in item.items()
        if method in {"get", "post", "put", "delete"} and "x-governed-scope" in operation
    }


EXPECTED_SCOPES = {
    ("POST", "/v1/responses"): {
        "action": "invoke",
        "resource_type": "llm_model",
        "resource_id": "body.model",
    },
    ("POST", "/v1/principals"): {
        "action": "admin.write",
        "resource_type": "administrative_control",
        "resource_id": "principals",
    },
    ("GET", "/v1/principals"): {
        "action": "admin.read",
        "resource_type": "administrative_control",
        "resource_id": "principals",
    },
    ("GET", "/v1/principals/{principal_id}"): {
        "action": "admin.read",
        "resource_type": "administrative_control",
        "resource_id": "principals",
    },
}


def test_current_governed_operations_have_one_declared_contract() -> None:
    document = _application().openapi()

    assert _governed_operations(document) == set(EXPECTED_SCOPES)
    for (method, path), expected_scope in EXPECTED_SCOPES.items():
        operation = document["paths"][path][method.lower()]
        schemes = operation["security"]
        assert len(schemes) == 1 and len(schemes[0]) == 1
        scheme = document["components"]["securitySchemes"][next(iter(schemes[0]))]
        assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
        assert operation["x-governed-scope"] == expected_scope
        assert {"401", "403"} <= set(operation["responses"])


def _record_principal_effects(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"create": 0, "list": 0, "get": 0}
    original_create = PrincipalRepository.create
    original_list = PrincipalRepository.list
    original_get = PrincipalRepository.get

    async def create(repository: PrincipalRepository, *args: Any, **kwargs: Any) -> Any:
        calls["create"] += 1
        return await original_create(repository, *args, **kwargs)

    async def list_(repository: PrincipalRepository, *args: Any, **kwargs: Any) -> Any:
        calls["list"] += 1
        return await original_list(repository, *args, **kwargs)

    async def get(repository: PrincipalRepository, *args: Any, **kwargs: Any) -> Any:
        calls["get"] += 1
        return await original_get(repository, *args, **kwargs)

    monkeypatch.setattr(PrincipalRepository, "create", create)
    monkeypatch.setattr(PrincipalRepository, "list", list_)
    monkeypatch.setattr(PrincipalRepository, "get", get)
    return calls


def _requests(client: TestClient, key: str) -> list[Any]:
    headers = {"Authorization": f"Bearer {key}"}
    return [
        client.post(
            "/v1/responses",
            headers=headers,
            json={"model": "triage-agent", "input": "Controlled test input."},
        ),
        client.post(
            "/v1/principals",
            headers={**headers, "Idempotency-Key": "unit3-create-key"},
            json={
                "principal_id": "unit3-principal",
                "kind": "human",
                "display_name": "Unit 3 principal",
            },
        ),
        client.get("/v1/principals", headers=headers),
        client.get("/v1/principals/incident-harness", headers=headers),
    ]


@pytest.mark.parametrize(
    ("key", "expected_status"),
    [(RESTRICTED_KEY, 403), (UNKNOWN_KEY, 401)],
)
def test_real_routes_stop_denied_credentials_before_business_effects(
    key: str, expected_status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_principal_effects(monkeypatch)
    provider = RecordingProvider()
    with TestClient(_application(provider), raise_server_exceptions=False) as client:
        responses = _requests(client, key)

    assert [response.status_code for response in responses] == [expected_status] * 4
    assert all(
        response.json()["error"]["code"]
        == {401: "authentication_failed", 403: "resource_unavailable"}[expected_status]
        for response in responses
    )
    assert calls == {"create": 0, "list": 0, "get": 0}
    assert provider.requests == []


def _assert_no_business_effect(response: Any, effects: list[str]) -> None:
    assert response.status_code == 403
    assert effects == []


def test_declared_secure_route_probe_detects_direct_adapter_bypass() -> None:
    effects: list[str] = []
    app = FastAPI()
    bearer = HTTPBearer(auto_error=False)

    @app.get(
        "/v1/synthetic",
        dependencies=[Security(bearer)],
        openapi_extra={
            "x-governed-scope": {
                "action": "test.read",
                "resource_type": "synthetic",
                "resource_id": "synthetic",
            }
        },
    )
    async def synthetic() -> JSONResponse:
        effects.append("adapter")
        return JSONResponse({"ok": True})

    with TestClient(app) as client:
        with pytest.raises(AssertionError):
            _assert_no_business_effect(
                client.get("/v1/synthetic", headers={"Authorization": "Bearer invalid"}),
                effects,
            )

    assert effects == ["adapter"]


def test_future_consumer_guidance_is_documentation_only() -> None:
    guidance = Path("docs/architecture.md").read_text()

    assert "Future LLM, MCP, skill, and knowledge consumers" in guidance
    assert "authorize_governed_access" in guidance
    assert "MCP, skill, and knowledge runtimes remain future-only" in guidance
    assert "adds no endpoint, grant model, provisioning path" in " ".join(guidance.split())
    assert not {
        path
        for path in _application().openapi()["paths"]
        if any(term in path.lower() for term in ("mcp", "skill", "knowledge"))
    }
