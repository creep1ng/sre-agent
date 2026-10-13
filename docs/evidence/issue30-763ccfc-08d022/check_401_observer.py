"""Supplemental mocked process checks, never integrated producer evidence."""

import copy
import json
import os
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

version = os.getenv("CHECK_CONTRACT_VERSION", "2.7.0")
fixture = Path(f"/candidate/schemas/releases/{version}/fixtures/positive")
event = json.loads(
    (fixture / f"audit.authentication.unresolved-401.positive.v{version}.fixture.json").read_text()
)["data"]
published_identity = next(
    json.loads(p.read_text())["data"]["identity"]
    for p in fixture.glob("*.json")
    if isinstance(json.loads(p.read_text()).get("data"), dict)
    and isinstance(json.loads(p.read_text())["data"].get("identity"), dict)
    and "credential_ref" in json.loads(p.read_text())["data"]["identity"]
    and "principal_ref" in json.loads(p.read_text())["data"]["identity"]
)
body = {
    "error": {"code": "authentication_failed", "message": "Authentication failed."},
    "request_id": event["correlation"]["request_id"],
    "retryable": False,
}
cases = {
    "fixture_only_valid": {},
    "fixture_only_partial_credential_identity": {
        "event": {"identity": {"credential_ref": published_identity["credential_ref"]}}
    },
    "attributed_unknown_credential_valid_schema": {
        "event": {
            "identity": {
                k: v
                for k, v in published_identity.items()
                if k in {"principal_ref", "principal_kind", "principal_status", "credential_ref"}
            }
        }
    },
    "missing_bearer_challenge": {"challenge": None},
    "wrong_bearer_challenge": {"challenge": "Basic"},
    "non_json_response": {"non_json": True},
    "missing_public_field": {"public_remove": "request_id"},
    "extra_public_field": {"public_extra": True},
    "wrong_http": {"status": 200},
    "wrong_error": {"error": "contract_validation_failed"},
    "tool_attempt": {"calls": 1},
    "forward_only": {"forwards": 1},
    "handshake": {"handshake": 1},
    "counter_reset": {"reset_epoch": 1},
    "wrong_retryability": {"retryable": True},
    "wrong_message": {"message": "Synthetic wrong message"},
    "wrong_audit_status": {"event": {"response_status": 403}},
    "wrong_audit_reason": {"event": {"reason_code": "contract_validation_failed"}},
    "missing_schema_field": {"remove": "ordinary_result"},
    "attributed_unknown_credential": {"event": {"identity": {}}},
    "unexpected_content": {"event": {"untrusted_input": {}}},
    "outside_window": {"outside": True},
    "fixture_only_sql_nulls": {"event": {"resource": None, "identity": None}},
    "wrong_stage": {"event": {"stage": "validation"}},
    "nested_explicit_null": {
        "event": {"correlation": {"request_id": body["request_id"], "trace_ref": None}}
    },
    "schema_extra": {"event": {"extra": "synthetic forbidden field"}},
    "wrong_correlation": {"event": {"correlation": {"request_id": "bad"}}},
    "missing": {"rows": 0},
    "duplicate": {"rows": 2},
}
sys.path.insert(0, str(Path(__file__).parent))
results = []
for name, change in cases.items():
    observed, public = copy.deepcopy(event), copy.deepcopy(body)
    observed.update(change.get("event", {}))
    if "remove" in change:
        observed.pop(change["remove"])
    observed["occurred_at"] = datetime.now(UTC).isoformat()
    public["error"]["code"] = change.get("error", "authentication_failed")
    public["error"]["message"] = change.get("message", "Authentication failed.")
    public["retryable"] = change.get("retryable", False)
    if "public_remove" in change:
        public.pop(change["public_remove"])
    if change.get("public_extra"):
        public["extra"] = "synthetic unknown field"
    counts = {"mcp_methods": {}, "upstream_attempts": 0, "reset_epoch": 0}
    after = {
        **counts,
        "mcp_methods": {
            "tools/call": change.get("calls", 0),
            "initialize": change.get("handshake", 0),
        },
        "reset_epoch": change.get("reset_epoch", 0),
    }
    forwards = iter([{}, {"tools/call": change.get("forwards", 0)}])
    client = Mock()
    snapshots = iter([counts, after])
    client.get.side_effect = lambda url, snapshots=snapshots, forwards=forwards: Mock(
        json=lambda: (
            {"info": {"x-sre-agent-contract-version": version}}
            if url.endswith("openapi.json")
            else next(snapshots)
            if url.endswith("__count")
            else {"forwarded_methods": next(forwards)}
        )
    )
    client.post.return_value = Mock(
        status_code=change.get("status", 401),
        json=lambda public=public: public,
        headers={"WWW-Authenticate": change["challenge"]}
        if change.get("challenge") is not None
        else ({} if "challenge" in change else {"WWW-Authenticate": "Bearer"}),
    )
    if change.get("non_json"):
        client.post.return_value.json = Mock(side_effect=ValueError("synthetic malformed JSON"))
    db = Mock()
    db.execute.side_effect = lambda query, params, observed=observed, change=change: Mock(
        fetchall=lambda: [
            (
                {
                    **observed,
                    "occurred_at": observed["occurred_at"] if change.get("outside") else params[1],
                },
            )
        ]
        * change.get("rows", 1),
        fetchone=lambda: (change.get("rows", 1),),
    )
    output = Path("/capture/401-reproduction.json")
    output.unlink(missing_ok=True)
    with patch("httpx.Client") as http, patch("psycopg.connect") as sql:
        http.return_value.__enter__.return_value = client
        sql.return_value.__enter__.return_value = db
        try:
            runpy.run_path(str(Path(__file__).with_name("reproduce_401.py")))
            code = 0
        except SystemExit as exc:
            code = exc.code
        except (ValueError, AssertionError):
            code = 1
    expected = 0 if name.startswith("fixture_only_") else 1
    results.append(
        {
            "case": name,
            "expected_exit": expected,
            "observed_exit": code,
            "artifact_written": output.is_file(),
        }
    )
Path("/capture/observer-process-checks.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps({"evidence_kind": "mock", "version": version, "cases": results}))
raise SystemExit(
    any(r["expected_exit"] != r["observed_exit"] or not r["artifact_written"] for r in results)
)
