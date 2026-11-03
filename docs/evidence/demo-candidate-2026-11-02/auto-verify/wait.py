"""Wait until the agent's own verification (#723, `{run_id}-verify`) resolves INCIDENT_ID, with
no person recording `verification_passed`, then print the run's verification events. Exits 1
unless the agent itself moved the incident to resolved.
Runs inside the `api` container: `exec -T -e DEMO_HUMAN_API_KEY -e INCIDENT_ID api python -`."""

import json
import os
import time
import urllib.request

API, INCIDENT = "http://127.0.0.1:8000/v1", os.environ["INCIDENT_ID"]
AUTH = {"Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"]}
TIMEOUT = float(os.environ.get("WAIT_SECONDS") or 300)


def get(path):
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=AUTH)) as response:
        return json.loads(response.read())


started, state = time.monotonic(), None
while time.monotonic() - started < TIMEOUT:
    state = get(f"/incidents/{INCIDENT}")["state"]
    if state != "verifying":
        break
    time.sleep(2)
run_id = next(i for i in get("/incidents")["incidents"] if i["incident_id"] == INCIDENT)[
    "latest_run"
]["run_id"]
events = get(f"/incidents/{INCIDENT}/runs/{run_id}/events?limit=200")["events"]
verification = [
    {
        "at": event.get("occurred_at"),
        "kind": event.get("kind"),
        "summary": event.get("summary"),
        "state": event.get("state"),
        "actor": event.get("actor"),
    }
    for event in events
    if "erif" in (event.get("summary") or "")
]
try:
    reasoning = get(f"/incidents/{INCIDENT}/runs/{run_id}/context")["reasoning"]
except OSError:
    reasoning = {}
ran = (reasoning.get("mitigation_strategy") or {}).get("execution") or {}
# What the agent measured after the approval ran: the query and its window (#723).
after = [
    {"query": item.get("query"), "collected_at": item.get("collected_at")}
    for item in reasoning.get("evidence", [])
    if ran.get("executed_at") and (item.get("collected_at") or "") > ran["executed_at"]
]
waited = round(time.monotonic() - started, 1)
print(
    json.dumps(
        {
            "state": state,
            "waited_seconds": waited,
            "executed_at": ran.get("executed_at"),
            "measured_after": after,
            "verification_events": verification,
        }
    )
)
by_agent = [
    event
    for event in verification
    if event["summary"] == "Service verified stable." and event["actor"]["type"] == "agent"
]
raise SystemExit(0 if state == "resolved" and by_agent else 1)
