"""Issue 30 real-stack replay. Assertions intentionally precede support services.

Failure inventory: wrong public status/code; unauthenticated/upstream crossing;
handshake counted as a tool call; non-deterministic normalized vector; unsafe
error leakage; uncorrelated/missing/duplicate audit rows; audit content capture;
discovery required for an ID; timeout/failure contracts not mapped safely.
Artifacts contain only statuses, codes, counters, request IDs, and audit metadata.
"""

import os
import re
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from issue30_audit import collect_audit, emit_artifact

API = httpx.Client(base_url="http://api:8000", timeout=40)
COUNT = httpx.Client(base_url="http://grafana-mcp:8000", timeout=10)
FAULT = httpx.Client(base_url="http://issue30-fault-proxy:8000", timeout=5)
OUT = {
    "tested_sha": os.getenv("TESTED_SHA", ""),
    "started_at": datetime.now(UTC).isoformat(),
    "environment": "isolated Docker gateway/PostgreSQL/Grafana/Prometheus/pinned MCP",
    "instrument_counts": "HTTP attempts and MCP initialize/initialized/tools/call separately",
    "cases": {},
    "failures": [],
    "sanitized": True,
}
SECRETS = []


def check(ok, label):
    if not ok:
        OUT["failures"].append(label)
    return bool(ok)


def now():
    return datetime.now(UTC).isoformat()


def admin_post(path, data):
    r = API.post(
        path,
        json=data,
        headers={
            "Authorization": "Bearer " + os.environ["ADMIN_HUMAN_API_KEY"],
            "Idempotency-Key": str(uuid4()),
        },
    )
    check(r.is_success, "setup:" + path)
    return r.json() if r.is_success else {}


def make_identity(label, grant=None):
    pid = "i30-" + label + "-" + uuid4().hex[:8]
    admin_post(
        "/v1/principals",
        {"principal_id": pid, "kind": "human", "display_name": "Issue 30 synthetic"},
    )
    key = admin_post(f"/v1/principals/{pid}/credentials", {}).get("key", "")
    SECRETS.append(key)
    if grant:
        admin_post(
            "/v1/grants",
            {
                "grant_id": "grant-" + pid,
                "principal_id": pid,
                "action": "mcp.invoke",
                "effect": "allow",
                "resource": {"resource_type": "mcp_tool", "resource_id": grant},
            },
        )
    return key


def request(name, key, body, status, code=None, mode="pass", expected_calls=1):
    reset = COUNT.post("/__count/reset").json()
    FAULT.post("/__stats/reset")
    FAULT.post("/__mode", json={"mode": mode})
    start = now()
    headers = {"Idempotency-Key": str(uuid4())}
    if key is not None:
        headers["Authorization"] = "Bearer " + key
    r = API.post("/v1/mcp/tools/query_prometheus", json=body, headers=headers)
    end = now()
    stats = COUNT.get("/__count").json()
    payload = r.json()
    executed = FAULT.get("/__stats").json().get("forwarded_methods", {})
    reqid = (payload.get("request_id") if isinstance(payload, dict) else None) or r.headers.get(
        "x-request-id"
    )
    item = {
        "status_expected": status,
        "status_observed": r.status_code,
        "command": "POST /v1/mcp/tools/query_prometheus",
        "code_expected": code,
        "code_observed": payload.get("error", {}).get("code"),
        "request_id": reqid,
        "window_start": start,
        "window_end": end,
        "counter": stats,
        "expected_tools_call_delta": expected_calls,
        "counter_reset": reset,
        "actual_upstream_forwarded_methods": executed,
        "mode": mode,
        "safe_error_body": None,
    }
    if status == 200 and isinstance(payload, dict):
        result = payload.get("result", [])
        sample = result[0] if result and isinstance(result[0], dict) else {}
        value = sample.get("value", []) if isinstance(sample, dict) else []
        item["normalized"] = {
            "result_type": payload.get("result_type"),
            "vector_count": len(result),
            "empty_metric": sample.get("metric") == {},
            "sample_value": value[1] if len(value) == 2 else None,
            "timestamp_run_dependent": len(value) == 2,
        }
        check(
            payload.get("result_type") == "vector"
            and len(result) == 1
            and sample.get("metric") == {}
            and len(value) == 2
            and value[1] == "1"
            and payload.get("warnings") == [],
            name + ":normalized deterministic vector(1)",
        )
    if status != 200:
        item["safe_error_body"] = (
            isinstance(payload, dict)
            and set(payload) <= {"error", "request_id", "retryable"}
            and isinstance(payload.get("error"), dict)
            and set(payload["error"]) == {"code", "message"}
            and payload["error"].get("code") == code
            and payload["error"].get("message") == code.replace("_", " ").capitalize() + "."
            and "ISSUE30_UPSTREAM_SENTINEL" not in r.text
            and not any(secret and secret in r.text for secret in SECRETS)
        )
    check(r.status_code == status and item["code_observed"] == code, name + ":public contract")
    if status == 200:
        check(reqid is not None, name + ":success public request correlation")
    check(
        reset.get("total_http_requests") == 0
        and not reset.get("mcp_methods")
        and stats.get("reset_epoch") == reset.get("reset_epoch")
        and stats.get("mcp_methods", {}).get("tools/call", 0) == expected_calls,
        name + ":tools/call delta after isolated reset",
    )
    handshakes = {
        m: stats.get("mcp_methods", {}).get(m, 0)
        for m in ("initialize", "notifications/initialized")
    }
    expected_handshake = 1 if name == "CA5_allowed_known_id" else 0
    check(
        all(count == expected_handshake for count in handshakes.values()),
        name + ":handshake separated",
    )
    expected_exec = 1 if status == 200 and mode == "pass" else 0
    check(executed.get("tools/call", 0) == expected_exec, name + ":real MCP execution delta")
    if status != 200:
        check(item["safe_error_body"], name + ":safe public error shape")
    OUT["cases"][name] = item
    return item


