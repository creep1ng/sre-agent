"""Read complete current-run SQL events without changing the acceptance runner."""

import hashlib
import json
import os
from pathlib import Path

import psycopg
from audit_contract import authentication_event_valid, canonical_event, contract_validator

capture = Path("/capture")
replay = json.loads((capture / "issue30-live-replay.json").read_text())
validator, schema_dir = contract_validator(os.getenv("SRE_AGENT_CONTRACT_VERSION", "2.7.0"))
schema = validator.schema
ids = [item["request_id"] for item in replay["cases"].values() if item.get("request_id")]
start, end = replay["started_at"], replay["ended_at"]
invalid = replay["cases"]["CA2_invalid_credential"]
query = """SELECT to_jsonb(a) FROM audit_events a
WHERE correlation->>'request_id'=ANY(%s)
  AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz
ORDER BY occurred_at,event_id"""
with psycopg.connect(
    os.environ["DATABASE_URL"], options="-c default_transaction_read_only=on"
) as db:
    rows = [row[0] for row in db.execute(query, (ids, start, end)).fetchall()]
    missing = db.execute(
        """SELECT operation,stage,response_status,count(*) FROM audit_events
WHERE correlation->>'request_id'=%s
  AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz
GROUP BY operation,stage,response_status""",
        (invalid["request_id"], invalid["window_start"], invalid["window_end"]),
    ).fetchall()
    outside = db.execute(
        "SELECT count(*) FROM audit_events WHERE correlation->>'request_id'=%s",
        (invalid["request_id"],),
    ).fetchone()[0]
    auth = db.execute(
        """SELECT operation,stage,response_status,count(*) FROM audit_events
WHERE (stage='authentication' OR operation='credentials.authenticate'
       OR (reason_code='authentication_failed' AND response_status=401))
  AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz
GROUP BY operation,stage,response_status""",
        (start, end),
    ).fetchall()
    all_operations = db.execute(
        """SELECT operation,stage,response_status,count(*) FROM audit_events
WHERE occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz
GROUP BY operation,stage,response_status ORDER BY operation,stage,response_status""",
        (start, end),
    ).fetchall()


events = [canonical_event(row, schema["required"]) for row in rows]
safe = json.dumps({"rows": rows, "events": events}, ensure_ascii=True)
secrets = [
    os.getenv(k, "")
    for k in [
        "ADMIN_HUMAN_API_KEY",
        "DEMO_HUMAN_API_KEY",
        "INCIDENT_HARNESS_API_KEY",
        "RESTRICTED_HARNESS_API_KEY",
        "AUDIT_HMAC_KEY",
    ]
]
assert not any(secret and secret in safe for secret in secrets), "secret exclusion failed"
assert all(
    row.get("redacted_content") is None and row.get("untrusted_input") is None for row in rows
), "unexpected content must remain private"
assert "Bearer " not in safe and "sre_" not in safe, "unexpected raw identifier/credential"
results = []
for event in events:
    errors = []
    for error in validator.iter_errors(event):
        errors.append(
            {
                "validator": error.validator,
                "instance_path": "/" + "/".join(map(str, error.absolute_path)),
                "schema_path": "/" + "/".join(map(str, error.absolute_schema_path)),
            }
        )
    results.append(
        {
            "request_id": event["correlation"]["request_id"],
            "event_id": event["event_id"],
            "operation": event["operation"],
            "stage": event["stage"],
            "response_status": event["response_status"],
            "retryable_observed": event["retryable"],
            "latency_ms": event["latency_ms"],
            "validation": "failed" if errors else "passed",
            "errors": errors,
        }
    )
for name, values in [
    ("sql-storage-full.jsonl", rows),
    ("audit-events-full.jsonl", events),
    ("audit-schema-results.jsonl", results),
]:
    (capture / name).write_text("".join(json.dumps(v, sort_keys=True) + "\n" for v in values))
credential_events = [e for e in events if e["correlation"]["request_id"] == invalid["request_id"]]
auth_valid = len(credential_events) == 1 and authentication_event_valid(
    credential_events[0],
    validator,
    invalid["request_id"],
    invalid["window_start"],
    invalid["window_end"],
)
summary = {
    "tested_sha": replay["tested_sha"],
    "schema_id": schema["$id"],
    "schema_sha256": hashlib.sha256(
        (schema_dir / "domain/audit-event.schema.json").read_bytes()
    ).hexdigest(),
    "selection": {
        "request_ids": ids,
        "window_start": start,
        "window_end": end,
        "operation_filter": None,
        "sql": query,
    },
    "rows": len(rows),
    "schema_passed": sum(r["validation"] == "passed" for r in results),
    "schema_failed": sum(r["validation"] == "failed" for r in results),
    "storage_representation": "complete SQL columns, including SQL NULL, retained separately",
    "contract_representation": (
        "Only optional top-level SQL NULL omitted; required root NULLs and all JSONB values "
        "preserved, including explicit nested NULLs; no field values repaired"
    ),
    "invalid_credential": {
        "request_id": invalid["request_id"],
        "window_start": invalid["window_start"],
        "window_end": invalid["window_end"],
        "all_operation_matches": missing,
        "same_request_id_all_database_count": outside,
        "authentication_matches_in_replay_window": auth,
        "terminal_event_required_by_runtime_audit_evidence": 1,
        "terminal_event_requirement": "passed" if auth_valid else "failed",
        "unchanged_legacy_runner_expected_mcp_invoke_rows": 0,
    },
    "all_operation_stage_counts_in_replay_window": all_operations,
    "sanitized": True,
}
(capture / "audit-full-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(
    json.dumps(
        {
            "rows": summary["rows"],
            "schema_passed": summary["schema_passed"],
            "schema_failed": summary["schema_failed"],
            "invalid_credential_all_operation_rows": sum(r[3] for r in missing),
            "same_request_id_all_database_count": outside,
            "auth_operation_rows_in_window": sum(r[3] for r in auth),
        }
    )
)
if (
    summary["schema_failed"]
    or summary["invalid_credential"]["terminal_event_requirement"] == "failed"
):
    raise SystemExit(1)
