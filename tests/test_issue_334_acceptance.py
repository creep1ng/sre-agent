"""End-to-end issue #334 acceptance (CA1-CA8) on the integrated consumption stack.

Each test names the criterion it proves and exercises the real FastAPI routes,
PostgreSQL persistence, the audited policy write, admission, a provider double
and settlement. No live provider or management credential is involved.
"""

import asyncio
import json
import os
import threading
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gateway.endpoint_catalog import EndpointCatalogSnapshot, EndpointMetadata
from sre_agent.gateway.providers import ProviderFailure, ProviderRequest, ProviderResult
from sre_agent.governance.dto import Consumption, PricingContext
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
AUDIT_KEY = "issue334-ca-audit-key"
ADMIN = "sre_admn_0123456789abcdefghijklmnop"
HARNESS = "sre_inci_0123456789abcdefghijklmnop"
RESTRICTED = "sre_rest_0123456789abcdefghijklmnop"
ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": HARNESS,
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
BODY = {"model": "triage-agent", "input": "sensitive incident prompt"}
PROMPT_TOKENS, COMPLETION_TOKENS, REQUEST_FEE = 10, 100, Decimal("0.2")
COMPLETION_PRICE = Decimal("0.1")
PRICING = PricingContext(
    observed_at=datetime(2026, 9, 10, 14, tzinfo=UTC),
    price_version="openrouter:2026-09-10T14:00:00Z",
)
FUTURE = datetime(2099, 1, 1, tzinfo=UTC)
counter = 0


def endpoint(**changes: object) -> EndpointMetadata:
    return replace(
        EndpointMetadata(
            model="openai/gpt-4o-mini",
            provider="OpenAI",
            max_prompt_tokens=PROMPT_TOKENS,
            max_completion_tokens=COMPLETION_TOKENS,
            valid_until=FUTURE,
            prompt_price=Decimal("0"),
            completion_price=COMPLETION_PRICE,
            request_price=REQUEST_FEE,
        ),
        **changes,  # type: ignore[arg-type]
    )


def snapshot(*endpoints: EndpointMetadata) -> EndpointCatalogSnapshot:
    return EndpointCatalogSnapshot(
        model="openai/gpt-4o-mini",
        endpoints=endpoints,
        observed_at=datetime.now(UTC),
        valid_until=FUTURE,
    )


class Catalog:
    def __init__(self, current: EndpointCatalogSnapshot) -> None:
        self._current = current

    async def fetch(self, _model: str) -> EndpointCatalogSnapshot:
        return self._current


def exact_usage(output_tokens: int) -> Consumption:
    return Consumption(
        availability="complete",
        source="openrouter",
        input_tokens=5,
        output_tokens=output_tokens,
        total_tokens=5 + output_tokens,
        billed_usd=f"0.{output_tokens}00",
        currency="USD",
        precision="exact",
        pricing_context=PRICING,
    )


def unknown_usage() -> Consumption:
    return Consumption(
        availability="unavailable",
        source="openrouter",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        billed_usd=None,
        currency=None,
        precision=None,
        pricing_context=None,
    )


class Provider:
    """Deterministic provider double; `block` keeps the first call in flight."""

    def __init__(
        self,
        consumption: Consumption | None = None,
        failure: str | None = None,
        block: threading.Event | None = None,
    ) -> None:
        self.consumption, self.failure, self.block = consumption, failure, block
        self.requests: list[ProviderRequest] = []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.block is not None:
            self.block.wait(timeout=10)
        if self.failure:
            raise ProviderFailure(self.failure, consumption=self.consumption)
        return ProviderResult(
            response_id="resp_12345678",
            model=request.model,
            text="sensitive provider output",
            provider=request.provider,
            consumption=self.consumption,
        )


@pytest.fixture(scope="module")
def ca_database() -> Database:
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


@pytest.fixture(autouse=True)
def clean_consumption_state() -> None:
    """Audit history is append-only, so only mutable admission state is reset."""
    reset = (
        "DELETE FROM consumption_reservations",
        "DELETE FROM idempotency_records",
        "UPDATE consumption_limit_policies SET version=0, incident_token_limit=NULL, "
        "monthly_usd_limit=NULL WHERE policy_id=1",
    )
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        for statement in reset:
            connection.execute(statement)
    yield
    # Resetting on the way out keeps an active limit from leaking into whichever
    # suite runs next against the same database.
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        for statement in reset:
            connection.execute(statement)


