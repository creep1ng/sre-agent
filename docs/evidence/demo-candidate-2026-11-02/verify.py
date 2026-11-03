"""Record `verification_passed` on INCIDENT_ID's latest run as demo-human, as a person would once
the alert resolved: nothing records it on Grafana's resolution yet (README.md, decisions).
Runs inside the `api` container: `exec -T -e DEMO_HUMAN_API_KEY -e INCIDENT_ID api python -`."""

import json
import os
import urllib.request

API, INCIDENT = "http://127.0.0.1:8000/v1", os.environ["INCIDENT_ID"]
AUTH = {"Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"]}


def call(path, body=None, key=None):
    headers = {**AUTH, "Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    data = None if body is None else json.dumps(body).encode()
    with urllib.request.urlopen(urllib.request.Request(API + path, data, headers)) as response:
        return response.status, json.loads(response.read())


detail = call(f"/incidents/{INCIDENT}")[1]
run_id = next(i for i in call("/incidents")[1]["incidents"] if i["incident_id"] == INCIDENT)[
    "latest_run"
]["run_id"]
status, body = call(
    f"/incidents/{INCIDENT}/runs/{run_id}/commands",
    {
        "command": "verification_passed",
        "actor": "human",
        "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
        "expected_incident_version": detail["version"],
    },
    f"verification_passed-{run_id}",
)
after = call(f"/incidents/{INCIDENT}")[1]
print(json.dumps({"status": status, "before": detail["state"], "after": after["state"]}))
