"""Contract-first HTTP acceptance scenarios for issue #333.

Failure modes the usage read must prevent:
- a related audit event counts the same effective request twice;
- a UTC month includes the next month's first instant or omits its last;
- incident aggregation crosses incident boundaries or counts one run twice;
- absent/unavailable consumption is reported as zero or complete coverage;
- distinct price versions are merged, or decimal USD is rounded;
- authorization failure reveals counts or touches persisted usage;
- missing, malformed, or unbounded filters silently broaden the query;
- a persistence outage is returned as a successful empty result;
- a valid empty scope omits evidence coverage or implies zero billed cost;
- the read emits new consumption or returns prompts, outputs, or credentials.

The fixtures project audit-domain events and persist them through
PostgresAuditStore to test PostgreSQL; they do not exercise the HTTP provider flow.
No provider body, prompt, or credential is used as usage source data.
"""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from sre_agent.application import create_application
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.providers import ProviderRequest, ProviderResult
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
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
READ_ONLY_KEY = "sre_rest_0123456789abcdefghijklmnop"
AUDIT_KEY = "issue333-usage-audit-key"
ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": "sre_demo_0123456789abcdefghijklmnop",
    "INCIDENT_HARNESS_API_KEY": "sre_inci_0123456789abcdefghijklmnop",
    "RESTRICTED_HARNESS_API_KEY": READ_ONLY_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "mcp_tools, mcp_servers, principals, idempotency_records, alembic_version CASCADE"
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
def isolated_audit_events():
    """Prevent persisted rows from one test affecting another test's aggregates."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("TRUNCATE TABLE audit_events")
    yield


@pytest.fixture
def client() -> TestClient:
    application = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client


def auth(key: str = ADMIN_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class ControlledAcceptanceProvider:
    """Deterministic provider stub for exercising the real responses HTTP route."""

    async def create(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult(
            response_id="resp_issue333_controlled",
            model=request.model,
            text="controlled acceptance response",
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


def test_producer_persists_protected_incident_and_run_attribution() -> None:
    request_id = str(uuid4())
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
    )
    with psycopg.connect(DATABASE_URL) as connection:
        correlation = connection.execute(
            "SELECT correlation FROM audit_events WHERE correlation ->> 'request_id' = %s",
            (request_id,),
        ).fetchone()[0]

    projector = AuditProjector(AUDIT_KEY.encode())
    assert correlation["incident_ref"] == projector.reference(
        "incident_id", "incident-a"
    ).model_dump(mode="json")
    assert correlation["run_ref"] == projector.reference("run_id", "run-a").model_dump(mode="json")
    assert "incident-a" not in repr(correlation) and "run-a" not in repr(correlation)


def append_event(
    *,
    request_id: str,
    at: datetime,
    incident_id: str,
    run_id: str,
    availability: str | None = "complete",
    amount: str | None = "0.0012300",
    price_version: str = "openrouter:2026-09-10T14:00:00Z",
    status: int = 200,
    stage: str = "response",
) -> None:
    consumption = None
    if availability is not None:
        consumption = Consumption(
            availability=availability,
            source="openrouter",
            input_tokens=(
                11 if availability == "complete" else (5 if availability == "partial" else None)
            ),
            output_tokens=7 if availability == "complete" else None,
            total_tokens=18 if availability == "complete" else None,
            billed_usd=amount if availability == "complete" else None,
            currency="USD" if availability == "complete" else None,
            precision="exact" if availability == "complete" else None,
            pricing_context=(
                PricingContext(
                    observed_at=at,
                    price_version=price_version,
                )
                if availability == "complete"
                else None
            ),
        )
    principal = Principal(
        principal_id="usage-harness",
        kind="agent",
        display_name="Usage acceptance harness",
        status="active",
        created_at=at,
        updated_at=at,
    )
    event = (
        AuditProjector(AUDIT_KEY.encode())
        .event(
            request_id=UUID(request_id),
            status=status,
            latency_ms=12,
            stage=stage,
            context=PrincipalContext(
                principal=principal,
                credential_id="credential-usage-harness",
                authenticated_at=at,
            ),
            alias="triage-agent",
            decision=(
                PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None)
                if status == 403
                else PolicyDecision(
                    decision="allow", reason_code="grant_matched", policy_id="usage-harness-grant"
                )
            ),
            assignment=ModelAlias(
                model_alias_id="usage-triage-alias",
                alias="triage-agent",
                concrete_model="openai/gpt-4o-mini",
                router="openrouter",
                inference_provider="openai",
                status="active",
            ),
            identifiers={"incident_id": incident_id, "run_id": run_id},
            consumption=consumption,
        )
        .model_copy(update={"occurred_at": at})
    )

    async def persist() -> None:
        database = Database(DATABASE_URL)
        try:
            await PostgresAuditStore(database.sessions).append(event)
        finally:
            await database.dispose()

    asyncio.run(persist())


async def project_usage(**filters):
    """Read through the persisted projection without introducing an HTTP route."""
    from sre_agent.gateway.usage import UsageReadProjection

    database = Database(DATABASE_URL)
    try:
        projection = UsageReadProjection(database.sessions, AUDIT_KEY.encode())
        return await projection.read(**filters)
    finally:
        await database.dispose()


def test_persisted_projection_deduplicates_consistent_events_and_marks_conflicts_unknown() -> None:
    request_id = str(uuid4())
    instant = datetime(2026, 9, 12, tzinfo=UTC)
    append_event(
        request_id=request_id,
        at=instant,
        incident_id="incident-a",
        run_id="run-a",
        amount="0.0012300",
    )
    append_event(
        request_id=request_id,
        at=instant,
        incident_id="incident-a",
        run_id="run-a",
        amount="0.0012300",
    )

    consistent = asyncio.run(project_usage(request_id=UUID(request_id)))
    assert consistent["request_count"] == 1
    assert consistent["totals"]["cost"]["amount"] == "0.0012300"

    append_event(
        request_id=request_id,
        at=instant,
        incident_id="incident-a",
        run_id="run-a",
        amount="0.0090000",
    )
    conflicted = asyncio.run(project_usage(request_id=UUID(request_id)))
    assert conflicted["request_count"] == 1
    assert conflicted["coverage"]["unknown"] == 1
    assert conflicted["totals"]["input_tokens"] is None
    assert conflicted["totals"]["cost"]["amount"] is None


def test_persisted_projection_incident_includes_all_distinct_runs_without_other_incidents() -> None:
    for request_id, run_id, incident_id in (
        (str(uuid4()), "run-a", "incident-a"),
        (str(uuid4()), "run-b", "incident-a"),
        (str(uuid4()), "run-a", "incident-b"),
    ):
        append_event(
            request_id=request_id,
            at=datetime(2026, 9, 12, tzinfo=UTC),
            incident_id=incident_id,
            run_id=run_id,
        )
    duplicate_id = str(uuid4())
    append_event(
        request_id=duplicate_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-b",
    )
    append_event(
        request_id=duplicate_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-b",
    )

    result = asyncio.run(project_usage(incident_id="incident-a"))
    assert result["request_count"] == 3
    assert result["incident_runs"] == 2
    assert result["totals"]["total_tokens"] == 54


def test_persisted_projection_uses_utc_half_open_months_and_preserves_price_versions() -> None:
    for request_id, at, amount, price_version in (
        (
            str(uuid4()),
            datetime(2026, 9, 30, 23, 59, 59, 999999, tzinfo=UTC),
            "0.0012300",
            "openrouter:2026-09-10T14:00:00Z",
        ),
        (
            str(uuid4()),
            datetime(2026, 10, 1, 0, 0, tzinfo=UTC),
            "0.0040000",
            "openrouter:2026-09-11T14:00:00Z",
        ),
    ):
        append_event(
            request_id=request_id,
            at=at,
            incident_id="incident-a",
            run_id=request_id,
            amount=amount,
            price_version=price_version,
        )

    result = asyncio.run(project_usage(month="2026-09"))
    assert result["request_count"] == 1
    assert result["months"] == [{"month": "2026-09", "request_count": 1}]
    assert result["totals"]["cost"] == {
        "amount": "0.0012300",
        "currency": "USD",
        "nature": "billed",
        "precision": "exact",
        "price_versions": ["openrouter:2026-09-10T14:00:00Z"],
    }


def test_persisted_projection_never_makes_partial_or_unknown_rows_look_complete() -> None:
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-known",
    )
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 13, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-partial",
        availability="partial",
        amount=None,
    )
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 14, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-unknown",
        availability="unavailable",
        amount=None,
        status=504,
        stage="upstream",
    )

    result = asyncio.run(project_usage(month="2026-09"))
    assert result["coverage"] == {
        "status": "partial",
        "known": 1,
        "incomplete": 1,
        "unknown": 1,
    }
    assert result["totals"]["total_tokens"] is None
    assert result["totals"]["cost"]["amount"] is None


def test_persisted_projection_refuses_to_silently_truncate_large_scopes(monkeypatch) -> None:
    from sre_agent.gateway.usage import UsageReadLimitExceeded, UsageReadProjection

    for _ in range(2):
        append_event(
            request_id=str(uuid4()),
            at=datetime(2026, 9, 12, tzinfo=UTC),
            incident_id="incident-a",
            run_id=str(uuid4()),
        )
    monkeypatch.setattr(UsageReadProjection, "MAX_ROWS", 1)
    with pytest.raises(UsageReadLimitExceeded):
        asyncio.run(project_usage(month="2026-09"))


def test_persisted_projection_does_not_combine_historical_price_versions() -> None:
    for amount, version in (
        ("0.0012300", "openrouter:2026-09-10T14:00:00Z"),
        ("0.0040000", "openrouter:2026-09-11T14:00:00Z"),
    ):
        append_event(
            request_id=str(uuid4()),
            at=datetime(2026, 9, 12, tzinfo=UTC),
            incident_id="incident-a",
            run_id=str(uuid4()),
            amount=amount,
            price_version=version,
        )

    result = asyncio.run(project_usage(month="2026-09"))
    assert result["totals"]["cost"]["amount"] is None
    assert result["totals"]["cost"]["price_versions"] == [
        "openrouter:2026-09-10T14:00:00Z",
        "openrouter:2026-09-11T14:00:00Z",
    ]


def test_request_read_counts_related_evidence_once_and_preserves_exact_usd(client) -> None:
    request_id = str(uuid4())
    instant = datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)
    append_event(
        request_id=request_id,
        at=instant,
        incident_id="incident-a",
        run_id="run-a",
    )
    append_event(
        request_id=request_id,
        at=instant,
        incident_id="incident-a",
        run_id="run-a",
    )

    response = client.get(
        "/v1/usage/consumption", params={"request_id": request_id}, headers=auth()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_count"] == 1
    assert body["totals"]["total_tokens"] == 18
    assert body["totals"]["cost"] == {
        "amount": "0.0012300",
        "currency": "USD",
        "nature": "billed",
        "precision": "exact",
        "price_versions": ["openrouter:2026-09-10T14:00:00Z"],
    }
    assert body["coverage"] == {"status": "complete", "known": 1, "incomplete": 0, "unknown": 0}
    assert body["months"] == [{"month": "2026-09", "request_count": 1}]


def test_month_read_uses_half_open_utc_month_boundary_and_excludes_other_month(client) -> None:
    first = str(uuid4())
    next_month = str(uuid4())
    append_event(
        request_id=first,
        at=datetime(2026, 9, 30, 23, 59, 59, 999999, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-september",
    )
    append_event(
        request_id=next_month,
        at=datetime(2026, 10, 1, 0, 0, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-october",
    )

    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_count"] == 1
    assert body["months"] == [{"month": "2026-09", "request_count": 1}]


def test_related_rows_across_month_boundary_use_earliest_request_month(client) -> None:
    request_id = str(uuid4())
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
    )
    append_event(
        request_id=request_id,
        at=datetime(2026, 10, 1, 0, 0, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
    )

    september = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())
    october = client.get("/v1/usage/consumption", params={"month": "2026-10"}, headers=auth())

    assert september.status_code == 200, september.text
    assert september.json()["request_count"] == 1
    assert september.json()["months"] == [{"month": "2026-09", "request_count": 1}]
    assert october.status_code == 200, october.text
    assert october.json()["request_count"] == 0
    assert october.json()["months"] == []


def test_cost_sum_preserves_digits_beyond_decimal_default_precision(client) -> None:
    for amount in ("1234567890123456789012345678", "0.1"):
        append_event(
            request_id=str(uuid4()),
            at=datetime(2026, 9, 12, tzinfo=UTC),
            incident_id="incident-a",
            run_id=str(uuid4()),
            amount=amount,
        )

    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    assert response.status_code == 200, response.text
    assert response.json()["totals"]["cost"]["amount"] == "1234567890123456789012345678.1"


def test_incident_read_deduplicates_runs_and_excludes_other_incidents(client) -> None:
    request_id = str(uuid4())
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
    )
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
    )
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-b",
    )
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-b",
        run_id="run-c",
    )

    response = client.get(
        "/v1/usage/consumption", params={"incident_id": "incident-a"}, headers=auth()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_count"] == 2
    assert body["incident_runs"] == 2
    assert body["totals"]["total_tokens"] == 36


@pytest.mark.parametrize("availability", ["absent", "unavailable"])
def test_uncertain_consumption_is_not_reported_as_zero_or_complete(
    client, availability: str
) -> None:
    request_id = str(uuid4())
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
        availability=availability,
        amount=None,
    )

    response = client.get(
        "/v1/usage/consumption", params={"request_id": request_id}, headers=auth()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_count"] == 1
    assert body["coverage"]["status"] in {"partial", "unknown"}
    assert body["coverage"]["known"] == 0
    assert body["totals"]["total_tokens"] is None
    assert body["totals"]["cost"]["amount"] is None


@pytest.mark.parametrize(
    ("status", "stage", "availability"),
    [
        (403, "authorization", None),
        (502, "upstream", "unavailable"),
        (504, "upstream", "unavailable"),
    ],
)
def test_denial_error_and_timeout_keep_their_persisted_uncertainty(
    client, status: int, stage: str, availability: str | None
) -> None:
    request_id = str(uuid4())
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
        availability=availability,
        amount=None,
        status=status,
        stage=stage,
    )

    response = client.get(
        "/v1/usage/consumption", params={"request_id": request_id}, headers=auth()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totals"]["total_tokens"] is None
    assert body["totals"]["cost"]["amount"] is None
    assert body["coverage"]["status"] in {"partial", "unknown"}


def test_mixed_price_versions_do_not_produce_a_combined_cost(client) -> None:
    request_id = str(uuid4())
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
        price_version="openrouter:2026-09-10T14:00:00Z",
    )
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 13, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-b",
        amount="0.0040000",
        price_version="openrouter:2026-09-11T14:00:00Z",
    )

    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totals"]["cost"]["amount"] is None
    assert body["totals"]["cost"]["price_versions"] == [
        "openrouter:2026-09-10T14:00:00Z",
        "openrouter:2026-09-11T14:00:00Z",
    ]


def test_partial_evidence_cannot_make_a_known_subtotal_look_complete(client) -> None:
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
    )
    append_event(
        request_id=str(uuid4()),
        at=datetime(2026, 9, 13, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-b",
        availability="partial",
        amount=None,
    )

    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["coverage"] == {"status": "partial", "known": 1, "incomplete": 1, "unknown": 0}
    assert body["totals"]["input_tokens"] is None
    assert body["totals"]["total_tokens"] is None
    assert body["totals"]["cost"]["amount"] is None


def test_non_admin_cannot_observe_usage_or_counts_before_storage(client, monkeypatch) -> None:
    from sre_agent.gateway.usage import UsageReadProjection

    def forbidden(*args, **kwargs):
        pytest.fail("usage storage must not be read before admin authorization")

    monkeypatch.setattr(UsageReadProjection, "read", forbidden)
    response = client.get(
        "/v1/usage/consumption", params={"month": "2026-09"}, headers=auth(READ_ONLY_KEY)
    )

    assert response.status_code == 403
    assert "request_count" not in response.text
    assert "total_tokens" not in response.text


def test_unauthenticated_cannot_observe_usage_or_touch_projection(client, monkeypatch) -> None:
    from sre_agent.gateway.usage import UsageReadProjection

    def forbidden(*args, **kwargs):
        pytest.fail("usage projection must not be called before authentication")

    monkeypatch.setattr(UsageReadProjection, "read", forbidden)
    response = client.get("/v1/usage/consumption", params={"month": "2026-09"})

    assert response.status_code == 401
    assert "request_count" not in response.text


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"month": "2026-13"},
        {"month": "2026-09", "incident_id": "incident-a"},
        {"from": "2026-01-01T00:00:00Z", "to": "2027-01-01T00:00:00Z"},
        {"request_id": "not-a-request-id"},
    ],
)
def test_missing_invalid_or_unbounded_filter_is_rejected(client, params: dict[str, str]) -> None:
    response = client.get("/v1/usage/consumption", params=params, headers=auth())

    assert response.status_code == 422


def test_storage_failure_is_not_an_empty_success(client, monkeypatch) -> None:
    from sre_agent.gateway.usage import UsageReadProjection

    async def unavailable(*args, **kwargs):
        raise RuntimeError("simulated usage persistence outage")

    monkeypatch.setattr(UsageReadProjection, "read", unavailable)

    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"


def test_valid_empty_month_has_explicit_empty_coverage(client) -> None:
    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_count"] == 0
    assert body["incident_runs"] == 0
    assert body["months"] == []
    assert body["coverage"] == {"status": "complete", "known": 0, "incomplete": 0, "unknown": 0}
    assert body["totals"]["input_tokens"] is None
    assert body["totals"]["total_tokens"] is None
    assert body["totals"]["cost"]["amount"] is None


def test_scope_over_explicit_result_limit_fails_instead_of_truncating(client, monkeypatch) -> None:
    from sre_agent.gateway.usage import UsageReadProjection

    monkeypatch.setattr(UsageReadProjection, "MAX_ROWS", 1)
    for _ in range(2):
        append_event(
            request_id=str(uuid4()),
            at=datetime(2026, 9, 12, tzinfo=UTC),
            incident_id="incident-a",
            run_id=str(uuid4()),
        )

    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    assert response.status_code == 413
    assert "request_count" not in response.text


def test_administrative_read_does_not_create_consumption_events(client) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        before = connection.execute(
            "SELECT count(*) FROM audit_events WHERE operation='responses.create'"
        ).fetchone()[0]

    response = client.get("/v1/usage/consumption", params={"month": "2026-09"}, headers=auth())

    with psycopg.connect(DATABASE_URL) as connection:
        after = connection.execute(
            "SELECT count(*) FROM audit_events WHERE operation='responses.create'"
        ).fetchone()[0]
    assert response.status_code == 200, response.text
    assert after == before
    body = response.json()
    assert set(body) == {"filter", "request_count", "incident_runs", "months", "totals", "coverage"}
    assert not {"prompt", "output", "api_key", "credential"} & set(body)
    assert all(
        forbidden not in response.text.lower()
        for forbidden in ("prompt", "provider_body", "api_key", "credential")
    )


def test_generated_http_contract_describes_validated_selectors_and_response(client) -> None:
    request_id = str(uuid4())
    append_event(
        request_id=request_id,
        at=datetime(2026, 9, 12, tzinfo=UTC),
        incident_id="incident-a",
        run_id="run-a",
    )
    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    openapi = openapi_response.json()
    operation = openapi["paths"]["/v1/usage/consumption"]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}

    def schema_variants(schema: dict[str, object]) -> list[dict[str, object]]:
        variants = [schema]
        for key in ("anyOf", "oneOf", "allOf"):
            for nested in schema.get(key, []):
                variants.extend(schema_variants(nested))
        return variants

    assert set(parameters) == {"request_id", "incident_id", "month"}
    assert parameters["request_id"]["in"] == "query"
    assert any(
        variant.get("format") == "uuid"
        for variant in schema_variants(parameters["request_id"]["schema"])
    )
    incident_constraints = schema_variants(parameters["incident_id"]["schema"])
    assert any(variant.get("minLength") == 1 for variant in incident_constraints)
    assert any(variant.get("maxLength") == 128 for variant in incident_constraints)
    assert any(
        variant.get("pattern") == r"^\d{4}-(0[1-9]|1[0-2])$"
        for variant in schema_variants(parameters["month"]["schema"])
    )

    success_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in success_schema or success_schema.get("properties")

    def resolve_schema(schema: object) -> object:
        if isinstance(schema, dict):
            reference = schema.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
                component_name = reference.rsplit("/", maxsplit=1)[1]
                return resolve_schema(openapi["components"]["schemas"][component_name])
            return {name: resolve_schema(value) for name, value in schema.items()}
        if isinstance(schema, list):
            return [resolve_schema(value) for value in schema]
        return schema

    response = client.get(
        "/v1/usage/consumption", params={"request_id": request_id}, headers=auth()
    )
    assert response.status_code == 200, response.text
    Draft202012Validator(
        resolve_schema(success_schema),
        format_checker=FormatChecker(),
    ).validate(response.json())


def test_duplicate_and_unknown_query_parameters_remain_rejected(client) -> None:
    request_id = str(uuid4())
    duplicate = client.get(
        "/v1/usage/consumption",
        params=[("request_id", request_id), ("request_id", request_id)],
        headers=auth(),
    )
    unknown = client.get(
        "/v1/usage/consumption", params={"month": "2026-09", "unexpected": "value"}, headers=auth()
    )

    assert duplicate.status_code == 422
    assert unknown.status_code == 422


def test_response_producer_persists_usage_visible_to_administrative_read() -> None:
    application = create_application(
        Settings(DATABASE_URL, AUDIT_KEY, audit_hmac_key=AUDIT_KEY),
        llm_provider=ControlledAcceptanceProvider(),
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        produced = client.post(
            "/v1/responses",
            headers=auth("sre_inci_0123456789abcdefghijklmnop"),
            json={
                "model": "triage-agent",
                "input": "controlled integration fixture",
                "incident_id": "issue333-produced-incident",
                "run_id": "issue333-produced-run",
            },
        )
        assert produced.status_code == 200, produced.text
        request_id = produced.json()["request_id"]

        usage = client.get(
            "/v1/usage/consumption",
            params={"request_id": request_id},
            headers=auth(),
        )

    assert usage.status_code == 200, usage.text
    assert usage.json()["request_count"] == 1
    assert usage.json()["incident_runs"] == 1
    assert usage.json()["totals"]["total_tokens"] == 18
    assert usage.json()["totals"]["cost"]["amount"] == "0.0012300"
