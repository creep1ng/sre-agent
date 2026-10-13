"""Repeat only the existing invalid-credential case; capture actual safe HTTP/SQL."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
from audit_contract import authentication_event_valid, canonical_event, contract_validator

with httpx.Client(timeout=10, trust_env=False) as client:
    version = client.get("http://api:8000/openapi.json").json()["info"][
        "x-sre-agent-contract-version"
    ]
    validator, _ = contract_validator(version)
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
    parsed = True
    try:
        body = response.json()
    except ValueError:
        body, parsed = None, False
    request_id = body.get("request_id") if isinstance(body, dict) else None
    try:
        UUID(request_id)
    except (ValueError, TypeError, AttributeError):
        request_id = None
    public_shape = (
        isinstance(body, dict)
        and set(body) == {"error", "request_id", "retryable"}
        and isinstance(body["error"], dict)
        and set(body["error"]) == {"code", "message"}
        and request_id is not None
        and key not in json.dumps(body)
    )

with psycopg.connect(
    os.environ["DATABASE_URL"], options="-c default_transaction_read_only=on"
) as db:
    rows = (
        db.execute(
            """SELECT to_jsonb(a) FROM audit_events a
WHERE correlation->>'request_id'=%s
AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz""",
            (request_id, start, end),
        ).fetchall()
        if request_id
        else []
    )
    window_rows = db.execute(
        "SELECT count(*) FROM audit_events WHERE occurred_at >= %s::timestamptz "
        "AND occurred_at < %s::timestamptz",
        (start, end),
    ).fetchone()[0]
    auth_rows = db.execute(
        """SELECT count(*) FROM audit_events
WHERE (stage='authentication' OR operation='credentials.authenticate'
OR (response_status=401 AND reason_code='authentication_failed'))
AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz""",
        (start, end),
    ).fetchone()[0]
events = [canonical_event(row[0], validator.schema["required"]) for row in rows]
methods_before, methods_after = before["mcp_methods"], after["mcp_methods"]
checks = {
    "http_contract": public_shape
    and response.status_code == 401
    and response.headers.get("WWW-Authenticate") == "Bearer"
    and body["error"] == {"code": "authentication_failed", "message": "Authentication failed."}
    and body["retryable"] is False,
    "zero_mcp_activity": all(
        methods_before.get(k, 0) == methods_after.get(k, 0)
        for k in methods_before.keys() | methods_after.keys()
    )
    and before["upstream_attempts"] == after["upstream_attempts"]
    and before["reset_epoch"] == after["reset_epoch"]
    and before.get("total_http_requests", 0) == after.get("total_http_requests", 0),
    "zero_forwarding": all(
        forward_before["forwarded_methods"].get(k, 0)
        == forward_after["forwarded_methods"].get(k, 0)
        for k in forward_before["forwarded_methods"].keys()
        | forward_after["forwarded_methods"].keys()
    ),
    "complete_authentication_event": len(events) == 1
    and authentication_event_valid(events[0], validator, request_id, start, end),
}
passed = all(checks.values())
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
    "actual_public_body": body if checks["http_contract"] else None,
    "contract_version": version,
    "bearer_challenge_valid": response.headers.get("WWW-Authenticate") == "Bearer",
    "checks": checks,
    "public_json_parsed": parsed,
    "correlation_available": request_id is not None,
    "all_operation_rows_in_window": window_rows,
    "audit_events": events if passed else [],
    "counter_before": before,
    "counter_after": after,
    "forward_before": forward_before,
    "forward_after": forward_after,
    "tools_call_delta": after["mcp_methods"].get("tools/call", 0)
    - before["mcp_methods"].get("tools/call", 0),
    "all_operation_sql_row_count": len(rows) if request_id else None,
    "authentication_row_count_in_window": auth_rows,
    "terminal_event_required": 1,
    "terminal_event_observed": len(rows) if request_id else None,
    "terminal_event_requirement": "passed" if passed else "failed",
    "sanitized": True,
}
Path("/capture/401-reproduction.json").write_text(json.dumps(out, indent=2) + "\n")
print(
    json.dumps(
        {
            "status": response.status_code,
            "public_body": out["actual_public_body"],
            "tools_call_delta": out["tools_call_delta"],
            "all_operation_sql_row_count": len(rows) if request_id else None,
            "terminal_event_requirement": out["terminal_event_requirement"],
        }
    )
)
if not passed:
    raise SystemExit(1)
