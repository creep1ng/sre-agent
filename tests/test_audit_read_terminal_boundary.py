"""Real PostgreSQL HTTP proofs for the governed audit-read terminal boundary."""

import asyncio
import os
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "AUDIT_READS_DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"),
)
AUDIT_KEY = "issue25-audit-reads-test-key"
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
DEMO_KEY = "sre_demo_0123456789abcdefghijklmnop"
INCIDENT_KEY = "sre_inci_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": ADMIN_KEY,
    "DEMO_HUMAN_API_KEY": DEMO_KEY,
    "INCIDENT_HARNESS_API_KEY": INCIDENT_KEY,
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}
UUID_MISSING = "00000000-0000-4000-8000-000000000000"


@pytest.fixture(scope="module", autouse=True)
def migrated_audit_database() -> Iterator[None]:
    """Reset only the explicitly configured isolated acceptance database."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        if connection.info.dbname not in {"python_checks", "sre_agent_issue25_audit"}:
            pytest.fail("audit HTTP acceptance requires its dedicated test database")
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, bok_section_chunks, bok_documents, "
            "bok_collection_versions, audit_events, skill_versions, grants, credentials, "
            "resources, mcp_tools, mcp_servers, principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            assert await seed(database, SeedSettings.from_environment(SEED_ENV))
        finally:
            await database.dispose()

    asyncio.run(bootstrap())
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _projection_rows(*, request_id: str | None = None) -> list[dict[str, Any]]:
    where = ""
    parameters: tuple[str, ...] = ()
    if request_id is not None:
        where = " AND correlation->>'request_id' = %s"
        parameters = (request_id,)
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT to_jsonb(a) FROM audit_events a WHERE operation='audit.project'"
            + where
            + " ORDER BY occurred_at, event_id",
            parameters,
        ).fetchall()
    return [row[0] for row in rows]


def _assert_terminal_row(response, status: int) -> dict[str, Any]:
    request_id = response.json()["request_id"]
    rows = _projection_rows(request_id=request_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["operation"] == "audit.project"
    assert row["action"] == "read_metadata"
    assert row["response_status"] == status
    assert row["correlation"]["request_id"] == request_id
    assert row["content_state"] == "absent"
    assert row.get("redacted_content") is None
    assert row["identity"] is None if status in {401, 422} else True
    assert row["resource"] is None if status in {401, 422} else True
    return row


def _latest_projection_row() -> dict[str, Any]:
    rows = _projection_rows()
    assert rows
    return rows[-1]


def _latest_http_event(operation: str, response_status: int) -> dict[str, Any]:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT to_jsonb(a) FROM audit_events a WHERE operation=%s AND response_status=%s "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1",
            (operation, response_status),
        ).fetchone()
    assert row is not None
    return row[0]


def test_list_and_detail_success_are_audited_without_content(client: TestClient) -> None:
    produced = client.get(
        "/v1/grants?principal_id=admin-human",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert produced.status_code == 200, produced.text
    source = _latest_http_event("grants.list", 200)
    source_request_id = source["correlation"]["request_id"]
    before = len(_projection_rows())

    listing = client.get(
        f"/v1/audit-events?request_id={source_request_id}",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert listing.status_code == 200, listing.text
    assert set(listing.json()) == {"items", "limit", "truncated"}
    assert len(listing.json()["items"]) == 1
    projected_source = listing.json()["items"][0]
    assert projected_source["correlation"]["request_id"] == source_request_id
    assert projected_source["event_id"] == source["event_id"]
    assert "redacted_content" not in projected_source
    assert "secret" not in listing.text.lower()
    assert len(_projection_rows()) == before + 1
    list_event = _latest_projection_row()
    assert list_event["response_status"] == 200
    assert list_event["stage"] == "authorization"
    assert list_event["policy_decision"]["decision"] == "allow"
    assert list_event["content_state"] == "absent"

    before = len(_projection_rows())
    detail = client.get(
        f"/v1/audit-events/{projected_source['event_id']}",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["event_id"] == projected_source["event_id"]
    assert "redacted_content" not in detail.json()
    assert len(_projection_rows()) == before + 1
    detail_event = _latest_projection_row()
    assert detail_event["response_status"] == 200
    assert detail_event["stage"] == "authorization"
    assert detail_event["policy_decision"]["decision"] == "allow"
    assert detail_event["content_state"] == "absent"


def test_terminal_authz_validation_and_not_found_results_are_audited(
    client: TestClient,
) -> None:
    before = len(_projection_rows())
    unauthorized = client.get(f"/v1/audit-events/{UUID_MISSING}")
    assert unauthorized.status_code == 401, unauthorized.text
    unauthorized_row = _assert_terminal_row(unauthorized, 401)
    assert unauthorized_row["stage"] == "authentication"
    assert unauthorized_row["outcome"] == "error"
    assert len(_projection_rows()) == before + 1

    before = len(_projection_rows())
    denied = client.get(
        "/v1/audit-events/not-a-uuid",
        headers={"Authorization": f"Bearer {RESTRICTED_KEY}"},
    )
    assert denied.status_code == 403, denied.text
    denied_row = _assert_terminal_row(denied, 403)
    assert denied_row["stage"] == "authorization"
    assert denied_row["outcome"] == "denied"
    assert denied_row["policy_decision"]["decision"] == "deny"
    assert len(_projection_rows()) == before + 1

    before = len(_projection_rows())
    missing = client.get(
        f"/v1/audit-events/{UUID_MISSING}",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert missing.status_code == 404, missing.text
    missing_row = _assert_terminal_row(missing, 404)
    assert missing_row["stage"] == "authorization"
    assert missing_row["outcome"] == "error"
    assert missing_row["policy_decision"]["decision"] == "allow"
    assert (
        missing.json()["error"]
        == client.get(
            f"/v1/audit-events/{UUID_MISSING}",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        ).json()["error"]
    )
    assert len(_projection_rows()) == before + 2

    before = len(_projection_rows())
    malformed = client.get(
        "/v1/audit-events/INVALID",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert malformed.status_code == 422, malformed.text
    malformed_row = _assert_terminal_row(malformed, 422)
    assert malformed_row["stage"] == "validation"
    assert malformed_row["reason_code"] == "contract_validation_failed"
    assert len(_projection_rows()) == before + 1

    before = len(_projection_rows())
    bad_filter = client.get(
        "/v1/audit-events?limit=10",
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert bad_filter.status_code == 422, bad_filter.text
    bad_filter_row = _assert_terminal_row(bad_filter, 422)
    assert bad_filter_row["stage"] == "validation"
    assert len(_projection_rows()) == before + 1


def test_valid_unauthorized_and_forbidden_ids_never_query_audit_targets(
    client: TestClient,
) -> None:
    database = client.app.state.database
    target_selects: list[str] = []

    def record_target_select(connection, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.lower().split())
        if "from audit_events" in normalized and "event_id" in normalized:
            target_selects.append(normalized)

    event.listen(database.engine.sync_engine, "before_cursor_execute", record_target_select)
    try:
        for event_id, headers, status in (
            (UUID_MISSING, {}, 401),
            ("not-a-uuid", {"Authorization": f"Bearer {RESTRICTED_KEY}"}, 403),
        ):
            target_selects.clear()
            response = client.get(f"/v1/audit-events/{event_id}", headers=headers)
            assert response.status_code == status, response.text
            assert target_selects == []
            _assert_terminal_row(response, status)
            assert target_selects == []
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", record_target_select)


def test_query_failure_returns_retryable_503_and_persists_terminal_event(
    client: TestClient,
) -> None:
    database = client.app.state.database

    def fail_audit_detail_read(connection, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.lower().split())
        if "from audit_events" in normalized and "event_id" in normalized:
            raise RuntimeError("synthetic audit detail query failure")

    event.listen(database.engine.sync_engine, "before_cursor_execute", fail_audit_detail_read)
    try:
        response = client.get(
            f"/v1/audit-events/{UUID_MISSING}",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", fail_audit_detail_read)
    assert response.status_code == 503, response.text
    assert response.json()["retryable"] is True
    row = _assert_terminal_row(response, 503)
    assert row["stage"] == "authorization"
    assert row["outcome"] == "error"
    assert row["policy_decision"]["decision"] == "allow"


def test_failed_audit_append_suppresses_a_denied_read_response() -> None:
    class RejectingAudit:
        async def append(self, audit_event: object) -> None:
            raise RuntimeError("synthetic audit append failure")

        async def append_in_transaction(self, audit_event: object, session: object) -> None:
            raise RuntimeError("synthetic audit append failure")

    before = len(_projection_rows())
    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/audit-events/not-a-uuid",
            headers={"Authorization": f"Bearer {RESTRICTED_KEY}"},
        )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "audit_unavailable"
    assert response.json()["retryable"] is True
    assert len(_projection_rows()) == before
