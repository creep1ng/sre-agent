#!/usr/bin/env python3
"""E2E of flag.set (#724): the agent proposes the catalog operation, a person approves it, the
deploy-executor turns the fault flag off, and the alert resolves. Prints one JSON record.

Runs inside the `api` container, the executor's only caller (it signs with the api's own key):
    docker compose ... exec -T -e DEMO_HUMAN_API_KEY api python - checks < scripts/flag_set_e2e.py
    (inject the fault and make the rule fire)
    docker compose ... exec -T -e DEMO_HUMAN_API_KEY -e DECIDE=telegram api \\
        python - flow < scripts/flag_set_e2e.py

With FLAGD_ADDRESS=flagd:8013 (the local stand-in) `flow` also holds flagd's EventStream across the
approval and requires a reload without a restart.
`checks` proves the boundaries with nothing broken; `flow` waits for the incident of SERVICE
(default checkout), approves its proposal through the fake Bot API (DECIDE=telegram, needs the
telegram profile) or the API (DECIDE=api), then waits for the receipt, the flag and the alert.
"""

import http.client
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

from sre_agent.executor.signature import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

API = os.environ.get("API_URL", "http://127.0.0.1:8000")
EXECUTOR = "http://deploy-executor:8000"
TELEGRAM = "http://fake-telegram:8081/_test/"
SERVICE = os.environ.get("SERVICE", "checkout")
FLAG = os.environ.get("FLAG", "paymentUnreachable")
TIMEOUT = float(os.environ.get("FLOW_TIMEOUT_SECONDS", "600"))
# flagd itself, where the stack runs it (the local stand-in): host:port of its evaluation API.
FLAGD = os.environ.get("FLAGD_ADDRESS")
STARTED = time.monotonic()
record = {"started_at": datetime.now(UTC).isoformat(timespec="seconds"), "steps": []}


def call(url, body=None, headers=None, method=None):
    data = (
        None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    )
    request = urllib.request.Request(
        url, data, {"Content-Type": "application/json", **(headers or {})}, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=70) as response:
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
    print(json.dumps(record, indent=2, sort_keys=True))
    raise SystemExit(code)


