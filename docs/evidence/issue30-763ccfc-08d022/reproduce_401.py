"""Repeat only the existing invalid-credential case; capture actual safe HTTP/SQL."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg

with httpx.Client(timeout=10, trust_env=False) as client:
    before = client.get("http://grafana-mcp:8000/__count").json()
    forward_before = client.get("http://issue30-fault-proxy:8000/__stats").json()
    start = datetime.now(UTC).isoformat()
    key = "sre-invalid-" + uuid4().hex
    response = client.post(
        "http://api:8000/v1/mcp/tools/query_prometheus",
        headers={"Authorization": "Bearer " + key},
        json={
            "datasource_uid": "webstore-metrics",
            "expr": "vector(1)",
            "query_type": "instant",
            "end_time": "now",
        },
    )
    end = datetime.now(UTC).isoformat()
    after = client.get("http://grafana-mcp:8000/__count").json()
    forward_after = client.get("http://issue30-fault-proxy:8000/__stats").json()
    body = response.json()
    assert set(body) == {"error", "request_id", "retryable"}
    assert set(body["error"]) == {"code", "message"}
    assert key not in json.dumps(body)
with psycopg.connect(
    os.environ["DATABASE_URL"], options="-c default_transaction_read_only=on"
) as db:
    rows = db.execute(
        """SELECT to_jsonb(a) FROM audit_events a
WHERE correlation->>'request_id'=%s
AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz""",
        (body["request_id"], start, end),
    ).fetchall()
    auth_rows = db.execute(
        """SELECT count(*) FROM audit_events
WHERE (stage='authentication' OR operation='credentials.authenticate'
OR (response_status=401 AND reason_code='authentication_failed'))
AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz""",
        (start, end),
    ).fetchone()[0]
out = {
    "tested_sha": os.environ["TESTED_SHA"],
    "scenario": "separate repeat of CA2_invalid_credential",
    "request": (
        "POST /v1/mcp/tools/query_prometheus, synthetic vector(1), "
        "invalid credential; header omitted"
    ),
    "window_start": start,
    "window_end": end,
    "status_observed": response.status_code,
    "actual_public_body": body,
    "counter_before": before,
    "counter_after": after,
    "forward_before": forward_before,
    "forward_after": forward_after,
    "tools_call_delta": after["mcp_methods"].get("tools/call", 0)
    - before["mcp_methods"].get("tools/call", 0),
    "all_operation_sql_row_count": len(rows),
    "authentication_row_count_in_window": auth_rows,
    "terminal_event_required": 1,
    "terminal_event_observed": len(rows),
    "terminal_event_requirement": "passed" if len(rows) == 1 else "failed",
    "sanitized": True,
}
Path("/capture/401-reproduction.json").write_text(json.dumps(out, indent=2) + "\n")
print(
    json.dumps(
        {
            "status": response.status_code,
            "public_body": body,
            "tools_call_delta": out["tools_call_delta"],
            "all_operation_sql_row_count": len(rows),
            "terminal_event_requirement": out["terminal_event_requirement"],
        }
    )
)
if len(rows) != 1:
    raise SystemExit(1)
