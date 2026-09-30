"""Admission, output-cap, settlement and concurrency contracts for issue #334."""

import asyncio
import os
import threading
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sre_agent.gateway.consumption_admission import ConsumptionAdmissionService
from sre_agent.gateway.endpoint_catalog import EndpointCatalogSnapshot, EndpointMetadata
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
PERIOD = datetime(2026, 9, 1, tzinfo=UTC)


def priced(**changes: object) -> EndpointMetadata:
    return replace(
        EndpointMetadata(
            model="openai/gpt-4o-mini",
            provider="OpenAI",
            max_prompt_tokens=10,
            max_completion_tokens=100,
            valid_until=datetime(2027, 6, 1, tzinfo=UTC),
            prompt_price=Decimal("0"),
            completion_price=Decimal("0.1"),
            request_price=Decimal("0.2"),
        ),
        **changes,  # type: ignore[arg-type]
    )


def snapshot(*endpoints: EndpointMetadata) -> EndpointCatalogSnapshot:
    return EndpointCatalogSnapshot(
        model="openai/gpt-4o-mini",
        endpoints=endpoints,
        observed_at=NOW,
        valid_until=datetime(2027, 6, 1, tzinfo=UTC),
    )


class StaticCatalog:
    def __init__(self, current: EndpointCatalogSnapshot) -> None:
        self._current = current

    async def fetch(self, _model: str) -> EndpointCatalogSnapshot:
        return self._current


@pytest.fixture(scope="module")
def admission_database() -> Database:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, audit_events, grants, credentials, "
            "resources, mcp_tools, mcp_servers, principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    database = Database(DATABASE_URL)
    yield database
    asyncio.run(database.dispose())


async def seed_policy(database: Database, *, incident: int | None, monthly: str | None) -> None:
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


async def seed_incident(database: Database, incident_id: str) -> None:
    async with PostgresIncidentUnitOfWork(database) as unit:
        await unit.incidents.add(incident_id, {"state": "active"}, now=NOW)


async def reservation_count(database: Database) -> int:
    async with database.transaction() as session:
        rows = (await session.execute(text("SELECT count(*) FROM consumption_reservations"))).all()
        return int(rows[0][0])


def admit(database: Database, catalog: object | None = None, **kwargs: object) -> object:
    async def run() -> object:
        return await ConsumptionAdmissionService(database.sessions).admit(
            catalog=catalog or StaticCatalog(snapshot(priced())),
            now=NOW,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )

    return asyncio.run(run())


@pytest.fixture(autouse=True)
def _clean_state(admission_database: Database) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DELETE FROM consumption_reservations")
        connection.execute("DELETE FROM audit_events")
        connection.execute("DELETE FROM consumption_limit_policies")
    yield


def test_allow_at_exact_equality_reserves_cap(admission_database: Database) -> None:
    asyncio.run(seed_policy(admission_database, incident=12, monthly="1.00"))
    asyncio.run(seed_incident(admission_database, "incident-eq"))
    result = admit(admission_database, incident_id="incident-eq", model="m", provider="OpenAI")
    assert result.allowed and result.max_output_tokens == 2
    assert result.policy_version == 0 and result.reservation_id is not None


@pytest.mark.parametrize(
    ("incident", "monthly", "incident_id", "prices", "reason", "retryable"),
    [
        (None, "0.10", None, {}, "monthly_limit_exceeded", False),
        (0, None, "incident-zero", {}, "incident_limit_exceeded", False),
        (None, "1.00", None, {"request_price": None}, "consumption_bounds_unavailable", False),
        ("deleted", None, None, {}, "policy_unavailable", True),
    ],
)
def test_deny_cases_create_no_reservation(
    admission_database: Database,
    incident: object,
    monthly: str | None,
    incident_id: str | None,
    prices: dict,
    reason: str,
    retryable: bool,
) -> None:
    if incident == "deleted":
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("DELETE FROM consumption_limit_policies")
    else:
        asyncio.run(seed_policy(admission_database, incident=incident, monthly=monthly))
    if incident_id is not None:
        asyncio.run(seed_incident(admission_database, incident_id))
    before = asyncio.run(reservation_count(admission_database))
    result = admit(
        admission_database,
        StaticCatalog(snapshot(priced(**prices))),
        incident_id=incident_id,
        model="m",
        provider="OpenAI",
    )
    assert not result.allowed and result.denial_reason == reason
    assert result.retryable == retryable
    assert asyncio.run(reservation_count(admission_database)) == before


