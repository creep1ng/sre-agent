#!/usr/bin/env python3
"""The run's turns and the incident's timeline after the investigation of SERVICE ends (#724).
Prints one JSON record. Runs inside the `api` container, like scripts/flag_set_e2e.py:
    docker compose ... exec -T -e DEMO_HUMAN_API_KEY -e EXPECT=resolved api python - < trace.py

EXPECT=resolved: the incident resolves after the approved flag.set. EXPECT=needs_human: the run
ends asking for a person. Either way the run must hold a refusal, the BoK search and a query made
with the steps the refusal left, and stay inside its bound (6 steps plus at most 4 once).
"""

import json
import os
import sys
import time
import urllib.request

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
SERVICE = os.environ.get("SERVICE", "checkout")
EXPECT = os.environ.get("EXPECT", "resolved")
TIMEOUT = float(os.environ.get("FLOW_TIMEOUT_SECONDS", "600"))
BOUND = 6 + 4


def api(path):
    request = urllib.request.Request(
        API + path, headers={"Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"]}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def incident():
    found = [item for item in api("/v1/incidents")["incidents"] if item.get("service") == SERVICE]
    return found[0] if found else None


def ended(item):
    # After flag_set_e2e.py's `flow` the approval ran: the incident verifies or has resolved.
    if EXPECT == "resolved":
        return item and item["state"] in ("verifying", "resolved")
    return item and ((item.get("latest_run") or {}).get("status") or "running") != "running"


deadline = time.monotonic() + TIMEOUT
while not ended(item := incident()):
    if time.monotonic() > deadline:
        sys.exit(f"the investigation of {SERVICE} did not end within {TIMEOUT:.0f}s: {item}")
    time.sleep(2)

incident_id, run_id = item["incident_id"], item["latest_run"]["run_id"]
# A verification (#723) appends its turns to the run: keep the investigation's.
context = api(f"/v1/incidents/{incident_id}/runs/{run_id}/context")
turns = []
for turn in context["turns"]:
    lines = (turn.get("assembled_input") or "").splitlines()
    state = next(json.loads(line[7:]) for line in lines if line.startswith("State: "))
    if state["objective"] != "investigate":
        continue
    output = json.loads(turn.get("model_output") or "{}")
    call = turn.get("tool_invocation") or {}
    operation = (output.get("operation") or {}).get("parameters")
    turns.append(
        {
            "sequence": turn["sequence"],
            "steps_left": state["steps_left"],
            "action": output.get("action"),
            "detail": call.get("arguments", {}).get("query", call.get("arguments", {}).get("expr"))
            if call
            else operation or output.get("statement") or output.get("reason"),
            "tool": call.get("tool"),
            # What the runtime told the model about its previous reply, when it refused it.
            "told": next((line for line in lines if line.startswith("Your previous reply")), None),
            "refused_so_far": state.get("refused_mitigations"),
        }
    )
timeline = api(f"/v1/incidents/{incident_id}/timeline?limit=200")
KEPT = ("occurred_at", "kind", "type", "title", "summary")
events = [
    {key: event[key] for key in KEPT if key in event}
    for event in timeline.get("items", timeline.get("events", []))
]
refusals = [t for t in turns if t["told"] and "is already" in t["told"]]
checks = {
    "a proposal was refused as already at its value": bool(refusals),
    "the refusal told the model its next steps": all(
        "steps are left" in t["told"] for t in refusals
    ),
    "the steps after the refusal searched the BoK": any(
        t["tool"] == "bok.search" and t["sequence"] >= refusals[0]["sequence"] for t in turns
    )
    if refusals
    else False,
    f"the run stayed within {BOUND} steps": len(turns) <= BOUND,
    f"the incident ends as {EXPECT}": item["state"] in ("verifying", "resolved")
    if EXPECT == "resolved"
    else turns[-1]["action"] in ("propose_mitigation", "request_human")
    and item["latest_run"].get("status") != "completed",
}
print(
    json.dumps(
        {
            "incident_id": incident_id,
            "run_id": run_id,
            "state": item["state"],
            "run": item["latest_run"],
            "checks": checks,
            "turns": turns,
            "timeline": events,
        },
        indent=2,
        ensure_ascii=False,
    )
)
sys.exit(0 if all(checks.values()) else 1)
