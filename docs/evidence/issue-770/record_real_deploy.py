"""Record the real sre-checkout deploy with the step's own script (#770 evidence).

Runs in the compose `seed` container: creates a change.write-only integration through the
admin API, then runs /action/record_change.py with the env action.yml would give it. The issued
key stays in this process; only the script's output is printed.
"""

import json
import os
import subprocess
import time
import urllib.request
import uuid

API = "http://api:8000"
WORKFLOW = {"resource_type": "incident_workflow", "resource_id": "incident-response"}
stamp = time.strftime("%Y%m%d%H%M%S")


def admin(path, body):
    request = urllib.request.Request(
        API + path,
        json.dumps(body).encode(),
        {
            "Authorization": "Bearer " + os.environ["ADMIN_HUMAN_API_KEY"],
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as reply:
        return json.load(reply)


integration = f"local-deploy-{stamp}"
admin(
    "/v1/principals",
    {"principal_id": integration, "kind": "agent", "display_name": "Local deploy"},
)
key = admin(f"/v1/principals/{integration}/credentials", {})["key"]
admin(
    "/v1/grants",
    {
        "grant_id": f"grant-{integration}",
        "principal_id": integration,
        "action": "change.write",
        "resource": WORKFLOW,
        "effect": "allow",
    },
)
print(f"integration {integration}: change.write only")

env = {
    "PATH": os.environ["PATH"],
    "MIDNIGHT_URL": API,
    "MIDNIGHT_API_KEY": key,
    "CHANGE_SOURCE": "local-deploy",
    "CHANGE_EXTERNAL_ID": f"demo_env/fail/sre-checkout/{stamp}/deploy",
    "CHANGE_SERVICE": "sre-checkout",
    "CHANGE_KIND": "deploy",
    "CHANGE_VERSION": os.environ["CHANGE_VERSION"],
    "CHANGE_COMMIT": os.environ["CHANGE_COMMIT"],
    "CHANGE_REF": os.environ.get("CHANGE_REF", ""),
    "CHANGE_AUTHOR": "local-operator",
}
for attempt in ("first send", "resend"):
    step = subprocess.run(
        ["python", "/action/record_change.py"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"{attempt}: {(step.stdout + step.stderr).strip()}")
