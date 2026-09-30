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
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, audit_events, grants, credentials, "
            "resources, "
            "principals, idempotency_records, mcp_tools, mcp_servers, alembic_version CASCADE"
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


def test_repeated_head_has_expected_domain_tables() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
    assert {row[0] for row in rows} == {
        "alembic_version",
        "audit_events",
        "credentials",
        "consumption_reservations",
        "consumption_limit_policies",
        "grants",
        "idempotency_records",
        "mcp_servers",
        "mcp_tools",
        "principals",
        "resources",
    }


def test_mcp_tool_foreign_key_points_to_owner_server() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        definitions = connection.execute(
            """SELECT pg_get_constraintdef(constraint_oid)
            FROM (
              SELECT oid AS constraint_oid
              FROM pg_constraint
              WHERE conrelid = 'mcp_tools'::regclass AND contype = 'f'
            ) constraints"""
        ).fetchall()
    assert any(
        definition[0] == "FOREIGN KEY (server_id) REFERENCES mcp_servers(server_id)"
        for definition in definitions
    )


def test_mcp_audit_migration_allows_metadata_operations() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        operation_check = connection.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_audit_events_operation'"
        ).fetchone()[0]
    assert "'mcp.discovery'" in operation_check
    assert "'mcp.invoke'" in operation_check


def test_mcp_owner_tables_have_closed_lifecycle_constraints() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        constraints = {
            table: {
                row[0]
                for row in connection.execute(
                    "SELECT conname FROM pg_constraint WHERE conrelid=%s::regclass", (table,)
                )
            }
            for table in ("mcp_servers", "mcp_tools")
        }
    assert constraints["mcp_servers"] >= {
        "pk_mcp_servers",
        "ck_mcp_servers_contract_version",
        "ck_mcp_servers_status",
        "ck_mcp_servers_visibility",
        "ck_mcp_servers_lifecycle",
    }
    assert constraints["mcp_tools"] >= {
        "pk_mcp_tools",
        "uq_mcp_tools_server_upstream",
        "ck_mcp_tools_contract_version",
        "ck_mcp_tools_status",
        "ck_mcp_tools_visibility",
        "ck_mcp_tools_lifecycle",
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


def test_control_read_denial_404_is_valid_but_other_404_denials_are_rejected() -> None:
    insert = """INSERT INTO audit_events (
      event_id, occurred_at, operation, action, stage, outcome, reason_code,
      response_status, retryable, latency_ms, correlation, resource, redaction, content_state,
      authoritative_acceptance, ordinary_result, exporter_result, authorization_denial_cause)
    VALUES (%s, now(), %s, %s, 'authorization', 'denied', 'no_matching_grant', %s, false, 1,
      '{}', %s, '{}', 'absent', 'accepted', 'released', 'not_attempted', 'resource_missing')"""
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            insert,
            (
                "00000000-0000-4000-8000-000000000089",
                "principals.get",
                "admin.read",
                404,
                '{"resource_type":"administrative_control"}',
            ),
        )
        connection.execute(
            """INSERT INTO audit_events (
              event_id, occurred_at, operation, action, stage, outcome, reason_code,
              response_status, retryable, latency_ms, correlation, resource, redaction,
              content_state, authoritative_acceptance, ordinary_result, exporter_result)
            VALUES ('00000000-0000-4000-8000-000000000092', now(),
              'principals.status.replace', 'admin.write', 'authorization', 'error',
              'status_conflict', 409, false, 1, '{}',
              '{"resource_type":"administrative_control"}', '{}', 'absent',
              'accepted', 'released', 'not_attempted')"""
        )
        connection.rollback()
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                insert,
                (
                    "00000000-0000-4000-8000-000000000090",
                    "responses.create",
                    "invoke",
                    404,
                    '{"resource_type":"llm_model"}',
                ),
            )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                insert,
                (
                    "00000000-0000-4000-8000-000000000093",
                    "principals.get",
                    "admin.read",
                    404,
                    None,
                ),
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
                "INSERT INTO resources (resource_type, resource_id, status, updated_at, "
                "model_alias_id, alias, concrete_model, router, inference_provider) VALUES "
                "('skill','triage-agent','active',now(),'alias-id',NULL,NULL,NULL,NULL)"
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