def seed_incident(incident_id: str) -> None:
    async def run() -> None:
        database = Database(DATABASE_URL)
        async with PostgresIncidentUnitOfWork(database) as unit:
            await unit.incidents.add(incident_id, {"state": "active"}, now=datetime.now(UTC))
        await database.dispose()

    asyncio.run(run())


def legacy_month_usd() -> Decimal:
    """Admitted-and-settled cost already recorded in the current admission month."""
    with psycopg.connect(DATABASE_URL) as connection:
        total = connection.execute(
            "SELECT COALESCE(SUM((consumption->>'billed_usd')::numeric), 0) FROM ("
            "SELECT DISTINCT ON (correlation->>'request_id') consumption FROM audit_events "
            "WHERE operation = 'responses.create' AND stage = 'response' "
            "AND outcome = 'success' AND (consumption->>'availability') = 'complete' "
            "AND occurred_at >= date_trunc('month', now()) AND occurred_at < "
            "date_trunc('month', now()) + interval '1 month') t"
        ).fetchone()[0]
    return Decimal(str(total))


def reservations() -> list[tuple]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT incident_id, token_exposure, usd_exposure, state, settled_tokens, "
            "settled_usd_cost, period_start FROM consumption_reservations ORDER BY created_at"
        ).fetchall()


def audited(request_id: str) -> str:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT reason_code FROM audit_events WHERE correlation ->> 'request_id' = %s",
            (request_id,),
        ).fetchone()[0]


DEFAULT_CATALOG = Catalog(snapshot(endpoint()))


class Gateway:
    def __init__(self, provider: Provider, catalog: Catalog | None = DEFAULT_CATALOG) -> None:
        global counter
        counter += 1
        self.key = f"issue334-ca-policy-write-{counter:04d}"
        settings = Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY)
        self.application = create_application(
            settings,
            llm_provider=provider,
            endpoint_catalog=catalog,
        )

    def put_policy(self, incident: int | None, monthly: str | None) -> dict:
        global counter
        counter += 1
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                "SELECT version FROM consumption_limit_policies WHERE policy_id = 1"
            ).fetchone()
        with TestClient(self.application) as client:
            response = client.put(
                "/v1/consumption-limits",
                headers={
                    "Authorization": f"Bearer {ADMIN}",
                    "Idempotency-Key": f"{self.key}-{counter:04d}",
                },
                json={
                    "expected_version": row[0] if row else 0,
                    "incident_token_limit": incident,
                    "monthly_usd_limit": monthly,
                },
            )
        assert response.status_code == 200, response.text
        return response.json()

    def respond(self, key: str = HARNESS, body: dict | None = None) -> object:
        with TestClient(self.application) as client:
            return client.post(
                "/v1/responses", headers={"Authorization": f"Bearer {key}"}, json=body or BODY
            )


def test_ca1_protected_versioned_write_governs_new_admissions_without_restart(
    ca_database: Database,
) -> None:
    provider = Provider(exact_usage(2))
    gateway = Gateway(provider)
    first_write = gateway.put_policy(None, None)
    assert first_write["version"] == 1
    assert first_write["incident_token_limit"] is None
    assert gateway.respond().status_code == 200
    written = gateway.put_policy(PROMPT_TOKENS + COMPLETION_TOKENS + 7, "1000.00")
    assert written["version"] == 2
    assert written["incident_token_limit"] == PROMPT_TOKENS + COMPLETION_TOKENS + 7
    seed_incident("ca1-hot")
    assert gateway.respond(body=BODY | {"incident_id": "ca1-hot"}).status_code == 200
    assert provider.requests[-1].max_output_tokens == COMPLETION_TOKENS
    assert gateway.respond(key=RESTRICTED).status_code == 403
    assert len(provider.requests) == 2