def main():
    global OUT
    check(bool(re.fullmatch(r"[0-9a-f]{40}", OUT["tested_sha"])), "full tested SHA")
    admin = os.environ["ADMIN_HUMAN_API_KEY"]
    demo = os.environ["DEMO_HUMAN_API_KEY"]
    SECRETS.extend([admin, demo, os.environ["RESTRICTED_HARNESS_API_KEY"]])
    allowed = make_identity("allowed", "query_prometheus")
    none = make_identity("no-grant")
    wrong = make_identity("other-tool", "query_elasticsearch")
    base = {
        "datasource_uid": "webstore-metrics",
        "expr": "vector(1)",
        "query_type": "instant",
        "end_time": "now",
    }
    # Known IDs are tested before any discovery; reset counters makes first handshake explicit.
    request("CA5_allowed_known_id", allowed, base, 200, expected_calls=1)
    request("CA5_denied_known_id", none, base, 403, "resource_unavailable", expected_calls=0)
    scenarios = [
        ("CA2_nonvisible_tool_id", wrong, base, 403, "resource_unavailable", "pass", 0),
        (
            "CA2_no_grant",
            os.environ["RESTRICTED_HARNESS_API_KEY"],
            base,
            403,
            "resource_unavailable",
            "pass",
            0,
        ),
        (
            "CA2_invalid_credential",
            "sre-invalid-" + uuid4().hex,
            base,
            401,
            "authentication_failed",
            "pass",
            0,
        ),
        (
            "CA3_invalid_input",
            allowed,
            {**base, "unexpected": "sentinel"},
            422,
            "contract_validation_failed",
            "pass",
            0,
        ),
        ("CA3_timeout", allowed, base, 504, "upstream_timeout", "timeout", 1),
        ("CA3_upstream_failure", allowed, base, 503, "upstream_unavailable", "unavailable", 1),
        ("CA3_upstream_invalid", allowed, base, 502, "upstream_invalid", "invalid", 1),
        ("CA1_positive_control", demo, base, 200, None, "pass", 1),
    ]
    for name, key, body, status, code, mode, calls in scenarios:
        request(name, key, body, status, code, mode, calls)
    OUT["ended_at"] = now()
    collect_audit(OUT, check, os.environ["DATABASE_URL"])
    OUT["result"] = "passed" if not OUT["failures"] else "failed"
    OUT = emit_artifact(OUT, SECRETS)
    if OUT["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:
        # Do not print or serialize upstream exceptions, response bodies, or traces.
        OUT["result"] = "failed"
        OUT["failures"].append("runner_exception:" + type(error).__name__)
        OUT["ended_at"] = now()
        emit_artifact(OUT, SECRETS)
        raise SystemExit(1) from None
    finally:
        try:
            FAULT.post("/__mode", json={"mode": "pass"})
        except Exception:
            pass