def test_404_denial_evidence_prevents_fail_open_downgrade() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO audit_events (
              event_id, occurred_at, operation, action, stage, outcome, reason_code,
              response_status, retryable, latency_ms, correlation, resource, redaction,
              content_state, authoritative_acceptance, ordinary_result, exporter_result,
              authorization_denial_cause)
            VALUES ('00000000-0000-4000-8000-000000000091', now(), 'principals.get',
              'admin.read', 'authorization', 'denied', 'no_matching_grant', 404, false, 1,
              '{}', '{"resource_type":"administrative_control"}', '{}', 'absent',
              'accepted', 'released', 'not_attempted', 'resource_missing')"""
        )
        connection.commit()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    with pytest.raises(RuntimeError, match="cannot downgrade"):
        command.downgrade(config, "20260902_04")


def test_catalog_projection_migration_exposes_mcp_provenance_constraints() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        columns = {
            row[0]
            for row in connection.execute(
                """SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='resources'
                  AND column_name IN ('owner_id','source','source_ref','display_name',
                                      'visibility','description','tags')"""
            )
        }
        assert columns == {
            "owner_id",
            "source",
            "source_ref",
            "display_name",
            "visibility",
            "description",
            "tags",
        }
        constraints = {
            row[0]
            for row in connection.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid='resources'::regclass"
            )
        }
        assert {
            "ck_resources_catalog_projection",
            "ck_resources_catalog_source",
            "ck_resources_catalog_visibility",
            "ck_resources_catalog_owner",
        } <= constraints
        operation_check = connection.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_audit_events_operation'"
        ).fetchone()[0]
        assert all(
            f"'{operation}'" in operation_check
            for operation in (
                "catalog.create",
                "catalog.list",
                "catalog.read",
            )
        )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                """INSERT INTO resources (
                  resource_type, resource_id, status, updated_at, model_alias_id, alias,
                  concrete_model, router, inference_provider, owner_id, source, source_ref,
                  display_name, visibility, description, tags)
                VALUES ('mcp_tool', 'grafana.alerts.query', 'registered', now(), NULL, NULL,
                  NULL, NULL, NULL, 'admin', 'skill', 'grafana', 'Grafana alerts', 'private',
                  '', '[]'::jsonb)"""
            )


def test_consumption_column_is_nullable_jsonb_and_legacy_rows_remain_null() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        metadata = connection.execute(
            """SELECT is_nullable, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='audit_events'
              AND column_name='consumption'"""
        ).fetchone()
        assert metadata == ("YES", "jsonb", "jsonb")
        assert connection.execute(
            "SELECT consumption FROM audit_events WHERE event_id=%s",
            ("00000000-0000-4000-8000-000000000000",),
        ).fetchone() == (None,)


def test_consumption_is_append_only_with_exact_decimal_json() -> None:
    consumption = (
        '{"availability":"complete","source":"openrouter",'
        '"input_tokens":11,"output_tokens":7,"total_tokens":18,'
        '"billed_usd":"0.0012300","currency":"USD","precision":"exact",'
        '"pricing_context":{"observed_at":"2026-09-10T14:00:00Z",'
        '"price_version":"openrouter:2026-09-10T14:00:00Z"}}'
    )
    event_id = "00000000-0000-4000-8000-000000000130"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO audit_events (
              event_id, occurred_at, operation, action, stage, outcome, reason_code,
              response_status, retryable, latency_ms, correlation, redaction, content_state,
              authoritative_acceptance, ordinary_result, exporter_result, consumption)
            VALUES (%s, now(), 'responses.create', 'invoke', 'response', 'success',
              'grant_matched', 200, false, 1, '{}', '{}', 'absent', 'accepted',
              'released', 'not_attempted', %s::jsonb)""",
            (event_id, consumption),
        )
        connection.commit()
        assert connection.execute(
            "SELECT consumption->>'billed_usd' FROM audit_events WHERE event_id=%s",
            (event_id,),
        ).fetchone() == ("0.0012300",)
        with (
            pytest.raises(psycopg.errors.RaiseException, match="audit_events are append-only"),
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE audit_events SET consumption='{}'::jsonb WHERE event_id=%s", (event_id,)
            )