def test_ca2_incident_scope_is_shared_across_runs_and_gran_is_mandatory(
    ca_database: Database,
) -> None:
    seed_incident("ca2-shared")
    seed_incident("ca2-independent")
    block = threading.Event()
    provider = Provider(exact_usage(2), block=block)
    gateway = Gateway(provider)
    gateway.put_policy(PROMPT_TOKENS + COMPLETION_TOKENS, None)
    outcomes: list[int] = []

    def attempt(body: dict) -> None:
        outcomes.append(gateway.respond(body=body).status_code)

    inflight = threading.Thread(
        target=attempt, args=(BODY | {"incident_id": "ca2-shared", "run_id": "run-a"},)
    )
    inflight.start()
    while not reservations():
        pass
    attempt(BODY | {"incident_id": "ca2-shared", "task_id": "task-b"})
    attempt(BODY | {"incident_id": "ca2-independent", "run_id": "run-c"})
    block.set()
    inflight.join()
    assert sorted(outcomes) == [200, 200, 429]
    assert [row[0] for row in reservations()] == ["ca2-shared", "ca2-independent"]
    assert gateway.respond(key=RESTRICTED).status_code == 403


def test_ca3_monthly_budget_covers_calls_without_incident_and_keeps_period(
    ca_database: Database,
) -> None:
    provider = Provider(exact_usage(1))
    gateway = Gateway(provider)
    budget = legacy_month_usd() + REQUEST_FEE + COMPLETION_PRICE
    gateway.put_policy(None, f"{budget:.12f}")
    first = gateway.respond(body=BODY | {"run_id": "no-incident-run"})
    assert first.status_code == 200
    assert reservations()[0][0] is None
    assert reservations()[0][6] == datetime.now(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    second = gateway.respond(body=BODY | {"task_id": "no-incident-task"})
    assert second.status_code == 429
    assert audited(second.json()["request_id"]) == "monthly_limit_exceeded"


def test_ca4_concurrent_admissions_cannot_oversubscribe_one_incident(
    ca_database: Database,
) -> None:
    seed_incident("ca4-incident")
    block = threading.Event()
    provider = Provider(exact_usage(1), block=block)
    gateway = Gateway(provider)
    gateway.put_policy(PROMPT_TOKENS + COMPLETION_TOKENS, None)
    statuses: list[int] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        barrier.wait()
        statuses.append(gateway.respond(body=BODY | {"incident_id": "ca4-incident"}).status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    block.set()
    assert sorted(statuses) == [200, 429]
    assert len(provider.requests) == 1
    assert [row[0] for row in reservations()] == ["ca4-incident"]


def test_ca5_denial_precedes_provider_and_records_metadata_only(
    ca_database: Database,
) -> None:
    provider = Provider(exact_usage(1))
    gateway = Gateway(provider)
    gateway.put_policy(None, "0.000000000001")
    response = gateway.respond()
    assert response.status_code == 429 and provider.requests == []
    with psycopg.connect(DATABASE_URL) as connection:
        stored = json.dumps(
            connection.execute(
                "SELECT to_jsonb(audit_events) FROM audit_events "
                "WHERE correlation ->> 'request_id' = %s",
                (response.json()["request_id"],),
            ).fetchone()[0]
        )
    assert "sensitive incident prompt" not in stored
    assert "sensitive provider output" not in stored
    assert reservations() == []


def test_ca6_exact_settlement_is_exact_and_uncertain_usage_stays_reserved(
    ca_database: Database,
) -> None:
    provider = Provider(exact_usage(3))
    gateway = Gateway(provider)
    gateway.put_policy(100000, "100.00")
    assert gateway.respond().status_code == 200
    settled = reservations()[0]
    assert settled[3] == "settled" and settled[4] == 8
    assert settled[5] == Decimal("0.3000000000000000")
    assert gateway.respond().status_code == 200
    assert len(reservations()) == 2
    unknown = Gateway(Provider(unknown_usage(), failure="timeout"))
    unknown.put_policy(100000, "100.00")
    assert unknown.respond().status_code == 504
    retained = reservations()[-1]
    assert retained[3] == "reserved"
    assert retained[4] is None and retained[5] is None
    assert retained[6] == settled[6]


def test_ca7_active_limits_fail_closed_without_trustworthy_price_or_bounds(
    ca_database: Database,
) -> None:
    provider = Provider(exact_usage(1))
    gateway = Gateway(provider)
    gateway.put_policy(None, "10.00")
    unpriced = Gateway(provider, Catalog(snapshot(endpoint(request_price=None))))
    response = unpriced.respond()
    assert response.status_code == 429 and provider.requests == []
    assert audited(response.json()["request_id"]) == "consumption_bounds_unavailable"
    stale = Gateway(
        provider, Catalog(snapshot(endpoint(valid_until=datetime(2000, 1, 1, tzinfo=UTC))))
    )
    assert stale.respond().status_code == 429
    assert reservations() == []
    assert provider.requests == []


def test_ca8_equality_zero_unset_and_hot_policy_change(
    ca_database: Database,
) -> None:
    seed_incident("ca8-incident")
    provider = Provider(exact_usage(0))
    gateway = Gateway(provider)
    gateway.put_policy(PROMPT_TOKENS + COMPLETION_TOKENS, None)
    exact = gateway.respond(body=BODY | {"incident_id": "ca8-incident"})
    assert exact.status_code == 200
    assert provider.requests[-1].max_output_tokens == COMPLETION_TOKENS
    gateway.put_policy(0, None)
    zero = gateway.respond(body=BODY | {"incident_id": "ca8-incident"})
    assert zero.status_code == 429
    assert audited(zero.json()["request_id"]) == "incident_limit_exceeded"
    gateway.put_policy(None, None)
    unset = gateway.respond(body=BODY | {"incident_id": "ca8-incident"})
    assert unset.status_code == 200
    assert unset.json()["metadata"]["consumption"]["availability"] == "complete"


def test_ca9_active_limit_without_a_catalog_fails_closed_before_the_provider(
    ca_database: Database,
) -> None:
    """An active provider with no endpoint catalog must not skip admission."""
    provider = Provider(exact_usage(1))
    uncatalogued = Gateway(provider, None)
    uncatalogued.put_policy(None, "10.00")
    denied = uncatalogued.respond()
    assert denied.status_code == 429
    assert audited(denied.json()["request_id"]) == "consumption_bounds_unavailable"
    assert provider.requests == []
    assert reservations() == []
    # With no active limit there is nothing to bound, so a missing catalog must
    # not stand between the caller and the provider.
    uncatalogued.put_policy(None, None)
    allowed = uncatalogued.respond()
    assert allowed.status_code == 200
    assert len(provider.requests) == 1
    assert allowed.json()["metadata"]["consumption"]["availability"] == "complete"


def test_ca10_monthly_budget_counts_reservations_booked_to_any_incident(
    ca_database: Database,
) -> None:
    """One incident's reservation must reduce what another incident may spend."""
    seed_incident("ca10-first")
    seed_incident("ca10-second")
    # Absent consumption leaves the reservation outstanding, so the only thing
    # that can hold the second incident back is the monthly sum itself.
    provider = Provider(None, block=threading.Event())
    gateway = Gateway(provider)
    budget = legacy_month_usd() + REQUEST_FEE + COMPLETION_PRICE
    gateway.put_policy(None, f"{budget:.12f}")
    statuses: list[int] = []

    def attempt(incident_id: str) -> None:
        statuses.append(gateway.respond(body=BODY | {"incident_id": incident_id}).status_code)

    inflight = threading.Thread(target=attempt, args=("ca10-first",))
    inflight.start()
    while not reservations():
        pass
    denied = gateway.respond(body=BODY | {"incident_id": "ca10-second"})
    provider.block.set()
    inflight.join()
    assert denied.status_code == 429
    assert audited(denied.json()["request_id"]) == "monthly_limit_exceeded"
    assert statuses == [200]
    assert [row[0] for row in reservations()] == ["ca10-first"]
    assert provider.requests[0].max_output_tokens == 1


@pytest.mark.parametrize("with_incident", [False, True])
@pytest.mark.parametrize("settlement_fails", [False, True])
def test_ca6_monthly_usage_counts_each_request_once_with_legacy_history(
    ca_database: Database,
    monkeypatch: pytest.MonkeyPatch,
    with_incident: bool,
    settlement_fails: bool,
) -> None:
    """Legacy audit, settled usage and uncertain reservations share one allowance."""
    from sre_agent.gateway.consumption_admission import ConsumptionAdmissionService

    body = BODY
    if with_incident:
        incident = f"ca6-dedup-{int(settlement_fails)}"
        seed_incident(incident)
        body = BODY | {"incident_id": incident}
    # Write real audit-only history while limits are unset.
    usage = exact_usage(1).model_copy(update={"billed_usd": "0.300"})
    provider = Provider(usage)
    catalog = Catalog(snapshot(endpoint(max_completion_tokens=1)))
    gateway = Gateway(provider, catalog)
    before = legacy_month_usd()
    assert gateway.respond(body=body).status_code == 200
    assert reservations() == []
    assert legacy_month_usd() == before + Decimal("0.3")
    gateway.put_policy(None, f"{before + Decimal('0.9'):.12f}")

    if settlement_fails:

        async def fail_settlement(self, **kwargs):
            raise RuntimeError("controlled settlement failure")

        monkeypatch.setattr(ConsumptionAdmissionService, "settle", fail_settlement)

    first = gateway.respond(body=body)
    assert first.status_code == 200
    assert first.json()["metadata"]["consumption"]["availability"] == "complete"
    assert legacy_month_usd() == before + Decimal("0.6")
    row = reservations()[0]
    assert row[3] == ("reserved" if settlement_fails else "settled")
    assert row[2] == Decimal("0.3")
    assert row[5] == (None if settlement_fails else Decimal("0.3"))

    # A fresh service must see exactly 0.30 remaining, even with both sources.
    # Unknown consumption keeps this last 0.30 reserved across the workspace.
    unknown_provider = Provider(None)
    restarted = Gateway(unknown_provider, catalog)
    second = restarted.respond()
    assert second.status_code == 200
    assert reservations()[-1][3] == "reserved"
    denied = restarted.respond(body=body)
    assert denied.status_code == 429
    assert audited(denied.json()["request_id"]) == "monthly_limit_exceeded"
    assert len(provider.requests) == 2
    assert len(unknown_provider.requests) == 1
    print(
        json.dumps(
            {
                "with_incident": with_incident,
                "settlement_fails": settlement_fails,
                "complete_status": first.status_code,
                "remaining_request_status": second.status_code,
                "exhausted_status": denied.status_code,
                "reservation_states": [item[3] for item in reservations()],
                "settled_usd": str(row[5]),
                "outstanding_usd": str(reservations()[-1][2]),
            }
        )
    )


def test_ca6_settled_cost_counts_even_when_audit_write_fails(
    ca_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sre_agent.gateway.responses import PostgresAuditStore

    seed_incident("ca6-audit-failure")
    body = BODY | {"incident_id": "ca6-audit-failure"}
    provider = Provider(exact_usage(1).model_copy(update={"billed_usd": "0.300"}))
    gateway = Gateway(provider, Catalog(snapshot(endpoint(max_completion_tokens=1))))
    before = legacy_month_usd()
    gateway.put_policy(None, f"{before + Decimal('0.6'):.12f}")

    async def fail_audit(self, event):
        raise RuntimeError("controlled audit failure")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresAuditStore, "append", fail_audit)
        assert gateway.respond(body=body).status_code == 503
    assert reservations()[0][3:6:2] == ("settled", Decimal("0.3"))
    assert legacy_month_usd() == before
    assert gateway.respond(body=body).status_code == 200
    assert gateway.respond(body=body).status_code == 429
    assert len(provider.requests) == 2


def test_ca6_audit_fallback_counts_when_reservation_has_no_usd_exposure(
    ca_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sre_agent.gateway.consumption_admission import ConsumptionAdmissionService

    seed_incident("ca6-token-only")
    provider = Provider(exact_usage(1).model_copy(update={"billed_usd": "0.300"}))
    gateway = Gateway(provider, Catalog(snapshot(endpoint(max_completion_tokens=1))))
    before = legacy_month_usd()
    gateway.put_policy(100, None)

    async def fail_settlement(self, **kwargs):
        raise RuntimeError("controlled settlement failure")

    with monkeypatch.context() as patch:
        patch.setattr(ConsumptionAdmissionService, "settle", fail_settlement)
        assert gateway.respond(body=BODY | {"incident_id": "ca6-token-only"}).status_code == 200
    assert reservations()[0][2:4] == (None, "reserved")
    assert legacy_month_usd() == before + Decimal("0.3")
    gateway.put_policy(None, f"{before + Decimal('0.5'):.12f}")
    denied = gateway.respond()
    assert denied.status_code == 429
    assert audited(denied.json()["request_id"]) == "monthly_limit_exceeded"
    assert len(provider.requests) == 1
