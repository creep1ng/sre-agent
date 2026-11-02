"""Issue #704 against the running API (no TestClient): run start, 5 s bound, replay, missing grant.

Runs inside the api container against http://127.0.0.1:8000. DEMO_KEY and ADMIN_KEY come from
the environment and are never printed. Prints sanitized JSON only; exits 1 on a failed check.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
DEMO, ADMIN = os.environ["DEMO_KEY"], os.environ["ADMIN_KEY"]
STAMP = format(int(time.time() * 1000), "x")
WORKFLOW = {"resource_type": "incident_workflow", "resource_id": "incident-response"}
checks: dict[str, bool] = {}


def call(method, path, key, body=None, idem=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def declare(key, alert_id, idem):
    return call("POST", f"/v1/alerts/{alert_id}/triage/commands", key, {
        "operation": "triage_declare", "expected_version": 1,
        "reason": "Verify issue 704 against the running API.",
        "severity": "sev2", "impact": "Synthetic: customers cannot pay.",
        "alert_context": {"service": "checkout", "summary": "Synthetic checkout failure.",
                          "observed_at": "2026-10-28T12:00:00Z", "source": "issue-704 verification",
                          "severity": "sev2"},
    }, idem)


def runs(incident_id):
    status, detail = call("GET", f"/v1/incidents/{incident_id}", DEMO)
    assert status == 200, status
    return [{k: run[k] for k in ("run_id", "status", "current_state")} for run in detail["runs"]]


# 1. Granted declarant: the investigate run exists and is not pending within 5 s.
alert, key = f"al-v704-{STAMP}", f"v704-granted-{STAMP}-0000"
sent_at = time.monotonic()
status, first = declare(DEMO, alert, key)
accepted_ms = round((time.monotonic() - sent_at) * 1000)
checks["declare_201"] = status == 201
incident = first["incident_id"]
observed_ms, investigation = None, None
while time.monotonic() - sent_at < 5:
    investigation = next((r for r in runs(incident) if r["current_state"] == "investigating"), None)
    if investigation and investigation["status"] not in (None, "pending"):
        observed_ms = round((time.monotonic() - sent_at) * 1000)
        break
    time.sleep(0.1)
checks["run_not_pending_within_5s"] = observed_ms is not None
_, page = call("GET", f"/v1/incidents/{incident}/runs/{investigation['run_id']}/events", DEMO)
starts = [e for e in page["events"] if e["summary"] == "Investigation started."]
checks["one_start_as_declarant"] = (
    len(starts) == 1 and starts[0]["actor"]["reference"]["principal_id"] == "demo-human"
)
before = runs(incident)

# 2. Replay the same request with the same key: same answer, no second run, no second start.
replay_status, replay = declare(DEMO, alert, key)
status = replay_status
after = runs(incident)
_, page = call("GET", f"/v1/incidents/{incident}/runs/{investigation['run_id']}/events", DEMO)
checks["replay_same_body"] = status == 201 and replay == first
checks["replay_no_new_run"] = len(after) == len(before)
checks["replay_no_second_start"] = (
    len([e for e in page["events"] if e["summary"] == "Investigation started."]) == 1
)

# 3. A declarant without run.start: declared, no investigation run, timeline says why.
principal = f"v704-norun-{STAMP}"
post = lambda path, body, tag: call("POST", path, ADMIN, body, f"v704-{tag}-{STAMP}-000")  # noqa: E731
assert post("/v1/principals", {"principal_id": principal, "kind": "human",
                               "display_name": "No run.start"}, "p")[0] == 201
status, issued = post(f"/v1/principals/{principal}/credentials",
                      {"expires_at": "2031-01-01T00:00:00Z"}, "c")
assert status == 201, status
for index, action in enumerate(("incident.declare",)):
    assert post("/v1/grants", {"grant_id": f"grant-{principal}-{index}", "principal_id": principal,
                               "action": action, "resource": WORKFLOW, "effect": "allow"},
                f"g{index}")[0] == 201
status, blocked = declare(issued["key"], f"al-v704-norun-{STAMP}", f"v704-norun-{STAMP}-0000")
checks["no_grant_declare_201"] = status == 201
blocked_runs = runs(blocked["incident_id"])
checks["no_grant_no_investigation_run"] = not any(
    r["current_state"] == "investigating" for r in blocked_runs
)
_, timeline = call("GET", f"/v1/incidents/{blocked['incident_id']}/timeline", DEMO)
reasons = [e for e in timeline["events"] if e.get("reason_code") == "run_start_not_authorized"]
checks["no_grant_timeline_reason"] = len(reasons) == 1 and reasons[0]["summary"] == (
    "Investigation did not start: the declarant lacks the run.start grant."
)

print(json.dumps({
    "sanitized": True,
    "granted": {"alert_id": alert, "incident_id": incident, "accepted_ms": accepted_ms,
                "run_not_pending_after_ms": observed_ms, "investigation": investigation,
                "start_event_id": starts[0]["event_id"] if starts else None,
                "runs_before_replay": before, "runs_after_replay": after,
                "replay_status": replay_status, "replay_same_body": replay == first},
    "no_grant": {"incident_id": blocked["incident_id"], "runs": blocked_runs,
                 "timeline": [{k: e.get(k) for k in ("event_id", "kind", "summary", "reason_code")}
                              for e in timeline["events"]]},
    "checks": checks,
}, indent=2))
sys.exit(0 if all(checks.values()) else 1)
