"""Real isolated gateway/auth/PostgreSQL/counting-boundary acceptance replay.

Failure checks defined before replay: hidden metadata, wrong status/error,
401 MCP rows, missing/duplicate authenticated rows, content leakage, upstream
crossings during discovery, absent positive control, and handshake conflation.
Never prints credentials, response bodies, query results or exceptions.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from psycopg.rows import dict_row


def utc():
    return datetime.now(UTC).isoformat()


out = {
    "tested_sha": os.environ.get("TESTED_SHA", ""),
    "started_at": utc(),
    "surface": "real isolated HTTP gateway, API-key auth, PostgreSQL, pinned MCP boundary",
    "sanitized": True,
    "provider_calls": "none; Grafana backend query success not claimed",
    "cases": {},
    "counter": {},
    "checks": [],
}
client = httpx.Client(base_url="http://api:8000", timeout=40)
count = httpx.Client(base_url="http://grafana-mcp:8000", timeout=10)
admin = full = denied = ""
keys = {}


def check(condition, label):
    out["checks"].append({"check": label, "passed": bool(condition)})
    if not condition:
        raise AssertionError(label)


def mutate(path, payload):
    response = client.post(
        path,
        json=payload,
        headers={"Authorization": "Bearer " + admin, "Idempotency-Key": str(uuid4())},
    )
    check(response.is_success, "synthetic setup " + path)
    return response.json()


def probe(name, path, key=None, payload=None):
    headers = {"Authorization": "Bearer " + key} if key else {}
    response = (
        client.get(path, headers=headers)
        if payload is None
        else client.post(path, headers=headers, json=payload)
    )
    body = response.json()
    item = {
        "request_id": body.get("request_id"),
        "http_status": response.status_code,
        "error_code": body.get("error", {}).get("code"),
        "observed_at": utc(),
    }
    if "tools" in body:
        item["tool_ids"] = [tool["tool_id"] for tool in body["tools"]]
        item["metadata_fields_present"] = all(
            set(
                (
                    "tool_id",
                    "server_id",
                    "display_name",
                    "description",
                    "visibility",
                    "tags",
                    "action",
                )
            )
            <= set(tool)
            for tool in body["tools"]
        )
        hidden = (
            "query_elasticsearch",
            "Query Elasticsearch",
            "Read Elasticsearch logs.",
        )
        item["restricted_metadata_absent"] = all(value not in response.text for value in hidden)
    out["cases"][name] = item
    return item


try:
    check(
        len(out["tested_sha"]) == 40 and all(c in "0123456789abcdef" for c in out["tested_sha"]),
        "full tested SHA supplied",
    )
    admin = os.environ["ADMIN_HUMAN_API_KEY"]
    full = os.environ["DEMO_HUMAN_API_KEY"]
    denied = os.environ["RESTRICTED_HARNESS_API_KEY"]
    suffix = uuid4().hex[:8]
    for role in ("partial", "empty"):
        pid = "i29-" + role + "-" + suffix
        mutate(
            "/v1/principals",
            {
                "principal_id": pid,
                "kind": "human",
                "display_name": "Issue 29 synthetic",
            },
        )
        keys[role] = mutate(f"/v1/principals/{pid}/credentials", {})["key"]
        mutate(
            "/v1/grants",
            {
                "grant_id": "grant-" + pid + "-discovery",
                "principal_id": pid,
                "action": "mcp.discovery",
                "effect": "allow",
                "resource": {
                    "resource_type": "mcp_server",
                    "resource_id": "grafana-mcp",
                },
            },
        )
        if role == "partial":
            mutate(
                "/v1/grants",
                {
                    "grant_id": "grant-" + pid + "-invoke",
                    "principal_id": pid,
                    "action": "mcp.invoke",
                    "effect": "allow",
                    "resource": {
                        "resource_type": "mcp_tool",
                        "resource_id": "query_prometheus",
                    },
                },
            )
    out["counter"]["reset_before_discovery"] = count.post("/__count/reset").json()
    out["discovery_window_start"] = utc()
    out["counter"]["before_discovery"] = count.get("/__count").json()
    specs = [
        ("full", full, 200, None),
        ("partial", keys["partial"], 200, None),
        ("empty", keys["empty"], 200, None),
        ("denied", denied, 403, "resource_unavailable"),
        ("unknown_key", "sre_" + uuid4().hex, 401, "authentication_failed"),
        ("no_key", None, 401, "authentication_failed"),
        ("invalid_query", full, 422, "contract_validation_failed"),
    ]
    for name, key, status, error in specs:
        path = "/v1/mcp/discovery" + ("?unexpected=1" if name == "invalid_query" else "")
        item = probe(name, path, key)
        check(
            item["http_status"] == status and item["error_code"] == error,
            name + " status/code",
        )
    check(
        out["cases"]["full"]["tool_ids"] == ["query_prometheus", "query_elasticsearch"],
        "full visibility",
    )
    check(
        out["cases"]["partial"]["tool_ids"] == ["query_prometheus"]
        and out["cases"]["partial"]["restricted_metadata_absent"],
        "partial hides metadata",
    )
    check(
        out["cases"]["empty"]["tool_ids"] == []
        and out["cases"]["empty"]["restricted_metadata_absent"],
        "empty hides metadata",
    )
    check(
        all(out["cases"][name]["metadata_fields_present"] for name in ("full", "partial", "empty")),
        "published metadata",
    )
    payload = {
        "datasource_uid": "webstore-metrics",
        "expr": "up",
        "query_type": "instant",
        "end_time": "now",
    }
    item = probe("denied_invoke", "/v1/mcp/tools/query_prometheus", denied, payload)
    check(
        item["http_status"] == 403 and item["error_code"] == "resource_unavailable",
        "denied invoke",
    )
    out["counter"]["after_discovery"] = count.get("/__count").json()
    out["discovery_window_end"] = utc()
    check(
        all(
            out["counter"][name]["total_http_requests"] == 0
            for name in ("before_discovery", "after_discovery")
        ),
        "zero discovery/denial boundary calls",
    )
    item = probe("cold_invoke_control", "/v1/mcp/tools/query_prometheus", full, payload)
    check(
        item["http_status"] == 502 and item["error_code"] == "upstream_invalid",
        "cold control upstream rejection, not success",
    )
    out["counter"]["after_cold_control"] = count.get("/__count").json()
    check(
        out["counter"]["after_cold_control"]["mcp_methods"]
        == {"initialize": 1, "notifications/initialized": 1, "tools/call": 1},
        "cold handshake separate from tools call",
    )
    out["counter"]["reset_before_warm_control"] = count.post("/__count/reset").json()
    item = probe("warm_invoke_control", "/v1/mcp/tools/query_prometheus", full, payload)
    check(
        item["http_status"] == 502 and item["error_code"] == "upstream_invalid",
        "warm control upstream rejection, not success",
    )
    out["counter"]["after_warm_control"] = count.get("/__count").json()
    check(
        out["counter"]["after_warm_control"]["total_http_requests"] == 1
        and out["counter"]["after_warm_control"]["mcp_methods"] == {"tools/call": 1},
        "warm epoch one tools call, no handshake",
    )
    out["capture_window_end"] = utc()
    ids = [item["request_id"] for item in out["cases"].values()]
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        rows = db.execute(
            """SELECT correlation->>'request_id' AS request_id, occurred_at,
          response_status, operation, action, stage, outcome,
          policy_decision->>'decision' AS decision, reason_code,
          length(identity->'principal_ref'->>'digest') = 64 AS has_principal_hmac,
          length(resource->'resource_ref'->>'digest') = 64 AS has_resource_hmac,
          content_state, COALESCE(jsonb_typeof(redacted_content), 'null') = 'null' AS no_content,
          COALESCE(jsonb_typeof(untrusted_input), 'null') = 'null' AS no_untrusted_input
          FROM audit_events WHERE operation IN ('mcp.discovery', 'mcp.invoke')
          AND correlation->>'request_id' = ANY(%s)
          AND occurred_at >= %s::timestamptz AND occurred_at < %s::timestamptz
          ORDER BY occurred_at""",
            (ids, out["discovery_window_start"], out["capture_window_end"]),
        ).fetchall()
    out["audit"] = rows
    discovery = [r for r in rows if r["operation"] == "mcp.discovery"]
    check(
        len(discovery) == 5 and len(rows) == 8,
        "scoped five discovery and three invoke rows",
    )
    for name, item in out["cases"].items():
        matched = [r for r in rows if r["request_id"] == item["request_id"]]
        check(
            len(matched) == (0 if item["http_status"] == 401 else 1),
            name + " audit correlation",
        )
    check(
        all(
            r["content_state"] == "absent"
            and r["no_content"]
            and r["no_untrusted_input"]
            and r["has_principal_hmac"]
            and r["has_resource_hmac"]
            for r in rows
        ),
        "metadata-only HMAC audit",
    )
    out["result"] = "passed"
except Exception as error:
    out["result"] = "failed"
    out["failure_type"] = type(error).__name__
finally:
    out["ended_at"] = utc()
    secrets = (admin, full, denied, *keys.values())
    result = json.dumps(out, indent=2, default=str) + "\n"
    safe = not any(value and value in result for value in secrets)
    out["checks"].append({"check": "artifact secret exclusion", "passed": safe})
    if not safe:
        # Never write an artifact that contains any configured/generated API key.
        out = {
            "tested_sha": out.get("tested_sha"),
            "started_at": out.get("started_at"),
            "ended_at": out["ended_at"],
            "sanitized": True,
            "result": "failed",
            "failure_type": "SanitizationError",
            "cases": {},
            "counter": {},
            "checks": [{"check": "artifact secret exclusion", "passed": False}],
        }
    Path("/capture").mkdir(parents=True, exist_ok=True)
    Path("/capture/live-replay.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "result": out["result"],
                "tested_sha": out.get("tested_sha"),
                "artifact": "live-replay.json",
                "checks": len(out["checks"]),
            }
        )
    )
    if out["result"] != "passed":
        raise SystemExit(1)