def test_consumption_policy_defaults_and_bigint_storage() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT policy_id, version, incident_token_limit, monthly_usd_limit "
            "FROM consumption_limit_policies"
        ).fetchall() == [(1, 0, None, None)]
        connection.execute(
            "UPDATE consumption_limit_policies SET version=2147483648, "
            "incident_token_limit=2147483648, monthly_usd_limit=0.000000000001"
        )
        assert connection.execute(
            "SELECT version, incident_token_limit, monthly_usd_limit::text "
            "FROM consumption_limit_policies"
        ).fetchone() == (2147483648, 2147483648, "0.000000000001")
        connection.rollback()


@pytest.mark.parametrize(
    "column", ["policy_id", "version", "incident_token_limit", "monthly_usd_limit"]
)
def test_consumption_policy_rejects_invalid_storage(column: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(f"UPDATE consumption_limit_policies SET {column}=-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        "consumption_limits.get",
        "consumption_limits.replace",
        "usage.read",
        "catalog.create",
        "catalog.list",
        "catalog.read",
    ],
)
async def test_consumption_audit_vocabulary_persists_without_rewriting_history(
    operation: str,
) -> None:
    from uuid import uuid4

    from sre_agent.gateway.audit import AuditProjector
    from sre_agent.gateway.responses import PostgresAuditStore

    database = Database(DATABASE_URL)
    try:
        event = AuditProjector(b"synthetic-migration-evidence").control_event(
            uuid4(),
            503,
            0,
            "audit",
            operation=operation,
            action="admin.write" if operation.endswith("replace") else "admin.read",
            reason="upstream_unavailable",
            retryable=True,
        )
        await PostgresAuditStore(database.sessions).append(event)
        with psycopg.connect(DATABASE_URL) as connection:
            assert connection.execute(
                "SELECT operation, content_state, consumption FROM audit_events WHERE event_id=%s",
                (str(event.event_id),),
            ).fetchone() == (operation, "absent", None)
            assert connection.execute(
                "SELECT consumption->>'billed_usd' FROM audit_events WHERE event_id=%s",
                ("00000000-0000-4000-8000-000000000130",),
            ).fetchone() == ("0.0012300",)
    finally:
        await database.dispose()


def test_consumption_sql_audit_evidence_blocks_lossy_downgrade() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO audit_events SELECT (jsonb_populate_record(NULL::audit_events, "
            "to_jsonb(a) || jsonb_build_object('operation','consumption_limits.get', "
            "'event_id','00000000-0000-4000-8000-000000000334'))).* "
            "FROM audit_events a WHERE event_id='00000000-0000-4000-8000-000000000000'"
        )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    with pytest.raises(RuntimeError, match="consumption.*audit evidence"):
        command.downgrade(config, "20260926_14")
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260929_17",
        )
        assert connection.execute("SELECT count(*) FROM consumption_limit_policies").fetchone() == (
            1,
        )


def test_consumption_put_binding_persists_and_blocks_lossy_downgrade() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals (principal_id,kind,display_name,status,created_at,updated_at) "
            "VALUES ('policy-schema-admin','human','Synthetic administrator','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO idempotency_records (scope,key_digest,payload_sha256,principal_id,method,"
            "canonical_path,binding,outcome,created_at,expires_at,transition_count) "
            "VALUES ('policy-schema-admin|PUT|/v1/consumption-limits',"
            "repeat('a',64),repeat('b',64),"
            "'policy-schema-admin','PUT','/v1/consumption-limits','at_least_24h',"
            '\'{"response_status":200,"response_payload":{"version":1}}\','
            "now(),now()+interval '1 day',1)"
        )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    with pytest.raises(RuntimeError, match="PUT.*bindings"):
        command.downgrade(config, "20260929_15")
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute(
            "SELECT method, transition_count, outcome->'response_payload'->>'version' "
            "FROM idempotency_records WHERE principal_id='policy-schema-admin'"
        ).fetchone() == ("PUT", 1, "1")
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260929_17",
        )
