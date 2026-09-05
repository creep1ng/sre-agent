import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sre_agent.persistence.database import Database

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "20260822_01")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO audit_events (
              event_id, occurred_at, operation, action, stage, outcome, reason_code,
              response_status, retryable, correlation, redaction, content_state,
              authoritative_acceptance, ordinary_result, exporter_result)
            VALUES ('00000000-0000-4000-8000-000000000000', now(), 'audit.accept',
              'persist', 'audit', 'success', NULL, 200, false, '{}', '{}', 'absent',
              'accepted', 'released', 'not_attempted')"""
        )
        connection.commit()
    command.upgrade(config, "head")
    command.upgrade(config, "head")


def test_repeated_head_has_exactly_six_domain_tables() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
    assert {row[0] for row in rows} == {
        "alembic_version",
        "audit_events",
        "credentials",
        "grants",
        "idempotency_records",
        "principals",
        "resources",
    }


def test_latency_migration_backfills_without_a_server_default() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT latency_ms FROM audit_events WHERE event_id=%s",
            ("00000000-0000-4000-8000-000000000000",),
        ).fetchone() == (0,)
        metadata = connection.execute(
            """SELECT is_nullable, column_default FROM information_schema.columns
            WHERE table_schema='public' AND table_name='audit_events'
              AND column_name='latency_ms'"""
        ).fetchone()
        assert metadata == ("NO", None)
        constraints = {
            row[0]
            for row in connection.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid='audit_events'::regclass"
            )
        }
        assert "ck_audit_events_latency" in constraints
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                """INSERT INTO audit_events (
                  event_id, occurred_at, operation, action, stage, outcome, reason_code,
                  response_status, retryable, latency_ms, correlation, redaction, content_state,
                  authoritative_acceptance, ordinary_result, exporter_result)
                VALUES ('00000000-0000-4000-8000-000000000099', now(), 'audit.accept',
                  'persist', 'audit', 'success', NULL, 200, false, -1, '{}', '{}', 'absent',
                  'accepted', 'released', 'not_attempted')"""
            )


def test_authorization_denial_cause_is_nullable_but_constrained() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        metadata = connection.execute(
            """SELECT is_nullable, column_default FROM information_schema.columns
            WHERE table_schema='public' AND table_name='audit_events'
              AND column_name='authorization_denial_cause'"""
        ).fetchone()
        assert metadata == ("YES", None)
        assert connection.execute(
            "SELECT authorization_denial_cause FROM audit_events WHERE event_id=%s",
            ("00000000-0000-4000-8000-000000000000",),
        ).fetchone() == (None,)
        constraints = {
            row[0]
            for row in connection.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid='audit_events'::regclass"
            )
        }
        assert "ck_audit_events_authorization_denial_cause" in constraints
        connection.execute(
            """INSERT INTO audit_events (
              event_id, occurred_at, operation, action, stage, outcome, reason_code,
              response_status, retryable, latency_ms, correlation, redaction, content_state,
              authoritative_acceptance, ordinary_result, exporter_result,
              authorization_denial_cause)
            VALUES ('00000000-0000-4000-8000-000000000087', now(), 'responses.create',
              'invoke', 'authorization', 'denied', 'no_matching_grant', 403, false, 1,
              '{}', '{}', 'absent', 'accepted', 'released', 'not_attempted',
              'grant_not_applicable')"""
        )
        assert connection.execute(
            "SELECT authorization_denial_cause FROM audit_events WHERE event_id=%s",
            ("00000000-0000-4000-8000-000000000087",),
        ).fetchone() == ("grant_not_applicable",)
        connection.rollback()
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                """INSERT INTO audit_events (
                  event_id, occurred_at, operation, action, stage, outcome, reason_code,
                  response_status, retryable, latency_ms, correlation, redaction, content_state,
                  authoritative_acceptance, ordinary_result, exporter_result,
                  authorization_denial_cause)
                VALUES ('00000000-0000-4000-8000-000000000088', now(), 'responses.create',
                  'invoke', 'routing', 'denied', 'no_matching_grant', 403, false, 1,
                  '{}', '{}', 'absent', 'accepted', 'released', 'not_attempted',
                  'resource_missing')"""
            )


@pytest.mark.asyncio
async def test_async_transaction_boundary() -> None:
    database = Database(DATABASE_URL)
    async with database.transaction() as session:
        assert await session.scalar(text("SELECT 1")) == 1
    await database.dispose()


def test_schema_exposes_required_constraints_and_rejects_invalid_rows() -> None:
    required = {
        "ck_principals_kind",
        "ck_credentials_lifecycle",
        "ck_resources_llm_assignment",
        "uq_grants_direct",
        "ck_grants_effect",
    }
    with psycopg.connect(DATABASE_URL) as connection:
        names = connection.execute("SELECT conname FROM pg_constraint").fetchall()
        assert required <= {row[0] for row in names}
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO resources VALUES "
                "('skill','triage-agent','active','alias-id',NULL,NULL,NULL,NULL)"
            )


def test_database_trigger_rejects_audit_updates_and_deletes() -> None:
    insert = """INSERT INTO audit_events (
      event_id, occurred_at, operation, action, stage, outcome, reason_code, response_status,
      retryable, latency_ms, correlation, redaction, content_state, authoritative_acceptance,
      ordinary_result, exporter_result)
    VALUES ('00000000-0000-4000-8000-000000000001', now(), 'audit.accept', 'persist',
      'audit', 'success', NULL, 200, false, 4, '{}', '{}', 'absent', 'accepted',
      'released', 'not_attempted')"""
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(insert)
        connection.commit()
        for statement in ("UPDATE audit_events SET retryable=true", "DELETE FROM audit_events"):
            with pytest.raises(psycopg.errors.RaiseException), connection.transaction():
                connection.execute(statement)
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 2
