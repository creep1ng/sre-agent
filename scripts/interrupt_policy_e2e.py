"""E2E phases of the interrupt policy (#771), driven by scripts/run_interrupt_policy_e2e.sh.

Runs in the seed container on the compose network. It sends deploys to POST /v1/changes as the
deploy-executor integration and Grafana's webhook deliveries to POST /v1/alert-intake/grafana,
plays the operator's chat through fake-telegram, queues digests with the gateway's CLI and reads
the decisions from GET /v1/event-decisions. Ways the policy can fail, each checked below:
1. a day without failures interrupts anyone, sends no digest or more than one message, or its
   digest miscounts «N eventos, M mensajes»;
2. a healthy deploy, a spike that recovers before its investigation ends and a broken deploy
   send more than one immediate message, or a message for anything but the broken deploy; the
   spike also proposes a rollback, so #767's decision message must follow the policy too, and
   the broken deploy's one message must be that decision, with its buttons;
3. the spike is missing from the digest, or the digest repeats the previous day;
4. an event ends without a decision, or a decision has no reason or a link that does not open
   its event;
5. the decisions answer a caller without alert.read;
6. a decision taken in the console, and the recovery after it, send a new message or count as
   an event instead of editing the decision message the operator already has;
7. a console link Telegram refuses as a button (a loopback host here) loses the message instead
   of travelling as text, or a time is not in the configured zone (Bogotá).
Appends every observation to /artifacts/interrupt-policy-e2e.json; any failed check exits 1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg

FAKE, API = "http://fake-telegram:8081", "http://api:8000"
ARTIFACT = Path("/artifacts/interrupt-policy-e2e.json")
OPERATOR = 222
READER = os.environ["DEMO_HUMAN_API_KEY"]
INTEGRATION = os.environ["DEPLOY_EXECUTOR_CHANGES_API_KEY"]
INTAKE_SECRET = os.environ["ALERT_INTAKE_GRAFANA_SECRET"]
# Set by scripts/run_interrupt_policy_e2e.sh: a loopback console the fake refuses as a button.
CONSOLE = os.environ["CONSOLE_PUBLIC_URL"].rstrip("/")


def http(method: str, path: str, body: Any = None, key: str | None = None) -> tuple[int, Any]:
    url = path if path.startswith("http") else API + path
    headers = {"Content-Type": "application/json"} | (
        {"Authorization": f"Bearer {key}"} if key else {}
    )
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:
            return reply.status, json.load(reply)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def sql(query: str, *args: Any) -> list[tuple]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        return connection.execute(query, args).fetchall()


def wait_for(probe, seconds: float = 60) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := probe():
            return value
        time.sleep(0.25)
    raise SystemExit(f"timed out after {seconds}s")


def sent() -> list[dict[str, Any]]:
    return [m for m in http("GET", f"{FAKE}/_test/sent")[1] if m["chat_id"] == OPERATOR]


def record(section: str, observed: Any, checks: dict[str, bool]) -> None:
    document = json.loads(ARTIFACT.read_text()) if ARTIFACT.exists() else {}
    document[section] = {"observed": observed, "checks": checks}
    ARTIFACT.write_text(json.dumps(document, indent=2, ensure_ascii=False, default=str))
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {section}: {name}")
    if not all(checks.values()):
        raise SystemExit(1)


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def deploy(service: str, version: str, at: datetime, kind: str = "deploy") -> None:
    change = {"source": "github-actions", "external_id": f"{service}-{version}-{kind}",
              "service": service, "kind": kind, "version": version,
              "occurred_at": iso(at)}  # fmt: skip
    status, body = http("POST", "/v1/changes", change, INTEGRATION)
    assert status == 201, (status, body)


def grafana(service: str, rule: str, status: str, starts_at: datetime, tag: str) -> None:
    alert = {
        "status": status,
        "fingerprint": f"{rule}-{service}",
        "startsAt": iso(starts_at),
        "endsAt": iso(datetime.now(UTC)) if status == "resolved" else "0001-01-01T00:00:00Z",
        "labels": {"alertname": rule, "service_name": service, "severity": "critical"},
        "annotations": {"summary": f"{tag} {service}: {rule} is {status}."},
    }
    body = {"groupKey": f"{rule}:{service}", "status": status, "alerts": [alert]}
    code, reply = http("POST", "/v1/alert-intake/grafana", body, INTAKE_SECRET)
    assert code == 200, (code, reply)


def digest() -> dict[str, Any]:
    """Queue a digest as the operator would, with the gateway's CLI, and wait for its message."""
    before = len(sent())
    output = subprocess.run(
        [sys.executable, "-m", "sre_agent.chat.telegram", "digest"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    message = wait_for(lambda: len(sent()) > before and sent()[-1])
    return {"cli": output, "text": message["text"]}


def decisions(since: datetime, key: str = READER) -> tuple[int, Any]:
    return http("GET", f"/v1/event-decisions?since={iso(since)}&limit=200", key=key)


def investigation(service: str) -> tuple[str, str] | None:
    rows = sql(
        "SELECT d.decision, d.rule FROM incident.event_decisions d JOIN incident.alert_episodes e"
        " ON e.incident_id = d.incident_id WHERE d.event_kind = 'investigation' AND e.service = %s",
        service,
    )
    return rows[0] if rows else None


def link(code: str) -> None:
    http("POST", f"{FAKE}/_test/messages", {"chat_id": OPERATOR, "text": f"/start {code}"})
    wait_for(lambda: sent())


def quiet_day() -> None:
    """Yesterday as it happened, compressed: three healthy deploys and a CI run, no alert."""
    started, yesterday = datetime.now(UTC), datetime.now(UTC) - timedelta(days=1)
    before = len(sent())
    deploy("catalog", "v41", yesterday.replace(hour=9))
    deploy("cart", "v17", yesterday.replace(hour=13))
    deploy("catalog", "v42", yesterday.replace(hour=16))
    deploy("frontend", "build-881", yesterday.replace(hour=18), kind="ci")
    sent_digest = digest()
    _, listed = decisions(started)
    messages = sent()[before:]
    record(
        "quiet_day",
        {"digest": sent_digest, "counts": listed["counts"], "messages": len(messages)},
        {
            "every event has a decision": listed["counts"]["events"] == 4,
            "zero interruptions": listed["counts"]["interrupt"] == 0,
            "one message, the digest": len(messages) == 1,
            "the digest counts 4 events and 0 messages": sent_digest["text"].startswith(
                "Resumen: 4 eventos, 0 mensajes."
            ),
        },
    )


def three_events() -> None:
    """A healthy deploy, a short spike that recovers by itself and the broken sre-checkout."""
    started = datetime.now(UTC)
    before = len(sent())
    deploy("catalog", "v43", started - timedelta(minutes=30))

    spike_at = datetime.now(UTC).replace(microsecond=0)
    # The spike also proposes a rollback: only the policy keeps its decision message quiet.
    spike_tag = "[e2e:spike] [e2e:broken]"
    grafana("cart", "cart-latency-p95", "firing", spike_at, spike_tag)
    wait_for(
        lambda: sql(
            "SELECT 1 FROM incident.alert_episodes e JOIN incident.run_events r"
            " ON r.run_id = e.investigation_run_id WHERE e.service = 'cart'"
            " AND r.kind = 'dispatch_receipt'"
        )
    )
    grafana("cart", "cart-latency-p95", "resolved", spike_at, spike_tag)
    spike = wait_for(lambda: investigation("cart"))

    deploy("sre-checkout", "v3", datetime.now(UTC) - timedelta(minutes=2))
    grafana("sre-checkout", "checkout-5xx-rate", "firing", datetime.now(UTC), "[e2e:broken]")
    broken = wait_for(lambda: investigation("sre-checkout"))
    immediate = wait_for(lambda: sent()[before:])
    time.sleep(3)  # nothing else may follow
    immediate = sent()[before:]
    sent_digest = digest()
    record(
        "three_events",
        {"spike": spike, "broken": broken, "immediate": immediate, "digest": sent_digest},
        {
            "the spike recovered before its result and goes to the digest": spike
            == ("digest", "recovered_before_result"),
            "the broken deploy interrupts: sustained impact, decision pending": broken
            == ("interrupt", "sustained_pending_decision"),
            "a single immediate message": len(immediate) == 1,
            "it is about the broken deploy": "sre-checkout" in immediate[0]["text"],
            "it is the decision message, with its buttons": bool(immediate[0]["buttons"]),
            "the refused link button travels as a text link": immediate[0]["text"].endswith(
                f"Ver incidente: {CONSOLE}/incidentes/{immediate[0]['text'].split()[3]}"
            )
            and all(
                not data.startswith("http") for row in immediate[0]["buttons"] for _, data in row
            ),
            "the digest counts 1 message": ", 1 mensaje." in sent_digest["text"],
            "the spike appears in the digest": "cart" in sent_digest["text"]
            and "Se recuperó sola" in sent_digest["text"],
            "the healthy deploy appears in the digest": "Despliegue v43 de catalog"
            in sent_digest["text"],
            "yesterday is not repeated": "v41" not in sent_digest["text"],
        },
    )


def edits() -> list[dict[str, Any]]:
    return [e for e in http("GET", f"{FAKE}/_test/answers")[1]["edits"] if e["chat_id"] == OPERATOR]


def run_command(incident_id: str, run_id: str, command: str) -> int:
    """A run command as the console sends it, as demo-human."""
    version = sql("SELECT version FROM incident.incidents WHERE incident_id = %s", incident_id)
    body = {"command": command, "actor": "human", "expected_incident_version": version[0][0]}
    body["actor_reference"] = {"reference_version": "1.0.0", "principal_id": "demo-human"}
    url = f"{API}/v1/incidents/{incident_id}/runs/{run_id}/commands"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {READER}"}
    headers["Idempotency-Key"] = f"policy-{command}-{run_id}"
    request = urllib.request.Request(url, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(request, timeout=60) as reply:
        return reply.status


def decided_in_console() -> None:
    """The broken deploy is approved in the console and recovers: its message is edited twice."""
    incident_id, run_id = sql(
        "SELECT incident_id, investigation_run_id FROM incident.alert_episodes"
        " WHERE service = 'sre-checkout'"
    )[0]
    messages, decisions_before = len(sent()), sql("SELECT count(*) FROM incident.event_decisions")

    def decision_message() -> dict[str, Any]:
        return next(m for m in sent() if m["text"].splitlines()[0].endswith(incident_id))

    approved = run_command(incident_id, run_id, "approve_mitigation")
    after_approval = wait_for(lambda: len(edits()) == 1 and decision_message())
    verified = run_command(incident_id, run_id, "verification_passed")
    wait_for(lambda: len(edits()) == 2)
    time.sleep(3)  # a new message would arrive by now
    message = decision_message()
    record(
        "decided_in_console",
        {"statuses": [approved, verified], "after_approval": after_approval}
        | {"message": message, "edits": edits()},
        {
            "the console approval edits the decision message": after_approval["buttons"] == []
            and "Aprobada por Demo" in after_approval["text"]
            and "desde la consola" in after_approval["text"],
            "the recovery edits it again, in Bogotá time, keeping the text link": message["text"]
            .splitlines()[-2]
            .startswith("Resuelto a las")
            and " UTC-5 · " in message["text"]
            and message["text"].splitlines()[-1].startswith("Ver incidente: "),
            "neither sends a new message": len(sent()) == messages,
            "neither is an event the policy decides": sql(
                "SELECT count(*) FROM incident.event_decisions"
            )
            == decisions_before,
        },
    )


def api() -> None:
    since = datetime.now(UTC) - timedelta(hours=1)  # both phases
    status, listed = decisions(since)
    opened = {
        d["link"]: (d["event_id"], http("GET", d["link"], key=READER)) for d in listed["decisions"]
    }
    # A link opens its event: 200, and the event's own id in what it returns.
    links = {
        link: s == 200 and event in json.dumps(body) for link, (event, (s, body)) in opened.items()
    }
    events = sql(
        "SELECT (SELECT count(*) FROM incident.alert_episodes)"
        " + (SELECT count(*) FROM incident.alert_episodes WHERE status = 'resolved')"
        " + (SELECT count(*) FROM incident.change_events)"
        " + (SELECT count(*) FROM incident.run_events WHERE kind = 'dispatch_receipt'"
        "    AND payload->'dispatch_receipt'->>'phase' = 'outcome')"
    )[0][0]
    total = sql("SELECT count(*) FROM incident.event_decisions")[0][0]
    denied = decisions(since, os.environ["RESTRICTED_HARNESS_API_KEY"])[0]
    Path("/artifacts/event-decisions.json").write_text(
        json.dumps(listed, indent=2, ensure_ascii=False)
    )
    record(
        "api",
        {"status": status, "counts": listed["counts"], "link_status": links, "denied": denied},
        {
            "every event recorded has exactly one decision": events == total,
            "every decision has a readable reason": all(
                len(d["reason"]) > 20 for d in listed["decisions"]
            ),
            "every decision links to its event, and the link opens it": bool(links)
            and all(links.values()),
            "a caller without alert.read is refused": denied == 403,
        },
    )


if __name__ == "__main__":
    phase, *arguments = sys.argv[1:]
    if phase == "link":
        link(*arguments)
    elif phase == "quiet_day":
        quiet_day()
    elif phase == "three_events":
        three_events()
        decided_in_console()
        api()