def until(name, probe, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(2)
    step(name, False, reason=f"not within {timeout:.0f}s")


def signed(operation, payload, key):
    body = json.dumps(payload).encode()
    path, stamp = f"/v1/operations/{operation}", str(int(time.time()))
    signature = sign(
        os.environ["DEPLOY_EXECUTOR_SIGNING_KEY"].encode(), "POST", path, key, body, stamp
    )
    headers = {"Idempotency-Key": key, TIMESTAMP_HEADER: stamp, SIGNATURE_HEADER: signature}
    return call(EXECUTOR + path, body, headers)


def watch_flagd(events, stop):
    """Hold flagd's EventStream open, as the store's providers do, and record every event: a
    write must arrive as `configuration_change`, never as `provider_shutdown` or a broken stream."""
    host, port = FLAGD.split(":")
    connection = http.client.HTTPConnection(host, int(port), timeout=5)
    body = b"{}"
    connection.request(
        "POST",
        "/flagd.evaluation.v1.Service/EventStream",
        struct.pack(">BI", 0, len(body)) + body,
        {"Content-Type": "application/connect+json", "Connect-Protocol-Version": "1"},
    )
    response = connection.getresponse()
    while not stop.is_set():
        try:
            head = response.read(5)
        except TimeoutError:
            continue
        except OSError as error:
            events.append(f"broken: {type(error).__name__}")
            return
        if len(head) < 5:
            events.append("ended")
            return
        flags_byte, size = struct.unpack(">BI", head)
        events.append(json.loads(response.read(size) or b"{}").get("type") or "end")
        if flags_byte & 2:
            return


def served(flag):
    host, _ = FLAGD.split(":")
    body = call(f"http://{host}:8016/ofrep/v1/evaluate/flags/{flag}", {"context": {}})[1]
    return body.get("variant")


def flags():
    return call(f"{EXECUTOR}/v1/services/{SERVICE}")[1]["flags"]


def checks():
    try:
        socket.gethostbyname("otel-flags")
        reachable = True
    except OSError:
        reachable = False
    step(
        "the api cannot resolve the flag listener; only the executor's network has it",
        not reachable,
    )
    before = flags()
    step("the executor serves the EC2 catalog for the service", before.get(FLAG), flags=before)
    status, body = call(
        f"{EXECUTOR}/v1/operations/flag.set",
        {"service": SERVICE, "flag": FLAG, "variant": "off"},
        {"Idempotency-Key": "e2e-flag-unsigned-0001"},
    )
    step("an unsigned flag.set is refused", status == 401, status=status, body=body)
    stamp = datetime.now(UTC).strftime("%H%M%S")
    for flag, variant in ((FLAG, "on"), ("loadGeneratorTraffic", "off")):
        status, body = signed(
            "flag.set",
            {"service": SERVICE, "flag": flag, "variant": variant},
            f"e2e-{flag}-{stamp}",
        )
        step(
            f"flag.set {flag}={variant} is outside the catalog and refused",
            status == 422 and body["error"]["code"] == "flag_not_allowed",
            status=status,
            body=body,
        )
    step("no refused call changed a flag", flags() == before, flags=flags())
    finish()


def flow():
    incident = until(
        "an incident is declared for the service",
        lambda: next(
            (
                item
                for item in api("/v1/incidents")[1]["incidents"]
                if item.get("service") == SERVICE
            ),
            None,
        ),
    )
    incident_id = incident["incident_id"]
    step("incident declared from the alert", True, incident_id=incident_id)

    def strategy_of():
        item = next(
            i for i in api("/v1/incidents")[1]["incidents"] if i["incident_id"] == incident_id
        )
        run_id = (item.get("latest_run") or {}).get("run_id")
        if not run_id:
            return None
        context = api(f"/v1/incidents/{incident_id}/runs/{run_id}/context")[1] or {}
        strategy = (context.get("reasoning") or {}).get("mitigation_strategy") or {}
        return (item, run_id, strategy) if strategy.get("operation") else None

    item, run_id, strategy = until("the investigation proposes a catalog operation", strategy_of)
    step(
        "the proposal names the catalog operation",
        strategy["operation"]["operation"] == "flag.set"
        and strategy["operation"]["parameters"] == {"flag": FLAG, "variant": "off"},
        state=item["state"],
        operation=strategy["operation"],
        description=strategy.get("description"),
        execution_mode=strategy.get("execution_mode"),
    )
    events, stop = [], threading.Event()
    if FLAGD:
        threading.Thread(target=watch_flagd, args=(events, stop), daemon=True).start()
        until("flagd's stream is open", lambda: "provider_ready" in events, 30)
        step(
            "flagd serves the fault before the approval", served(FLAG) != "off", flagd=served(FLAG)
        )
    if os.environ.get("DECIDE", "api") == "telegram":
        message = until(
            "the decision message reaches the chat",
            lambda: next(
                (m for m in reversed(call(TELEGRAM + "sent")[1]) if m.get("buttons")), None
            ),
        )
        data = next(d for row in message["buttons"] for label, d in row if label == "Aprobar")
        status, _ = call(
            TELEGRAM + "taps",
            {"chat_id": message["chat_id"], "message_id": message["message_id"], "data": data},
        )
        step("approved with one tap in Telegram", status == 200, text=message.get("text"))
    else:
        version = api(f"/v1/incidents/{incident_id}")[1]["version"]
        command = {  # the body the console sends
            "command": "approve_mitigation",
            "expected_incident_version": version,
            "actor": "human",
            "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
            "turn_id": None,
            "disposition": None,
            "comment": None,
            "authorization": {
                "action": "run.approve",
                "resource": {"type": "incident_workflow", "id": "incident-response"},
            },
        }
        status, body = api(
            f"/v1/incidents/{incident_id}/runs/{run_id}/commands", command, f"e2e-approve-{run_id}"
        )
        step("approved through the API", status in (200, 202), status=status, body=body)

    def executed():
        detail = api(f"/v1/incidents/{incident_id}")[1]
        mode = strategy_of()[2].get("execution_mode")
        return detail if detail["state"] == "verifying" and mode == "executed" else None

    detail = until("the approval runs the operation", executed, 120)
    executions = call(EXECUTOR + "/v1/executions")[1]["executions"]
    receipt = [e for e in executions if e.get("operation") == "flag.set"][-1]
    step(
        "the executor ran flag.set and the incident is verifying",
        receipt["outcome"] == "flag_set"
        and receipt["parameters"] == {"flag": FLAG, "variant": "off"},
        state=detail["state"],
        receipt=receipt,
    )
    step("the flag is off on the demo", flags()[FLAG]["variant"] == "off", flags=flags())
    if FLAGD:
        reloaded = time.monotonic()
        until("flagd serves the new variant", lambda: served(FLAG) == "off", 15)
        lag = round(time.monotonic() - reloaded, 1)
        until("flagd announces the change", lambda: "configuration_change" in events, 15)
        stop.set()
        step(
            "flagd reloaded without a restart: its stream stayed open",
            not any(e in ("provider_shutdown", "ended") or e.startswith("broken") for e in events),
            reload_seconds=lag,
            stream_events=events,
        )

    def resolved():
        # Only an episode that started with this fault: an earlier one may have resolved already.
        since = datetime.fromisoformat(record["started_at"]) - timedelta(minutes=1)
        alerts = api("/v1/alerts")[1] or {}
        return next(
            (
                a
                for a in alerts.get("resolved") or []
                if a.get("service") == SERVICE
                and datetime.fromisoformat(a["observed_at"].replace("Z", "+00:00")) >= since
            ),
            None,
        )

    alert = until("the alert resolves", resolved)
    step("the alert resolved", True, condition=alert["origin"]["condition"])
    timeline = api(f"/v1/incidents/{incident_id}/timeline")[1]
    summaries = [event.get("summary") for event in (timeline or {}).get("events", [])]
    step(
        "the timeline tells what ran",
        any("flag.set" in (s or "") for s in summaries),
        timeline=summaries,
    )
    finish()


if __name__ == "__main__":
    {"checks": checks, "flow": flow}[sys.argv[1]]()