def test_unset_limits_allow_without_reservation(admission_database: Database) -> None:
    asyncio.run(seed_policy(admission_database, incident=None, monthly=None))
    before = asyncio.run(reservation_count(admission_database))
    result = admit(admission_database, incident_id=None, model="m", provider="OpenAI")
    assert result.allowed and result.reservation_id is None
    assert asyncio.run(reservation_count(admission_database)) == before


def test_concurrent_admissions_serialize(admission_database: Database) -> None:
    asyncio.run(seed_policy(admission_database, incident=11, monthly=None))
    asyncio.run(seed_incident(admission_database, "incident-race"))
    barrier, outcomes = threading.Barrier(2), []

    def attempt() -> None:
        barrier.wait()
        outcomes.append(
            admit(
                admission_database,
                incident_id="incident-race",
                model="m",
                provider="OpenAI",
            ).allowed
        )

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == [False, True]


def test_exact_settlement_is_idempotent(admission_database: Database) -> None:
    asyncio.run(seed_policy(admission_database, incident=100, monthly="10.00"))
    result = admit(admission_database, incident_id=None, model="m", provider="OpenAI")

    async def settle() -> object:
        return await ConsumptionAdmissionService(admission_database.sessions).settle(
            reservation_id=result.reservation_id, tokens=15, usd_cost=Decimal("0.35")
        )

    first, second = asyncio.run(settle()), asyncio.run(settle())
    assert (first.settled_tokens, second.settled_tokens) == (15, 15)
    assert (first.state, second.state) == ("settled", "settled")


def test_uncertain_outcome_retains_reservation(admission_database: Database) -> None:
    asyncio.run(seed_policy(admission_database, incident=100, monthly="10.00"))
    result = admit(admission_database, incident_id=None, model="m", provider="OpenAI")

    async def read() -> object:
        async with admission_database.transaction() as session:
            return await session.get(
                __import__(
                    "sre_agent.persistence.models",
                    fromlist=["ConsumptionReservationRow"],
                ).ConsumptionReservationRow,
                result.reservation_id,
            )

    row = asyncio.run(read())
    assert row.state == "reserved" and row.period_start == PERIOD


def test_legacy_audit_usage_counts_toward_monthly(admission_database: Database) -> None:
    asyncio.run(seed_policy(admission_database, incident=None, monthly="1.00"))
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO audit_events (event_id, occurred_at, operation, action, stage, "
            "outcome, response_status, retryable, latency_ms, correlation, consumption, "
            "redaction, content_state, authoritative_acceptance, ordinary_result, "
            "exporter_result) VALUES ('legacyusage000000000000000000000001', %s, "
            "'responses.create', 'invoke', 'response', 'success', 200, false, 1, "
            '\'{"request_id": "legacy-request-1"}\', '
            '\'{"availability": "complete", "source": "openrouter", "input_tokens": 5, '
            '"output_tokens": 5, "total_tokens": 10, "billed_usd": "0.90", '
            '"currency": "USD", "precision": "exact", "pricing_context": null}\', '
            "'{}', 'redacted', 'accepted', 'released', 'not_attempted')",
            (datetime(2026, 9, 5, tzinfo=UTC),),
        )
    result = admit(admission_database, incident_id=None, model="m", provider="OpenAI")
    assert not result.allowed and result.denial_reason == "monthly_limit_exceeded"
