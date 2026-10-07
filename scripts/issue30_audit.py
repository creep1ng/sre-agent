"""Bounded audit inspection and safe artifact output for Issue 30 replay."""

import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def _rows(db, ids, start, end):
    return db.execute(
        """SELECT correlation->>'request_id' request_id, occurred_at,
          response_status, operation, action, stage, outcome,
          policy_decision->>'decision' decision, reason_code,
          length(identity->'principal_ref'->>'digest')=64 has_identity_hmac,
          length(resource->'resource_ref'->>'digest')=64 has_resource_hmac,
          COALESCE(jsonb_typeof(policy_decision),'null')<>'null' has_decision,
          content_state,
          COALESCE(jsonb_typeof(redacted_content),'null')='null' no_content,
          COALESCE(jsonb_typeof(untrusted_input),'null')='null' no_untrusted
          FROM audit_events WHERE operation='mcp.invoke'
            AND correlation->>'request_id'=ANY(%s)
            AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz
          ORDER BY occurred_at""",
        (ids, start, end),
    ).fetchall()


def collect_audit(out, check, database_url):
    """Collect only this replay's audit metadata and assert the published stages."""
    out["audit_window"] = {
        "start": out["started_at"],
        "end": out["ended_at"],
    }
    with psycopg.connect(database_url, row_factory=dict_row) as db:
        ids = [item.get("request_id") for item in out["cases"].values()]
        rows = _rows(db, [value for value in ids if value], out["started_at"], out["ended_at"])

        for name, item in out["cases"].items():
            correlation_id = item.get("request_id")
            matched = [row for row in rows if row["request_id"] == correlation_id]
            item["audit_rows_observed"] = len(matched)
            expected_count = 0 if item["status_expected"] == 401 else 1
            check(len(matched) == expected_count, name + ":bounded audit row count")
            for row in matched:
                stage = {
                    200: "response",
                    403: "authorization",
                    422: "validation",
                    502: "upstream",
                    503: "upstream",
                    504: "upstream",
                }[item["status_expected"]]
                check(row["response_status"] == item["status_expected"], name + ":audit status")
                check(row["stage"] == stage, name + ":audit stage")
                decision = "deny" if item["status_expected"] == 403 else "allow"
                if stage != "validation":
                    check(row["decision"] == decision, name + ":audit decision")
                outcome = (
                    "denied"
                    if item["status_expected"] == 403
                    else "success"
                    if item["status_expected"] == 200
                    else "error"
                )
                check(row["outcome"] == outcome, name + ":audit outcome")
                check(row["action"] == "invoke", name + ":audit action")
                check(
                    row["content_state"] == "absent" and row["no_content"] and row["no_untrusted"],
                    name + ":metadata-only",
                )
                if stage == "validation":
                    check(
                        not row["has_identity_hmac"]
                        and not row["has_resource_hmac"]
                        and not row["has_decision"],
                        name + ":validation stage omits context per published audit contract",
                    )
                    item["audit_contract_note"] = (
                        "validation stage intentionally omits identity/resource/decision"
                    )
                else:
                    check(
                        row["has_identity_hmac"]
                        and row["has_resource_hmac"]
                        and row["has_decision"],
                        name + ":CA4 HMAC identity/resource/decision",
                    )
                item["audit"] = {
                    key: row[key]
                    for key in (
                        "response_status",
                        "action",
                        "stage",
                        "outcome",
                        "decision",
                        "reason_code",
                        "has_identity_hmac",
                        "has_resource_hmac",
                        "has_decision",
                    )
                }
        out["audit"] = rows


def emit_artifact(out, secrets, path="/capture/issue30-live-replay.json"):
    """Persist only sanitized evidence; never emit a response or exception body."""
    out.setdefault("sanitized", True)
    encoded = json.dumps(out, default=str)
    if any(secret and secret in encoded for secret in secrets):
        out = {
            "tested_sha": out.get("tested_sha"),
            "result": "failed",
            "sanitized": True,
            "failures": ["artifact secret exclusion"],
        }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "result": out.get("result"),
                "tested_sha": out.get("tested_sha"),
                "artifact": Path(path).name,
                "failure_count": len(out.get("failures", [])),
            }
        )
    )
    return out
