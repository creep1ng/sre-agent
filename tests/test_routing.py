"""Isolated PostgreSQL acceptance tests for configured logical-model routing."""

import os

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gateway.openrouter import OpenRouterProvider
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import (
    SeedConflict,
    SeedSettings,
    routing_digest,
    routing_drift,
    seed,
)
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="routing tests require an explicitly isolated TEST_DATABASE_URL",
)
INCIDENT_KEY = "sre_inci_0123456789abcdefghijklmnop"
ENV = {
    "ADMIN_HUMAN_API_KEY": "sre_admn_0123456789abcdefghijklmnop",
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": INCIDENT_KEY,
    "RESTRICTED_HARNESS_API_KEY": "sre_rest_0123456789abcdefghijklmnop",
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}


@pytest.fixture(scope="module", autouse=True)
def fresh_database() -> None:
    assert DATABASE_URL is not None
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


@pytest.mark.asyncio
async def test_fresh_seed_persists_two_configured_aliases() -> None:
    assert DATABASE_URL is not None
    settings = SeedSettings.from_environment(ENV)
    database = Database(DATABASE_URL)
    assert await seed(database, settings) is True
    assert await routing_drift(database, settings.routing) == {}
    await database.dispose()

    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT resource_id, concrete_model, router, inference_provider "
            "FROM resources WHERE resource_type='llm_model' ORDER BY resource_id"
        ).fetchall()
    assert rows == [
        ("remediation-agent", "anthropic/claude-3.5-haiku", "openrouter", "anthropic"),
        ("triage-agent", "openai/gpt-4o-mini", "openrouter", "openai"),
    ]


@pytest.mark.asyncio
async def test_drift_is_safe_to_diagnose_and_requires_explicit_reconciliation() -> None:
    assert DATABASE_URL is not None
    settings = SeedSettings.from_environment(ENV)
    database = Database(DATABASE_URL)
    await seed(database, settings)
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE resources SET concrete_model='stale/model', "
            "inference_provider='stale-provider' WHERE resource_id='triage-agent'"
        )

    assert await routing_drift(database, settings.routing) == {
        "triage-agent": ("concrete_model", "inference_provider")
    }
    checked_digest = await routing_digest(database, settings.routing)
    with pytest.raises(SeedConflict, match=r"seed_state_conflict: resources\.concrete_model"):
        await seed(database, settings)
    with pytest.raises(SeedConflict, match="routing_snapshot_changed"):
        await seed(
            database,
            settings,
            reconcile_routing=True,
            expected_routing_digest="0" * 64,
        )
    assert (
        await seed(
            database,
            settings,
            reconcile_routing=True,
            expected_routing_digest=checked_digest,
        )
        is False
    )
    assert await routing_drift(database, settings.routing) == {}
    await database.dispose()


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult(
            response_id="resp_controlled123",
            model=request.model,
            text="controlled output",
            provider=request.provider,
        )


def test_public_responses_contract_routes_both_aliases_without_fallback() -> None:
    assert DATABASE_URL is not None
    database = Database(DATABASE_URL)
    import asyncio

    asyncio.run(seed(database, SeedSettings.from_environment(ENV)))
    asyncio.run(database.dispose())
    provider = RecordingProvider()
    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key="routing-test-audit-key"),
        llm_provider=provider,
    )
    with TestClient(app) as client:
        responses = [
            client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {INCIDENT_KEY}"},
                json={"model": alias, "input": "Controlled test input."},
            )
            for alias in ("triage-agent", "remediation-agent")
        ]

    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()["metadata"]["requested_model_alias"] for response in responses] == [
        "triage-agent",
        "remediation-agent",
    ]
    assert [(request.model, request.provider) for request in provider.requests] == [
        ("openai/gpt-4o-mini", "openai"),
        ("anthropic/claude-3.5-haiku", "anthropic"),
    ]


def test_incompatible_provider_is_normalized_without_upstream_body_persistence() -> None:
    assert DATABASE_URL is not None
    database = Database(DATABASE_URL)
    import asyncio

    asyncio.run(seed(database, SeedSettings.from_environment(ENV)))
    asyncio.run(database.dispose())

    def incompatible(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "secret upstream body"}})

    provider_client = httpx.AsyncClient(
        base_url="https://controlled.invalid",
        transport=httpx.MockTransport(incompatible),
    )
    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key="routing-test-audit-key"),
        llm_provider=OpenRouterProvider(provider_client, api_key="provider-secret"),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {INCIDENT_KEY}"},
            json={"model": "triage-agent", "input": "Controlled test input."},
        )
    asyncio.run(provider_client.aclose())

    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "upstream_invalid_response",
        "message": "Provider response was invalid.",
    }
    with psycopg.connect(DATABASE_URL) as connection:
        audit = connection.execute(
            "SELECT stage, reason_code, routing::text, row_to_json(audit_events)::text "
            "FROM audit_events ORDER BY occurred_at DESC LIMIT 1"
        ).fetchone()
    assert audit[:2] == ("upstream", "upstream_invalid")
    assert "secret upstream body" not in audit[3]
    assert "provider-secret" not in audit[3]
