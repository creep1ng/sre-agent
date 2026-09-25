"""Issue #23 C2a storage: alert_triage persistence with CAS and invariants."""

import os
from datetime import UTC, datetime

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sre_agent.persistence.database import Database
from sre_agent.triage.store import TriageRepository

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 23, tzinfo=UTC)


@pytest.fixture(scope="module", autouse=True)
def triage_store_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
        for (table,) in tables:
            connection.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


async def _write(**kwargs):
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            return await TriageRepository(session).write(**kwargs)
    finally:
        await database.dispose()


def _base(**overrides):
    fields = {
        "alert_id": "al-store-1",
        "expected_version": None,
        "status": "open",
        "incident_id": None,
        "reason": None,
        "severity": None,
        "actor": "op-human",
        "decided_at": NOW,
    }
    fields.update(overrides)
    return fields


@pytest.mark.asyncio
async def test_create_read_and_cas() -> None:
    created = await _write(**_base())
    assert created is not None and created["expected_version"] == 1
    assert await _write(**_base()) is None
    updated = await _write(
        **_base(expected_version=1, status="dismissed", reason="No action needed.")
    )
    assert updated is not None and updated["expected_version"] == 2
    assert updated["status"] == "dismissed"
    assert await _write(**_base(expected_version=1, status="open")) is None


@pytest.mark.asyncio
async def test_check_invariants_reject_bad_rows() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            for status, incident_id, severity in (
                ("bogus", None, None),
                ("declared", "inc-x", None),
                ("linked", None, None),
            ):
                with pytest.raises(IntegrityError):
                    async with session.begin_nested():
                        await session.execute(
                            text(
                                "INSERT INTO alert_triage (alert_id, status, incident_id,"
                                " expected_version, reason, severity, actor, decided_at)"
                                " VALUES ('al-ck', :status, :incident_id, 1, NULL,"
                                " :severity, 'op-human', now())"
                            ),
                            {"status": status, "incident_id": incident_id, "severity": severity},
                        )
    finally:
        await database.dispose()
