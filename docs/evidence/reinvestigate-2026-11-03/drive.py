#!/usr/bin/env python3
"""E2E of the automatic re-investigation after a failed verification (#710). Prints one JSON record.
Runs inside the `api` container (run.sh), with DEMO_HUMAN_API_KEY and the fake Bot API linked:

SCENARIO=retry, on `checkout` with both payment flags on: the scripted model proposes
paymentFailure, the API approves it, the agent's verification fails (paymentUnreachable still
breaks checkout), a new run starts on its own, proposes paymentUnreachable, the approval runs it
and the verification resolves the incident.
SCENARIO=exhausted, on `sre-checkout` (no catalog: simulated rollbacks) with its alert firing:
three times a proposal is approved and a person says «Sigue fallando»; the first two start a new
run on their own, the third does not, and the chat says a person is needed.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
TELEGRAM = "http://fake-telegram:8081/_test/"
SCENARIO = os.environ.get("SCENARIO", "retry")
SERVICE = {"retry": "checkout", "exhausted": "sre-checkout"}[SCENARIO]
STARTED = time.monotonic()
record = {"scenario": SCENARIO, "steps": []}


def call(url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url, data, {"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw) if raw else None


def api(path, body=None, key=None):
    headers = {"Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"]}
    if key:
        headers["Idempotency-Key"] = key
    return call(API + path, body, headers)


def step(name, ok, **detail):
    elapsed = round(time.monotonic() - STARTED, 1)
    record["steps"].append({"step": name, "ok": bool(ok), "elapsed_s": elapsed, **detail})
    print(f"{elapsed:7.1f}s {'PASS' if ok else 'FAIL'} {name}", file=sys.stderr, flush=True)
    if not ok:
        finish(1)


def finish(code=0):
    if incident_id := record.get("incident_id"):
        record["timeline"] = sorted(
            (
                {"occurred_at": e["occurred_at"], "run_id": run_id, "actor": e["actor"]["type"]}
                | {"summary": e["summary"]}
                for run_id, _ in runs(incident_id)
                for e in events_of(incident_id, run_id)
            ),
            key=lambda e: e["occurred_at"],
        )
        record["chat"] = [text.splitlines()[0] for text in sent() if text]
    print(json.dumps(record, indent=2, ensure_ascii=False))
    raise SystemExit(code)


def until(name, probe, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := probe():
            return value
        time.sleep(2)
    step(name, False, reason=f"not within {timeout}s")


def incident():
    found = [i for i in api("/v1/incidents")[1]["incidents"] if i.get("service") == SERVICE]
    return found[0] if found else None


def events_of(incident_id, run_id):
    return api(f"/v1/incidents/{incident_id}/runs/{run_id}/events?limit=200")[1]["events"]


def runs(incident_id):
    """Each run of the incident with who started it."""
    listed = api(f"/v1/incidents/{incident_id}")[1]["runs"]
    return [
        (run["run_id"], events_of(incident_id, run["run_id"])[0]["actor"]["type"]) for run in listed
    ]


def command(incident_id, run_id, name, action):
    version = api(f"/v1/incidents/{incident_id}")[1]["version"]
    body = {  # the body the console sends
        "command": name,
        "expected_incident_version": version,
        "actor": "human",
        "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
        "turn_id": None,
        "disposition": None,
        "comment": None,
        "authorization": {
            "action": action,
            "resource": {"type": "incident_workflow", "id": "incident-response"},
        },
    }
    return api(f"/v1/incidents/{incident_id}/runs/{run_id}/commands", body, f"e2e-{name}-{run_id}")


def proposal(incident_id):
    """The pending proposal of the latest run, once the incident waits for a decision."""
    item = next(i for i in api("/v1/incidents")[1]["incidents"] if i["incident_id"] == incident_id)
    if item["state"] != "mitigating":
        return None
    run_id = item["latest_run"]["run_id"]
    context = api(f"/v1/incidents/{incident_id}/runs/{run_id}/context")[1] or {}
    strategy = (context.get("reasoning") or {}).get("mitigation_strategy") or {}
    return (run_id, strategy) if strategy else None


def sent():
    return [m.get("text") or "" for m in call(TELEGRAM + "sent")[1]]


item = until("an incident is declared from the alert", incident)
incident_id = item["incident_id"]
record["incident_id"] = incident_id
step("incident declared from the alert", True, incident_id=incident_id)
attempts = 3 if SCENARIO == "exhausted" else 2
for attempt in range(1, attempts + 1):
    run_id, strategy = until(
        f"proposal {attempt} waits for a decision", lambda: proposal(incident_id)
    )
    started = dict(runs(incident_id))[run_id]
    step(
        f"proposal {attempt} comes from a run started by "
        + ("the alert" if attempt == 1 else "the system after the failed verification"),
        started == "system",
        run_id=run_id,
        description=strategy.get("description"),
        operation=strategy.get("operation"),
    )
    before = {run for run, _ in runs(incident_id)}
    if attempt > 1:
        turns = api(f"/v1/incidents/{incident_id}/runs/{run_id}/context")[1]["turns"]
        state = next(
            json.loads(line[7:])
            for line in turns[0]["assembled_input"].splitlines()
            if line.startswith("State: ")
        )
        told = state.get("failed_mitigations") or []
        step(
            f"the run behind proposal {attempt} was told the {attempt - 1} failed attempt(s)",
            len(told) == attempt - 1,
            failed_mitigations=told,
        )
    status, body = command(incident_id, run_id, "approve_mitigation", "run.approve")
    step(f"proposal {attempt} approved through the API", status in (200, 202), status=status)
    if SCENARIO == "exhausted":
        until("the incident verifies", lambda: incident()["state"] == "verifying", 60)
        status, body = command(incident_id, run_id, "verification_failed", "run.command")
        step(f"a person says it still fails ({attempt} of 3)", status in (200, 202), status=status)
    elif attempt == 1:
        until("the agent's verification fails", lambda: incident()["state"] == "investigating", 240)
        step("the agent's verification failed: the incident is investigating again", True)
    if attempt <= 2 and not (SCENARIO == "retry" and attempt == 2):
        fresh = until(
            f"re-investigation {attempt} starts on its own",
            lambda known=before: [
                run for run, who in runs(incident_id) if run not in known and who == "system"
            ],
            60,
        )
        step(f"re-investigation {attempt} of 2 started by the system", True, run_id=fresh[0])
if SCENARIO == "retry":
    until("the incident resolves", lambda: incident()["state"] in ("resolved", "postmortem"), 240)
    step("the second proposal ran and the verification resolved the incident", True)
    # The model has no clock: each verification turn is told now and the seconds since the
    # execution, and the query it made fits inside them (2026-11-03 EC2 rehearsal).
    verifying = []
    for run_id, _ in runs(incident_id):
        context = api(f"/v1/incidents/{incident_id}/runs/{run_id}/context")[1] or {}
        for turn in context.get("turns", []):
            lines = (turn.get("assembled_input") or "").splitlines()
            state = next(json.loads(x[7:]) for x in lines if x.startswith("State: "))
            if state["objective"] == "verify":
                invoked = turn.get("tool_invocation") or {}
                expr = (invoked.get("arguments") or {}).get("expr")
                verifying.append(
                    {
                        "now": state.get("now"),
                        "executed_at": state["mitigation"]["execution"]["executed_at"],
                        "seconds_since_execution": state.get("seconds_since_execution"),
                        "expr": expr,
                    }
                )
    step(
        "every verification turn was told now and the seconds since the execution",
        verifying
        and all(v["now"] and isinstance(v["seconds_since_execution"], int) for v in verifying),
        turns=verifying,
    )
else:
    gave_up = until(
        "the chat says a person is needed",
        lambda: [text for text in sent() if text.startswith("Necesita a una persona")],
        60,
    )
    step("the chat says the agent stopped retrying", True, message=gave_up[0])
    time.sleep(15)
    latest = runs(incident_id)
    step(
        "no third re-investigation started",
        {run for run, _ in latest} == before and incident()["state"] == "investigating",
        runs=latest,
    )
finish()
