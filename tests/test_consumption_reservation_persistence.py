"""PostgreSQL contracts for durable, metadata-only token reservations."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.models import ConsumptionReservationRow
from sre_agent.persistence.reservations import ConsumptionReservationRepository

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
PERIOD = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def reservation_database() -> Database:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS request_attributions, consumption_limit_policies, "
            "bok_section_chunks, "
            "bok_documents, bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, resources, alert_triage, "
            "mcp_tools, mcp_servers, principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    database = Database(DATABASE_URL)
    yield database
    asyncio.run(database.dispose())


async def _seed_incident(database: Database, incident_id: str) -> None:
    async with PostgresIncidentUnitOfWork(database) as unit:
        await unit.incidents.add(incident_id, {"state": "active"}, now=NOW)


async def _create_reservation(
    database: Database,
    reservation_id: str,
    *,
    incident_id: str | None,
    period_start: datetime = PERIOD,
) -> None:
    async with database.transaction() as session:
        await ConsumptionReservationRepository(session).create(
            reservation_id,
            incident_id=incident_id,
            period_start=period_start,
            policy_version=4,
            model="openai/gpt-4o-mini",
            provider="OpenAI",
            token_exposure=128,
            usd_exposure=Decimal("0.0000000000000000007"),
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_reservation_is_durable_metadata_before_provider_completion(
    reservation_database: Database,
) -> None:
    await _create_reservation(reservation_database, "reservation-before-provider", incident_id=None)
    async with reservation_database.transaction() as session:
        row = await session.get(ConsumptionReservationRow, "reservation-before-provider")
        record = await ConsumptionReservationRepository(session).get("reservation-before-provider")
    assert row is not None and record is not None
    assert record.state == "reserved"
    assert record.token_exposure == 128
    assert record.usd_exposure == Decimal("0.0000000000000000007")
    assert record.policy_version == 4
    assert "raw_prompt" not in ConsumptionReservationRow.__table__.columns
    assert "completion" not in ConsumptionReservationRow.__table__.columns
    assert "sensitive prompt marker" not in repr(record)


@pytest.mark.asyncio
async def test_incident_scope_and_utc_period_round_trip_without_collapsing_null_scope(
    reservation_database: Database,
) -> None:
    await _seed_incident(reservation_database, "incident-reservation-scope")
    offset_period = datetime.fromisoformat("2026-08-31T19:00:00-05:00")
    await _create_reservation(
        reservation_database,
        "reservation-with-incident",
        incident_id="incident-reservation-scope",
        period_start=offset_period,
    )
    await _create_reservation(
        reservation_database, "reservation-without-incident", incident_id=None
    )
    async with reservation_database.transaction() as session:
        repository = ConsumptionReservationRepository(session)
        scoped = await repository.get("reservation-with-incident")
        unscoped = await repository.get("reservation-without-incident")
    assert scoped is not None and scoped.incident_id == "incident-reservation-scope"
    assert scoped.period_start == PERIOD
    assert unscoped is not None and unscoped.incident_id is None
    assert unscoped.period_start == PERIOD


@pytest.mark.asyncio
async def test_period_is_database_immutable_and_downgrade_preserves_live_rows(
    reservation_database: Database,
) -> None:
    await _create_reservation(
        reservation_database, "reservation-immutable-period", incident_id=None
    )
    with (
        pytest.raises(psycopg.errors.RaiseException),
        psycopg.connect(DATABASE_URL, autocommit=True) as connection,
    ):
        connection.execute(
            "UPDATE consumption_reservations SET period_start=%s WHERE reservation_id=%s",
            (PERIOD + timedelta(days=1), "reservation-immutable-period"),
        )

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    with pytest.raises(RuntimeError, match="cannot downgrade while reservations exist"):
        command.downgrade(config, "20260929_16")
    async with reservation_database.transaction() as session:
        record = await ConsumptionReservationRepository(session).get("reservation-immutable-period")
    assert record is not None and record.period_start == PERIOD
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20261009_01",
        )
        assert connection.execute("SELECT count(*) FROM consumption_reservations").fetchone() == (
            4,
        )
