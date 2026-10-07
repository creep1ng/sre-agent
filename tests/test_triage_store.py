"""Issue #23 C2a storage: alert_triage persistence with CAS and invariants."""

import os
from datetime import UTC, datetime

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

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
async def test_decision_origin_and_responsible_system_persist() -> None:
    legacy_default = await _write(**_base(alert_id="al-origin-default"))
    assert legacy_default is not None
    assert (legacy_default["decision_origin"], legacy_default["responsible_system"]) == (
        "unknown",
        None,
    )

    manual = await _write(**_base(alert_id="al-origin-manual", decision_origin="manual"))
    external = await _write(
        **_base(
            alert_id="al-origin-external",
            decision_origin="external_automatic",
            responsible_system="producer-payments",
        )
    )
    assert manual is not None and (manual["decision_origin"], manual["responsible_system"]) == (
        "manual",
        None,
    )
    assert external is not None and (
        external["decision_origin"],
        external["responsible_system"],
    ) == ("external_automatic", "producer-payments")


def test_storage_rejects_invalid_provenance_pairs() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        invalid = (
            ("not-an-origin", None),
            ("external_automatic", None),
            ("external_automatic", " \t\n "),
            ("manual", "producer-payments"),
            ("unknown", "producer-payments"),
        )
        for index, (origin, system) in enumerate(invalid):
            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO alert_triage (alert_id, status, incident_id,"
                        " expected_version, reason, severity, actor, decided_at,"
                        " decision_origin, responsible_system)"
                        " VALUES (%s, 'open', NULL, 1, NULL, NULL, 'producer-agent', now(),"
                        " %s, %s)",
                        (f"al-origin-invalid-{index}", origin, system),
                    )


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


@pytest.mark.asyncio
async def test_missing_alert_has_no_row_and_no_phantom_write() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await TriageRepository(session).get("al-missing") is None
    finally:
        await database.dispose()
    assert (
        await _write(**_base(alert_id="al-missing", expected_version=1, status="dismissed")) is None
    )


@pytest.mark.asyncio
async def test_duplicate_create_preserves_original_and_cas_advances() -> None:
    first = await _write(**_base(alert_id="al-dup", status="open", reason="first"))
    assert first is not None and first["expected_version"] == 1
    assert await _write(**_base(alert_id="al-dup", status="dismissed", reason="second")) is None
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            kept = await TriageRepository(session).get("al-dup")
    finally:
        await database.dispose()
    assert kept is not None and kept["status"] == "open" and kept["reason"] == "first"
    second = await _write(
        **_base(alert_id="al-dup", expected_version=1, status="linked", incident_id="inc-1")
    )
    assert second is not None and second["expected_version"] == 2
    third = await _write(**_base(alert_id="al-dup", expected_version=2, status="dismissed"))
    assert third is not None and third["expected_version"] == 3
    assert third["incident_id"] is None


@pytest.mark.asyncio
async def test_linkage_length_and_actor_invariants_reject_bad_rows() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            for status, incident_id, severity, reason, actor in (
                ("dismissed", "inc-x", None, None, "op-human"),
                ("open", "inc-x", None, None, "op-human"),
                ("declared", "inc-x", "bogus", None, "op-human"),
                ("open", None, None, "x" * 1001, "op-human"),
                ("open", None, None, None, None),
            ):
                with pytest.raises((IntegrityError, DataError)):
                    async with session.begin_nested():
                        await session.execute(
                            text(
                                "INSERT INTO alert_triage (alert_id, status, incident_id,"
                                " expected_version, reason, severity, actor, decided_at)"
                                " VALUES ('al-ck2', :status, :incident_id, 1, :reason,"
                                " :severity, :actor, now())"
                            ),
                            {
                                "status": status,
                                "incident_id": incident_id,
                                "severity": severity,
                                "reason": reason,
                                "actor": actor,
                            },
                        )
    finally:
        await database.dispose()
