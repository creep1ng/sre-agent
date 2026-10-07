"""Capture sanitized real HTTP/PostgreSQL evidence for issue #25 audit reads."""

import json
import os
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from sqlalchemy import event

from sre_agent.application import create_application
from sre_agent.settings import Settings

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
AUDIT_KEY = "issue25-audit-reads-test-key"
ADMIN_KEY = "sre_admn_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"


def projection_snapshot() -> set[str]:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT event_id FROM audit_events WHERE operation='audit.project'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def new_projections(previous_ids: set[str]) -> list[dict]:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT to_jsonb(a) FROM audit_events a WHERE operation='audit.project'"
        ).fetchall()
    return [row[0] for row in rows if row[0]["event_id"] not in previous_ids]


def report(
    label: str,
    response,
    previous_ids: set[str],
    *,
    expected_status: int,
    persisted: bool = True,
) -> dict:
    body = response.json()
    request_id = body.get("request_id")
    rows = new_projections(previous_ids)
    if response.status_code != expected_status:
        raise AssertionError(
            f"{label}: expected HTTP {expected_status}, got {response.status_code}"
        )
    if persisted and len(rows) != 1:
        raise AssertionError(f"{label}: expected exactly one new audit row, got {len(rows)}")
    if not persisted:
        if rows:
            raise AssertionError(f"{label}: expected no new audit row, got {len(rows)}")
        if not request_id:
            raise AssertionError(f"{label}: failed response did not expose its request ID")
        with psycopg.connect(DATABASE_URL) as connection:
            count = connection.execute(
                "SELECT count(*) FROM audit_events WHERE operation='audit.project' "
                "AND correlation->>'request_id'=%s",
                (request_id,),
            ).fetchone()[0]
        if count != 0:
            raise AssertionError(f"{label}: request ID unexpectedly exists in audit SQL")
    row = rows[0] if rows else None
    if row:
        row_request_id = row["correlation"]["request_id"]
        if request_id and row_request_id != request_id:
            raise AssertionError(f"{label}: response and audit request IDs differ")
        if row["response_status"] != expected_status:
            raise AssertionError(f"{label}: persisted status differs from expected status")
        if row["operation"] != "audit.project" or row["action"] != "read_metadata":
            raise AssertionError(f"{label}: unexpected audit operation/action")
        if row["content_state"] != "absent" or row.get("redacted_content") is not None:
            raise AssertionError(f"{label}: audit row contains unexpected content")
    result = {
        "case": label,
        "http_status": response.status_code,
        "retryable": body.get("retryable"),
        "request_id": request_id or (row["correlation"]["request_id"] if row else None),
        "audit_persisted": row is not None,
        "new_audit_rows": len(rows),
    }
    if row:
        result.update(
            {
                "event_id": row["event_id"],
                "operation": row["operation"],
                "action": row["action"],
                "audit_status": row["response_status"],
                "stage": row["stage"],
                "outcome": row["outcome"],
                "content_state": row["content_state"],
                "redacted_content_is_null": row.get("redacted_content") is None,
            }
        )
    elif response.status_code >= 400:
        result["error_code"] = body["error"]["code"]
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        if connection.info.dbname not in {"python_checks", "sre_agent_issue25_audit"}:
            raise RuntimeError("capture requires the dedicated acceptance database")

    app = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(app, raise_server_exceptions=False) as client:
        produced = client.get(
            "/v1/grants?principal_id=admin-human",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        if produced.status_code != 200:
            raise AssertionError("controlled producer request failed")
        with psycopg.connect(DATABASE_URL) as connection:
            producer = connection.execute(
                "SELECT correlation->>'request_id',event_id FROM audit_events "
                "WHERE operation='grants.list' AND response_status=200 "
                "ORDER BY occurred_at DESC,event_id DESC LIMIT 1"
            ).fetchone()
        before = projection_snapshot()
        listing = client.get(
            f"/v1/audit-events?request_id={producer[0]}",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        report("list_200", listing, before, expected_status=200)
        source_event = next(
            item for item in listing.json()["items"] if item["event_id"] == str(producer[1])
        )
        before = projection_snapshot()
        detail = client.get(
            f"/v1/audit-events/{source_event['event_id']}",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        report("detail_200", detail, before, expected_status=200)
        if "redacted_content" in listing.text or "redacted_content" in detail.text:
            raise AssertionError("HTTP response exposed the redacted-content field")
        print(json.dumps({"case": "response_content_absent", "actual": True}))

        cases = (
            ("unauthenticated_401", "/v1/audit-events/abc", None, 401),
            ("restricted_403", "/v1/audit-events/cor_not-a-uuid", RESTRICTED_KEY, 403),
            ("missing_404", "/v1/audit-events/abc", ADMIN_KEY, 404),
            ("malformed_422", "/v1/audit-events/INVALID", ADMIN_KEY, 422),
        )
        for label, path, key, status in cases:
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            before = projection_snapshot()
            response = client.get(path, headers=headers)
            report(label, response, before, expected_status=status)

        database = app.state.database

        def fail_detail_query(connection, cursor, statement, parameters, context, executemany):
            normalized = " ".join(statement.lower().split())
            if "from audit_events" in normalized and "event_id" in normalized:
                raise RuntimeError("synthetic detail-query failure")

        event.listen(database.engine.sync_engine, "before_cursor_execute", fail_detail_query)
        before = projection_snapshot()
        try:
            response = client.get(
                "/v1/audit-events/abc",
                headers={"Authorization": f"Bearer {ADMIN_KEY}"},
            )
        finally:
            event.remove(database.engine.sync_engine, "before_cursor_execute", fail_detail_query)
        report("query_failure_503", response, before, expected_status=503)

    class RejectingAudit:
        async def append(self, audit_event: object) -> None:
            raise RuntimeError("synthetic append rejection")

        async def append_in_transaction(self, audit_event: object, session: object) -> None:
            raise RuntimeError("synthetic append rejection")

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=RejectingAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        before = projection_snapshot()
        response = client.get(
            "/v1/audit-events/cor_not-a-uuid",
            headers={"Authorization": f"Bearer {RESTRICTED_KEY}"},
        )
    report(
        "append_failure_503",
        response,
        before,
        expected_status=503,
        persisted=False,
    )

    class NoOpAudit:
        async def append(self, audit_event: object) -> None:
            return None

        async def append_in_transaction(self, audit_event: object, session: object) -> None:
            return None

    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=NoOpAudit()
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        before = projection_snapshot()
        response = client.get(
            f"/v1/audit-events/{source_event['event_id']}",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
    try:
        report("controlled_noop_mutation", response, before, expected_status=200)
    except AssertionError as error:
        print(
            json.dumps(
                {
                    "case": "probe_rejects_noop_mutation",
                    "actual": True,
                    "reason": str(error),
                }
            )
        )
    else:
        raise AssertionError("audit invariant probe accepted an append-suppression mutation")

    class DoubleAppendAudit:
        sessions = None

        async def append(self, audit_event: object) -> None:
            from sre_agent.gateway.responses import PostgresAuditStore

            store = PostgresAuditStore(self.sessions)
            await store.append(audit_event)
            duplicate = audit_event.model_copy(update={"event_id": uuid4()})
            await store.append(duplicate)

        async def append_in_transaction(self, audit_event: object, session: object) -> None:
            raise AssertionError("transactional append is not expected for this HTTP path")

    double_append = DoubleAppendAudit()
    app = create_application(
        Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY), audit_store=double_append
    )
    double_append.sessions = app.state.database.sessions
    with TestClient(app, raise_server_exceptions=False) as client:
        before = projection_snapshot()
        response = client.get(
            f"/v1/audit-events/{source_event['event_id']}",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
    try:
        report("controlled_double_append_mutation", response, before, expected_status=200)
    except AssertionError as error:
        print(
            json.dumps(
                {
                    "case": "probe_rejects_double_append_mutation",
                    "actual": True,
                    "reason": str(error),
                }
            )
        )
    else:
        raise AssertionError("audit invariant probe accepted a double-append mutation")


if __name__ == "__main__":
    main()
