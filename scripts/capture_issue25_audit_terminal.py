"""Capture sanitized real HTTP/PostgreSQL evidence for issue #25 audit reads."""

import json
import os
from typing import Literal
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


class AuditRowCountMismatch(AssertionError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected {expected} new audit rows, got {actual}")
        self.expected = expected
        self.actual = actual


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
    expected_envelope: Literal["error", "list", "detail"],
    persisted: bool = True,
) -> dict:
    body = response.json()
    if response.status_code != expected_status:
        raise AssertionError(
            f"{label}: expected HTTP {expected_status}, got {response.status_code}"
        )
    if not isinstance(body, dict):
        raise AssertionError(f"{label}: expected a JSON object response")
    request_id = body.get("request_id")
    if expected_envelope == "list":
        valid_envelope = (
            response.status_code == 200
            and set(body) == {"items", "limit", "truncated"}
            and isinstance(body["items"], list)
            and isinstance(body["limit"], int)
            and isinstance(body["truncated"], bool)
        )
    elif expected_envelope == "detail":
        valid_envelope = (
            response.status_code == 200
            and isinstance(body.get("event_id"), str)
            and bool(body["event_id"].strip())
            and isinstance(body.get("correlation"), dict)
            and isinstance(body["correlation"].get("request_id"), str)
            and bool(body["correlation"]["request_id"].strip())
        )
    else:
        valid_envelope = (
            response.status_code >= 400
            and isinstance(body.get("error"), dict)
            and isinstance(body["error"].get("code"), str)
            and isinstance(body["error"].get("message"), str)
        )
    if not valid_envelope:
        raise AssertionError(f"{label}: expected {expected_envelope} success envelope")
    if expected_envelope != "error":
        if request_id is not None and (not isinstance(request_id, str) or not request_id.strip()):
            raise AssertionError(f"{label}: response request ID is malformed")
    elif not isinstance(request_id, str) or not request_id.strip():
        raise AssertionError(f"{label}: error response did not expose a request ID")
    rows = new_projections(previous_ids)
    if not persisted:
        if rows:
            raise AuditRowCountMismatch(0, len(rows))
        with psycopg.connect(DATABASE_URL) as connection:
            count = connection.execute(
                "SELECT count(*) FROM audit_events WHERE operation='audit.project' "
                "AND correlation->>'request_id'=%s",
                (request_id,),
            ).fetchone()[0]
        if count != 0:
            raise AssertionError(f"{label}: request ID unexpectedly exists in audit SQL")
    for row in rows:
        row_request_id = row["correlation"]["request_id"]
        if request_id and row_request_id != request_id:
            raise AssertionError(f"{label}: response and audit request IDs differ")
        if request_id is None:
            request_id = row_request_id
        elif row_request_id != request_id:
            raise AssertionError(f"{label}: audit rows have inconsistent request IDs")
        if row["response_status"] != expected_status:
            raise AssertionError(f"{label}: persisted status differs from expected status")
        if row["operation"] != "audit.project" or row["action"] != "read_metadata":
            raise AssertionError(f"{label}: unexpected audit operation/action")
        if row["content_state"] != "absent" or row.get("redacted_content") is not None:
            raise AssertionError(f"{label}: audit row contains unexpected content")
    if persisted and len(rows) != 1:
        raise AuditRowCountMismatch(1, len(rows))
    row = rows[0] if rows else None
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


def expect_mutation_probe_rejection(
    label: str,
    response,
    previous_ids: set[str],
    *,
    expected_status: int,
    expected_envelope: Literal["list", "detail"],
    expected_rows: int,
) -> None:
    try:
        report(
            label,
            response,
            previous_ids,
            expected_status=expected_status,
            expected_envelope=expected_envelope,
        )
    except AuditRowCountMismatch as error:
        if error.expected != 1 or error.actual != expected_rows:
            raise AssertionError(
                f"{label}: expected the exact 1-to-{expected_rows} row-count rejection"
            ) from error
        print(
            json.dumps(
                {
                    "case": f"probe_rejects_{label}",
                    "actual": True,
                    "expected_rows": error.expected,
                    "observed_rows": error.actual,
                },
                sort_keys=True,
            )
        )
    else:
        raise AssertionError(f"{label}: audit invariant probe accepted the mutation")


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
        report("list_200", listing, before, expected_status=200, expected_envelope="list")
        source_event = next(
            item for item in listing.json()["items"] if item["event_id"] == str(producer[1])
        )
        before = projection_snapshot()
        detail = client.get(
            f"/v1/audit-events/{source_event['event_id']}",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        report("detail_200", detail, before, expected_status=200, expected_envelope="detail")
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
            report(label, response, before, expected_status=status, expected_envelope="error")

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
        report(
            "query_failure_503", response, before, expected_status=503, expected_envelope="error"
        )

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
        expected_envelope="error",
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
    expect_mutation_probe_rejection(
        "controlled_noop_mutation",
        response,
        before,
        expected_status=200,
        expected_envelope="detail",
        expected_rows=0,
    )

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
    expect_mutation_probe_rejection(
        "controlled_double_append_mutation",
        response,
        before,
        expected_status=200,
        expected_envelope="detail",
        expected_rows=2,
    )


if __name__ == "__main__":
    main()
