"""Minimal reproduction: identifiers of a triage declaration vs. the published schema patterns.

Runs inside the api container against http://127.0.0.1:8000. ADMIN_KEY comes from the
environment and is never printed. Output: sanitized JSON (ids, patterns, match flags).
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ADMIN = os.environ["ADMIN_KEY"]
STAMP = format(int(time.time()), "x")
WORKFLOW = {"resource_type": "incident_workflow", "resource_id": "incident-response"}


def call(method, path, key, body=None, idem=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


principal = f"idrepro-{STAMP}"
status, _ = call("POST", "/v1/principals", ADMIN,
                 {"principal_id": principal, "kind": "human", "display_name": "Id repro"},
                 f"idrepro-p-{STAMP}-000000")
assert status == 201, status
status, issued = call("POST", f"/v1/principals/{principal}/credentials", ADMIN,
                      {"expires_at": "2031-01-01T00:00:00Z"}, f"idrepro-c-{STAMP}-000000")
assert status == 201, status
for index, action in enumerate(("incident.declare", "run.read")):
    status, _ = call("POST", "/v1/grants", ADMIN,
                     {"grant_id": f"grant-{principal}-{index}", "principal_id": principal,
                      "action": action, "resource": WORKFLOW, "effect": "allow"},
                     f"idrepro-g{index}-{STAMP}-00000")
    assert status == 201, status
key = issued["key"]

alert_id = f"al-idrepro-{STAMP}"
status, declared = call("POST", f"/v1/alerts/{alert_id}/triage/commands", key, {
    "operation": "triage_declare", "expected_version": 1,
    "reason": "Reproduce the identifier format of a triage declaration.",
    "severity": "sev3", "impact": "None: synthetic reproduction.",
    "alert_context": {"service": "checkout", "summary": "Synthetic alert for the id reproduction.",
                      "observed_at": "2026-10-28T12:00:00Z", "source": "manual reproduction",
                      "severity": "sev3"},
}, f"idrepro-d-{STAMP}-000000")
incident_id = declared["incident_id"]
_, timeline = call("GET", f"/v1/incidents/{incident_id}/timeline", key)
_, snapshot = call("GET", f"/v1/incidents/{incident_id}/snapshot", key)

EVENT = r"^evt_[a-z0-9]{8,32}$"   # agent/schemas/run-event.schema.yaml
SNAP = r"^snap_[a-z0-9]{8,32}$"   # agent/schemas/incident-snapshot.schema.yaml
events = [event["event_id"] for event in timeline["events"]]
snapshot_id = (snapshot or {}).get("snapshot_id")
print(json.dumps({
    "sanitized": True,
    "declare_status": status,
    "incident_id": incident_id,
    "event_ids": [{"value": value, "pattern": EVENT, "matches": bool(re.fullmatch(EVENT, value))}
                  for value in events],
    "snapshot_id": {"value": snapshot_id, "pattern": SNAP,
                    "matches": bool(snapshot_id and re.fullmatch(SNAP, snapshot_id))},
}, indent=2))
