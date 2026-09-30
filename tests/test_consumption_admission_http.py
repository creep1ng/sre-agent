"""Gateway enforcement: deny before provider, cap propagation, settlement."""

import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sre_agent.application import create_application
from sre_agent.gateway.endpoint_catalog import EndpointCatalogSnapshot, EndpointMetadata
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.governance.dto import Consumption, PricingContext
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings


class StaticCatalog:
    """Live-clock catalog double: the gateway stamps its own admission time."""

    def __init__(self, current: EndpointCatalogSnapshot) -> None:
        self._current = current

    async def fetch(self, _model: str) -> EndpointCatalogSnapshot:
        return self._current


def live_snapshot() -> EndpointCatalogSnapshot:
    now = datetime.now(UTC)
    return EndpointCatalogSnapshot(
        model="openai/gpt-4o-mini",
        endpoints=(
            EndpointMetadata(
                model="openai/gpt-4o-mini",
                provider="OpenAI",
                max_prompt_tokens=10,
                max_completion_tokens=100,
                valid_until=now.replace(year=now.year + 1),
                prompt_price=Decimal("0"),
                completion_price=Decimal("0.1"),
                request_price=Decimal("0.2"),
            ),
        ),
        observed_at=now,
        valid_until=now.replace(year=now.year + 1),
    )


DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
KEYS = {"incident-harness": "sre_inci_0123456789abcdefghijklmnop"}
ENV = {
    "ADMIN_HUMAN_API_KEY": "sre_admn_0123456789abcdefghijklmnop",
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": KEYS["incident-harness"],
    "RESTRICTED_HARNESS_API_KEY": "sre_rest_0123456789abcdefghijklmnop",
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
BODY = {"model": "triage-agent", "input": "sensitive incident prompt"}
AUDIT_KEY = "admission-audit-key-must-not-persist"


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list = []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        return ProviderResult(
            response_id="resp_12345678",
            model=request.model,
            text="sensitive provider output",
            provider=request.provider,
            consumption=Consumption(
                availability="complete",
                source="openrouter",
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
                billed_usd="0.0012300",
                currency="USD",
                precision="exact",
                pricing_context=PricingContext(
                    observed_at=datetime(2026, 9, 10, 14, tzinfo=UTC),
                    price_version="openrouter:2026-09-10T14:00:00Z",
                ),
            ),
        )


@pytest.fixture(scope="module")
def gateway_database() -> Database:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, bok_section_chunks, "
            "bok_documents, bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, resources, "
            "mcp_tools, mcp_servers, principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def load() -> Database:
        database = Database(DATABASE_URL)
        await seed(database, SeedSettings.from_environment(ENV))
        return database

    database = asyncio.run(load())
    yield database
    asyncio.run(database.dispose())


def seed_policy(database: Database, incident: int | None, monthly: str | None) -> None:
    async def run() -> None:
        async with database.transaction() as session:
            await session.execute(
                text(
                    "INSERT INTO consumption_limit_policies "
                    "(policy_id, version, incident_token_limit, monthly_usd_limit, updated_at) "
                    "VALUES (1, 0, :incident, :monthly, :now) "
                    "ON CONFLICT (policy_id) DO UPDATE SET incident_token_limit=:incident, "
                    "monthly_usd_limit=:monthly"
                ),
                {"incident": incident, "monthly": monthly, "now": NOW},
            )

    asyncio.run(run())
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DELETE FROM consumption_reservations")


def post(database: Database, provider: RecordingProvider, key: str) -> object:
    settings = Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY)
    application = create_application(
        settings,
        llm_provider=provider,
        endpoint_catalog=StaticCatalog(live_snapshot()),
    )
    return application, {"Authorization": f"Bearer {key}"}


def test_deny_precedes_provider_and_audits_metadata_only(
    gateway_database: Database,
) -> None:
    from fastapi.testclient import TestClient

    seed_policy(gateway_database, incident=None, monthly="0.10")
    provider = RecordingProvider()
    application, headers = post(gateway_database, provider, KEYS["incident-harness"])
    with TestClient(application) as client:
        response = client.post("/v1/responses", headers=headers, json=BODY)
    assert response.status_code == 429
    assert provider.requests == []
    body = response.json()
    assert body["request_id"]
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT reason_code, to_jsonb(audit_events) FROM audit_events "
            "WHERE correlation ->> 'request_id' = %s",
            (body["request_id"],),
        ).fetchone()
    assert row[0] == "monthly_limit_exceeded"
    assert "sensitive incident prompt" not in json.dumps(row[1])
    assert "sensitive provider output" not in json.dumps(row[1])


def test_allow_propagates_cap_and_settles_exact(
    gateway_database: Database,
) -> None:
    from fastapi.testclient import TestClient

    seed_policy(gateway_database, incident=100000, monthly="10.00")
    provider = RecordingProvider()
    application, headers = post(gateway_database, provider, KEYS["incident-harness"])
    with TestClient(application) as client:
        response = client.post("/v1/responses", headers=headers, json=BODY)
    assert response.status_code == 200
    assert 0 < provider.requests[0].max_output_tokens <= 100
    with psycopg.connect(DATABASE_URL) as connection:
        settled = connection.execute(
            "SELECT state, settled_tokens FROM consumption_reservations "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert settled == ("settled", 18)
