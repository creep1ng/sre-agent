"""Exercise real populated histories, not stamped approximations of old schemas."""

import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
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
        ("20260926_15", "catalog.status.replace", "20260930_20"),
        ("20260926_16", "skills.resolve", "20260926_15"),
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
    if legacy == "20260930_18" and operation == "usage.read":
        command.downgrade(config, previous)
        preserved = snapshot()
        assert preserved["rows"] == before["rows"]
        definition, _validated = preserved["constraint"]
        assert "'usage.read'" in definition
        assert "'catalog.status.replace'" not in definition
        command.upgrade(config, legacy)
        assert snapshot()["rows"] == before["rows"]
    else:
        with pytest.raises(RuntimeError, match="cannot downgrade"):
            command.downgrade(config, previous)
        assert snapshot() == before

    def inject_failure(connection, clause, multiparams, params, options):
        if isinstance(clause, AddConstraint):
            constraint = clause.element
            definition = str(constraint.sqltext)
            if "'usage.read'" in definition and "'skills.resolve'" in definition:
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
    if legacy == "20260926_14":
        command.upgrade(config, "20260926_15")
        upgraded = snapshot()
        assert upgraded["rows"] == before["rows"]
        assert "'usage.read'" in upgraded["constraint"][0]
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    after = snapshot()
    assert after["rows"] == before["rows"]
    assert after["grants"] == before["grants"]
    assert after["heads"] == [("20261009_01",)]

    # Each revision guards only the evidence it owns. Leaving the slice that introduced
    # the persisted operation is lossy and must be refused, while rolling back past a
    # sibling slice that does not own it must keep every row intact.
    if legacy == "20260926_14":
        command.downgrade(config, "20260926_14")
        assert snapshot()["rows"] == after["rows"]
        command.upgrade(config, "head")
        assert snapshot()["rows"] == after["rows"]
    else:
        with pytest.raises(RuntimeError, match="cannot downgrade"):
            command.downgrade(config, "20260926_14")
        assert snapshot() == after
    definition, validated = after["constraint"]
    assert validated is True
    assert "'usage.read'" in definition and "'catalog.status.replace'" in definition
    assert "'skills.resolve'" in definition
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


def test_populated_legacy_triage_row_upgrades_as_unknown_without_actor_inference():
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
        connection.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "20260923_13")

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO alert_triage (alert_id, status, incident_id, expected_version,"
            " reason, severity, actor, decided_at) VALUES ('al-legacy-origin', 'declared',"
            " 'inc-legacy-origin', 3, 'legacy decision', 'sev2', 'producer-agent', now())"
        )
        legacy = connection.execute(
            "SELECT alert_id, status, incident_id, expected_version, reason, severity,"
            " actor, decided_at FROM alert_triage WHERE alert_id='al-legacy-origin'"
        ).fetchone()

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        current = connection.execute(
            "SELECT alert_id, status, incident_id, expected_version, reason, severity,"
            " actor, decided_at, decision_origin, responsible_system FROM alert_triage "
            "WHERE alert_id='al-legacy-origin'"
        ).fetchone()
        head = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert current[:8] == legacy
    assert current[8:] == ("unknown", None)
    assert head == ("20261009_01",)

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE alert_triage SET decision_origin='manual' WHERE alert_id='al-legacy-origin'"
        )
    with pytest.raises(RuntimeError, match="cannot downgrade while provenance data exists"):
        command.downgrade(config, "20260923_13")
    with psycopg.connect(DATABASE_URL) as connection:
        kept = connection.execute(
            "SELECT decision_origin, responsible_system FROM alert_triage "
            "WHERE alert_id='al-legacy-origin'"
        ).fetchone()
        head = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert kept == ("manual", None)
    assert head == ("20261009_01",)


@pytest.mark.parametrize(
    ("source_head", "command_id", "triage_origin", "responsible_system"),
    [
        ("20260928_14", "cmd-" + "x" * 146, None, None),
        ("20261006_01", "cmd-sibling-commit", "external_automatic", "synthetic-monitor"),
    ],
)
def test_populated_sibling_heads_merge_without_losing_branch_rows(
    source_head, command_id, triage_origin, responsible_system
):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
        connection.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, source_head)

    incident_id = "inc-populated-sibling-head"
    now = "2026-10-07T12:00:00+00:00"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO incident.incidents (incident_id, state, version, created_at, updated_at) "
            "VALUES (%s, '{}'::jsonb, 0, %s, %s)",
            (incident_id, now, now),
        )
        connection.execute(
            "INSERT INTO incident.transition_commits "
            "(incident_id, command_id, payload_sha256, result, committed_at) "
            "VALUES (%s, %s, %s, '{}'::jsonb, %s)",
            (incident_id, command_id, "a" * 64, now),
        )
        if triage_origin is not None:
            connection.execute(
                "INSERT INTO alert_triage (alert_id, status, incident_id, expected_version, "
                "reason, severity, actor, decided_at, decision_origin, responsible_system) "
                "VALUES ('al-sibling-origin', 'linked', %s, 3, 'external association', 'sev2', "
                "'authorized-producer', %s, %s, %s)",
                (incident_id, now, triage_origin, responsible_system),
            )

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        commit = connection.execute(
            "SELECT command_id, payload_sha256, result FROM incident.transition_commits "
            "WHERE incident_id=%s",
            (incident_id,),
        ).fetchone()
        heads = connection.execute(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        ).fetchall()
        if triage_origin is not None:
            triage = connection.execute(
                "SELECT decision_origin, responsible_system FROM alert_triage "
                "WHERE alert_id='al-sibling-origin'"
            ).fetchone()
    assert commit == (command_id, "a" * 64, {})
    if source_head == "20260928_14":
        assert len(command_id) == 150
    else:
        assert len(command_id) <= 128
    assert heads == [("20261009_01",)]
    if triage_origin is not None:
        assert triage == (triage_origin, responsible_system)
