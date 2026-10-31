"""Issue #761 on the composed stack: an ended investigation names its reason and can be retried.

Runs inside the compose `seed` service against the real API (`http://api:8000`), on an `active`
incident that `seed_war_room_runs.py` created (INCIDENT). The default compose has no Grafana
MCP, so every investigation ends at MCP discovery. The script starts one, reads the run, starts
a retry on the same incident and reads it, then writes every status and body it saw to
ARTIFACT as JSON. It exits non-zero when a run stays `running` or the retry is refused.

With DEACTIVATE_HARNESS=1 (issue #705) the administrator sets the agent identity
`incident-harness` inactive for the first attempt and reactivates it before the retry, so the
first ending names the identity and the retry gets past it.

With REVOKE_GRANT=<grant id> (issue #788) the administrator revokes that grant before the first
attempt, so the run is denied: it must end with no pending command the API would refuse, and
the retry must still be accepted.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

BASE = os.environ.get("API_URL", "http://api:8000")
INCIDENT = os.environ["INCIDENT"]
ARTIFACT = os.environ.get("ARTIFACT", "/artifacts/investigation-retry.json")
HEADERS = {
    "Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"],
    "Content-Type": "application/json",
}


ADMIN = HEADERS | {"Authorization": "Bearer " + os.environ["ADMIN_HUMAN_API_KEY"]}


def call(
    method: str, path: str, body: Any = None, key: str | None = None, admin: bool = False
) -> dict[str, Any]:
    headers = (ADMIN if admin else HEADERS) | ({"Idempotency-Key": key} if key else {})
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:
            raw = reply.read()
            body = json.loads(raw) if raw else None
            return {"request": f"{method} {path}", "status": reply.status, "body": body}
    except urllib.error.HTTPError as error:
        return {"request": f"{method} {path}", "status": error.code, "body": json.load(error)}


def investigate(attempt: str) -> tuple[dict[str, Any], ...]:
    start = call(
        "POST",
        f"/v1/incidents/{INCIDENT}/runs",
        {"workflow_version": "1.0.0", "objective": "investigate"},
        key=f"e2e-investigation-retry-{INCIDENT}-{attempt}",
    )
    run_id = start["body"].get("run_id")
    if run_id is None:
        return (start,)
    run = call("GET", f"/v1/incidents/{INCIDENT}/runs/{run_id}")
    events = call("GET", f"/v1/incidents/{INCIDENT}/runs/{run_id}/events")
    return start, run, events


def set_harness(status: str) -> None:
    current = call("GET", "/v1/principals/incident-harness", admin=True)["body"]
    changed = call(
        "PUT",
        "/v1/principals/incident-harness/status",
        {"status": status, "expected_updated_at": current["updated_at"]},
        key=f"e2e-harness-{status}-{INCIDENT}",
        admin=True,
    )
    print(f"incident-harness -> {status}: HTTP {changed['status']}")
    if changed["status"] != 200:
        # A harness left inactive would fail every later investigation on the stack.
        raise SystemExit(f"FAIL: incident-harness -> {status} answered {changed['status']}")


def main() -> int:
    revoke = os.environ.get("REVOKE_GRANT")
    if revoke:
        revoked = call("DELETE", f"/v1/grants/{revoke}", admin=True)
        print(f"revoke {revoke}: HTTP {revoked['status']}")
    deactivate = os.environ.get("DEACTIVATE_HARNESS") == "1"
    if deactivate:
        set_harness("inactive")
    try:
        first = investigate("first")
    finally:
        if deactivate:
            set_harness("active")
    retry = investigate("retry")
    detail = call("GET", f"/v1/incidents/{INCIDENT}")
    transcript = {"incident_id": INCIDENT, "first": first, "retry": retry, "incident": detail}
    with open(ARTIFACT, "w", encoding="utf-8") as artifact:
        json.dump(transcript, artifact, indent=2)
    failures = []
    for name, steps in (("first", first), ("retry", retry)):
        print(f"{name}: POST runs -> HTTP {steps[0]['status']}")
        if steps[0]["status"] != 201:
            failures.append(f"{name} start answered {steps[0]['status']}")
            continue
        run = steps[1]["body"]
        print(
            f"  {run['run_id']}: status={run['status']} state={run['current_state']} "
            f"pending_command={run['pending_command']} terminated_reason={run['terminated_reason']}"
        )
        for event in steps[2]["body"]["events"]:
            reason = f" [reason_code={event['reason_code']}]" if event.get("reason_code") else ""
            print(f"    #{event['sequence']} {event['kind']}: {event['summary']}{reason}")
        if run["status"] == "running":
            failures.append(f"{name} run {run['run_id']} is still running")
        if run["pending_command"] not in (None, "approve_mitigation"):
            failures.append(
                f"{name} run announces '{run['pending_command']}', which the API defers"
            )
    print(
        f"incident {INCIDENT}: state={detail['body']['state']} runs="
        f"{[(r['run_id'], r['status']) for r in detail['body']['runs']]}"
    )
    print("FAIL: " + "; ".join(failures) if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
