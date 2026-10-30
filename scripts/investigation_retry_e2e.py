"""Issue #761 on the composed stack: an ended investigation names its reason and can be retried.

Runs inside the compose `seed` service against the real API (`http://api:8000`), on an `active`
incident that `seed_war_room_runs.py` created (INCIDENT). The default compose has no Grafana
MCP, so every investigation ends at MCP discovery. The script starts one, reads the run, starts
a retry on the same incident and reads it, then writes every status and body it saw to
ARTIFACT as JSON. It exits non-zero when a run stays `running` or the retry is refused.
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


def call(method: str, path: str, body: Any = None, key: str | None = None) -> dict[str, Any]:
    headers = HEADERS | ({"Idempotency-Key": key} if key else {})
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:
            return {"request": f"{method} {path}", "status": reply.status, "body": json.load(reply)}
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


def main() -> int:
    first = investigate("first")
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
            print(f"    #{event['sequence']} {event['kind']}: {event['summary']}")
        if run["status"] == "running":
            failures.append(f"{name} run {run['run_id']} is still running")
    print(
        f"incident {INCIDENT}: state={detail['body']['state']} runs="
        f"{[(r['run_id'], r['status']) for r in detail['body']['runs']]}"
    )
    print("FAIL: " + "; ".join(failures) if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
