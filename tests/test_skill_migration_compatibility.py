"""Exercise real populated histories, not stamped approximations of old schemas."""

import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import AddConstraint
from test_demo_seeds import ENV

from sre_agent.gateway.health import postgres_readiness_probe
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def snapshot():
    with psycopg.connect(DATABASE_URL) as connection:
        return {
            "rows": connection.execute(
                "SELECT to_jsonb(audit_events) FROM audit_events ORDER BY event_id"
            ).fetchall(),
            "grants": connection.execute(
                "SELECT to_jsonb(grants) FROM grants ORDER BY grant_id"
            ).fetchall(),
            "heads": connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            ).fetchall(),
            "constraint": connection.execute(
                "SELECT pg_get_constraintdef(oid), convalidated FROM pg_constraint "
                "WHERE conrelid='audit_events'::regclass AND conname='ck_audit_events_operation'"
            ).fetchone(),
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("legacy", "operation", "previous"),
    [
        ("20260926_14", "usage.read", "20260922_12"),
        ("20260926_15", "catalog.status.replace", "20260924_14"),
    ],
)
@pytest.mark.parametrize("fault", [None, "failure", "unvalidated"])
async def test_populated_upgrade_preserves_evidence_and_rolls_back(
    legacy, operation, previous, fault
):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
        connection.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, legacy)
    database = Database(DATABASE_URL)
    try:
        await seed(database, SeedSettings.from_environment(ENV))
    finally:
        await database.dispose()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO audit_events (
            event_id, occurred_at, operation, action, stage, outcome, response_status,
            retryable, latency_ms, correlation, redaction, content_state,
            authoritative_acceptance, ordinary_result, exporter_result)
            VALUES ('00000000-0000-4000-8000-000000000081', now(), %s, 'admin.read',
            'audit', 'success', 200, false, 0, '{}', '{}', 'absent',
            'accepted', 'released', 'not_attempted')""",
            (operation,),
        )
    before = snapshot()
    with pytest.raises(RuntimeError, match="cannot downgrade"):
        command.downgrade(config, previous)
    assert snapshot() == before
    if legacy == "20260926_14":
        with pytest.raises(IntegrityError, match="ck_audit_events_operation"):
            command.upgrade(config, "20260926_15")
        assert snapshot() == before

    def inject_failure(connection, clause, multiparams, params, options):
        if isinstance(clause, AddConstraint):
            constraint = clause.element
            definition = str(constraint.sqltext)
            if "'usage.read'" in definition and "'catalog.status.replace'" in definition:
                if fault == "failure":
                    raise RuntimeError("injected union failure")
                constraint.dialect_options["postgresql"]["not_valid"] = True

    if fault:
        event.listen(Engine, "before_execute", inject_failure)
        try:
            with pytest.raises(RuntimeError, match="injected union failure|integration incomplete"):
                command.upgrade(config, "head")
        finally:
            event.remove(Engine, "before_execute", inject_failure)
        assert snapshot() == before
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    after = snapshot()
    assert after["rows"] == before["rows"]
    assert after["grants"] == before["grants"]
    assert after["heads"] == [("20260930_18",)]
    with pytest.raises(RuntimeError, match="cannot downgrade integration"):
        command.downgrade(config, "20260930_17")
    assert snapshot() == after
    definition, validated = after["constraint"]
    assert validated is True
    assert "'usage.read'" in definition and "'catalog.status.replace'" in definition
    await postgres_readiness_probe(DATABASE_URL)()
    with psycopg.connect(DATABASE_URL) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO audit_events SELECT (jsonb_populate_record(NULL::audit_events, "
                "to_jsonb(audit_events) || "
                '\'{"event_id":"00000000-0000-4000-8000-000000000082",'
                '"operation":"unknown.operation"}\'::jsonb)).* FROM audit_events'
            )
    print(
        f"legacy={legacy} fault={fault} rows={len(after['rows'])} "
        f"grants={len(after['grants'])} heads={after['heads']} validated={validated}"
    )
