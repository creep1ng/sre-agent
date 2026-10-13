"""Shared E2E fixtures and evidence builders for issue #454 acceptance tests."""

import asyncio
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.providers import ProviderFailure, ProviderRequest, ProviderResult
from sre_agent.gateway.responses import PostgresAuditStore
from sre_agent.governance.dto import (
    Consumption,
    ModelAlias,
    PolicyDecision,
    PricingContext,
    Principal,
    PrincipalContext,
)
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
AUDIT_KEY = "issue454-attribution-audit-key"
ADMIN = "sre_admn_0123456789abcdefghijklmnop"
CONSUMER = "sre_inci_0123456789abcdefghijklmnop"
RESTRICTED = "sre_rest_0123456789abcdefghijklmnop"
ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": CONSUMER,
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
PROMPT = "private attribution acceptance prompt"
OUTPUT = "private attribution acceptance output"
CONSUMPTION = Consumption(
    availability="complete",
    source="openrouter",
    input_tokens=5,
    output_tokens=7,
    total_tokens=12,
    billed_usd="0.0012300",
    currency="USD",
    precision="exact",
    pricing_context=PricingContext(
        observed_at=datetime(2026, 9, 10, 14, tzinfo=UTC),
        price_version="openrouter:2026-09-10T14:00:00Z",
    ),
)


class ControlledProvider:
    def __init__(
        self,
        failure: str | None = None,
        gate: threading.Event | None = None,
        entered: threading.Event | None = None,
    ) -> None:
        self.requests: list[ProviderRequest] = []
        self.failure = failure
        self.gate, self.entered = gate, entered

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.entered is not None:
            self.entered.set()
        if self.gate is not None:
            await asyncio.to_thread(self.gate.wait, 10)
        if self.failure:
            raise ProviderFailure(self.failure)
        return ProviderResult(
            response_id=f"resp_issue454_{len(self.requests):08d}",
            model=request.model,
            text=OUTPUT,
            provider=request.provider,
            consumption=CONSUMPTION,
        )


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS request_attributions, consumption_limit_policies, "
            "bok_section_chunks, "
            "bok_documents, bok_collection_versions, audit_events, skill_versions, grants, "
            "credentials, resources, alert_triage, mcp_tools, mcp_servers, principals, "
            "idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            await seed(database, SeedSettings.from_environment(ENV))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())


@pytest.fixture(autouse=True)
def clean_history():
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        has_snapshot_table = connection.execute(
            "SELECT to_regclass('public.request_attributions') IS NOT NULL"
        ).fetchone()[0]
        if has_snapshot_table:
            connection.execute("TRUNCATE TABLE audit_events, request_attributions CASCADE")
        else:
            connection.execute("TRUNCATE TABLE audit_events")
    yield


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def read_item(client: TestClient, request_id: str) -> dict[str, object]:
    response = client.get(
        "/v1/usage/requests", params={"request_id": request_id}, headers=auth(ADMIN)
    )
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"filter", "items"}
    assert response.json()["filter"] == {"request_id": request_id}
    assert len(response.json()["items"]) == 1
    return response.json()["items"][0]


def historical_response_event(request_id: UUID, occurred_at: datetime):
    """Build a closed valid response audit event as legacy persisted history."""
    principal = Principal(
        principal_id="issue454-harness",
        kind="agent",
        display_name="Issue 454 acceptance harness",
        status="active",
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    return (
        AuditProjector(AUDIT_KEY.encode())
        .event(
            request_id=request_id,
            status=200,
            latency_ms=1,
            stage="response",
            context=PrincipalContext(
                principal=principal,
                credential_id="issue454-credential",
                authenticated_at=occurred_at,
            ),
            alias="triage-agent",
            decision=PolicyDecision(
                decision="allow", reason_code="grant_matched", policy_id="issue454-grant"
            ),
            assignment=ModelAlias(
                model_alias_id="issue454-triage-alias",
                alias="triage-agent",
                concrete_model="openai/gpt-4o-mini",
                router="openrouter",
                inference_provider="openai",
                status="active",
            ),
            consumption=CONSUMPTION,
        )
        .model_copy(update={"occurred_at": occurred_at})
    )


def persist_audit_events(events: list[object]) -> None:
    async def persist() -> None:
        database = Database(DATABASE_URL)
        try:
            store = PostgresAuditStore(database.sessions)
            for audit_event in events:
                await store.append(audit_event)
        finally:
            await database.dispose()

    asyncio.run(persist())


def expected_assignment(assignment: dict) -> dict:
    return {
        "availability": "available",
        "alias": assignment["alias"],
        "model": assignment["concrete_model"],
        "provider": assignment["inference_provider"],
        "router": assignment["router"],
    }


def record_artifact(name: str, observed: dict) -> None:
    """Persist only explicitly selected safe observations after successful E2E assertions."""
    text = (
        json.dumps(
            {"scenario": name, "evidence_kind": "controlled integration", "observed": observed},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    for sensitive in (PROMPT, OUTPUT, ADMIN, AUDIT_KEY, "test-only-openrouter-credential"):
        assert sensitive not in text, "sensitive evidence refused"
    Path(f"/tmp/issue454-e2e-{name}.json").write_text(text, encoding="utf-8")
