"""E2E for Grafana alert intake (#765), run by compose.alert-intake.yaml against the real stack.

Grafana's contact point posts to this runner, which records each delivery and relays it
unchanged to POST /v1/alert-intake/grafana. Ways intake can fail, each checked below:
1. a firing alert reaches intake but opens no incident, or the incident starts no investigation;
2. the same delivery sent again opens a second incident or a second episode;
3. a delivery without the right secret is accepted, or leaves anything but an audit event;
4. `resolved` is not recorded on the episode;
5. the time from injection to the investigation's dispatch is not measured.
The operator injects and resets the failure from the host (the runner prints when). The artifact
holds ids, statuses and timings, never the secret. The EC2 store runs through the demo's own
wiring (docs/otel-demo-ec2.md); scripts/alert_intake_journey.py covers the paths a real Grafana
cannot be made to take on demand.
"""

import json
import os
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import psycopg

API = os.environ.get("API_URL", "http://api:8000")
CHECKOUT = os.environ.get("CHECKOUT_URL", "http://sre-checkout:8080")
DATABASE = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
DEMO_KEY = os.environ["DEMO_HUMAN_API_KEY"]
SECRET = os.environ["ALERT_INTAKE_GRAFANA_SECRET"]
SERVICE = "sre-checkout"
OUT = os.environ.get("ARTIFACT_DIR", "/artifacts")
INTAKE = f"{API}/v1/alert-intake/grafana"
deliveries: list[dict] = []
report: dict = {"service": SERVICE, "mode": "local-sre-checkout"}


def now() -> datetime:
    return datetime.now(UTC)


def say(message: str) -> None:
    print(f"{now().isoformat(timespec='seconds')} {message}", flush=True)


class Relay(BaseHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        authorization = self.headers.get("Authorization", "")
        received = now()
        answer = httpx.post(
            INTAKE,
            content=body,
            headers={"Authorization": authorization, "Content-Type": "application/json"},
            timeout=30,
        )
        alerts = json.loads(body).get("alerts", [])
        deliveries.append(
            {
                "received_at": received.isoformat(),
                "status": answer.status_code,
                "alerts": [
                    (a.get("labels", {}).get("service_name"), a.get("status")) for a in alerts
                ],
                "body": body,
                "authorization": authorization,
            }
        )
        say(f"delivery {answer.status_code}: {deliveries[-1]['alerts']}")
        self.send_response(answer.status_code)
        self.end_headers()


def sql(query: str, *params: object) -> list[tuple]:
    with psycopg.connect(DATABASE) as connection:
        return connection.execute(query, params).fetchall()


def wait(what: str, check, timeout: float, interval: float = 0.5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if result := check():
            return result
        time.sleep(interval)
    raise SystemExit(f"FAIL: timed out waiting for {what}")


def version() -> str | None:
    try:
        return httpx.get(CHECKOUT, timeout=2).json().get("version")
    except (httpx.HTTPError, ValueError):
        return None


def firing_delivery():
    return next(
        (
            d
            for d in deliveries
            if d["status"] == 200 and (SERVICE, "firing") in [tuple(a) for a in d["alerts"]]
        ),
        None,
    )


def episode() -> tuple | None:
    rows = sql(
        "SELECT episode_id, status, received_count, incident_id, investigation_run_id,"
        " first_received_at, resolved_at FROM incident.alert_episodes"
        " WHERE service = %s ORDER BY first_received_at DESC LIMIT 1",
        SERVICE,
    )
    return rows[0] if rows else None


def dispatched(run_id: str) -> datetime | None:
    rows = sql(
        "SELECT min(occurred_at) FROM incident.run_events WHERE run_id = %s"
        " AND kind = 'dispatch_receipt' AND payload->'dispatch_receipt'->>'phase' = 'intent'",
        run_id,
    )
    return rows[0][0]


def counts() -> dict:
    return {
        "incidents": sql("SELECT count(*) FROM incident.incidents")[0][0],
        "episodes": sql("SELECT count(*) FROM incident.alert_episodes")[0][0],
        "unauthenticated_audits": sql(
            "SELECT count(*) FROM audit_events WHERE operation = 'credentials.authenticate'"
            " AND response_status = 401"
        )[0][0],
    }


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8099), Relay)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report["before"] = counts()
    wait("sre-checkout 1.4.0", lambda: version() == "1.4.0", 300)
    say("READY: deploy the broken release now (DEMO_CHECKOUT_VERSION=1.5.0)")
    wait("sre-checkout 1.5.0", lambda: version() == "1.5.0", 900, 0.2)
    injected = now()
    say("injected")
    delivery = wait(f"a firing {SERVICE} delivery", firing_delivery, 900)
    first = wait("the incident intake opened", lambda: (e := episode()) and e[3] and e, 60)
    episode_id, _, _, incident_id, run_id, _, _ = first
    # An episode that joined another episode's incident starts no run of its own.
    run_id = (
        run_id
        or sql(
            "SELECT investigation_run_id FROM incident.alert_episodes"
            " WHERE incident_id = %s AND investigation_run_id IS NOT NULL",
            incident_id,
        )[0][0]
    )
    dispatched_at = wait("the investigation dispatch", lambda: dispatched(run_id), 60)
    alerts = httpx.get(
        f"{API}/v1/alerts", headers={"Authorization": f"Bearer {DEMO_KEY}"}, timeout=10
    ).json()["alerts"]
    listed = next(a for a in alerts if a["alert_id"] == episode_id)
    report["intake"] = {
        "injected_at": injected.isoformat(),
        "first_delivery_at": delivery["received_at"],
        "investigation_dispatched_at": dispatched_at.isoformat(),
        "injection_to_dispatch_seconds": round((dispatched_at - injected).total_seconds(), 1),
        "episode_id": episode_id,
        "incident_id": incident_id,
        "investigation_run_id": run_id,
        "inbox": {k: listed[k] for k in ("alert_id", "service", "triage_status", "incident_id")},
        "pass": listed["triage_status"] in {"declared", "linked"}
        and listed["incident_id"] == incident_id,
    }
    say(f"intake: {report['intake']}")

    before = counts()
    received = episode()[2]
    headers = {"Authorization": delivery["authorization"], "Content-Type": "application/json"}
    replay = httpx.post(INTAKE, content=delivery["body"], headers=headers, timeout=30)
    after = counts()
    report["replay"] = {
        "status": replay.status_code,
        "incidents_before": before["incidents"],
        "incidents_after": after["incidents"],
        "episodes_before": before["episodes"],
        "episodes_after": after["episodes"],
        "received_count_before": received,
        "received_count_after": episode()[2],
        "incident_after": episode()[3],
    }
    report["replay"]["pass"] = (
        replay.status_code == 200
        and after["incidents"] == before["incidents"]
        and after["episodes"] == before["episodes"]
        and episode()[3] == incident_id
    )
    say(f"replay: {report['replay']}")

    before, received = counts(), episode()[2]
    wrong = {
        "Authorization": "Bearer not-the-integration-secret",
        "Content-Type": "application/json",
    }
    rejected = httpx.post(INTAKE, content=delivery["body"], headers=wrong, timeout=30)
    after = counts()
    report["unauthenticated"] = {
        "status": rejected.status_code,
        "body": rejected.json(),
        "audit_events_401_before": before["unauthenticated_audits"],
        "audit_events_401_after": after["unauthenticated_audits"],
        "episodes_unchanged": after["episodes"] == before["episodes"] and episode()[2] == received,
        "incidents_unchanged": after["incidents"] == before["incidents"],
    }
    report["unauthenticated"]["pass"] = (
        rejected.status_code == 401
        and after["unauthenticated_audits"] == before["unauthenticated_audits"] + 1
        and report["unauthenticated"]["episodes_unchanged"]
        and report["unauthenticated"]["incidents_unchanged"]
    )
    say(f"unauthenticated: {report['unauthenticated']}")

    say("RESET: deploy the healthy release now (DEMO_CHECKOUT_VERSION=1.4.0)")
    closed = wait(
        "the resolved episode", lambda: (e := episode()) and e[1] == "resolved" and e, 600
    )
    report["resolved"] = {
        "episode_id": closed[0],
        "resolved_at": closed[6].isoformat(),
        "pass": closed[0] == episode_id,
    }
    say(f"resolved: {report['resolved']}")
    report["deliveries"] = [
        {k: d[k] for k in ("received_at", "status", "alerts")} for d in deliveries
    ]
    report["pass"] = all(
        report[k]["pass"] for k in ("intake", "replay", "unauthenticated", "resolved")
    )
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/alert-intake-e2e.json", "w") as stream:
        json.dump(report, stream, indent=2, default=str)
    say("PASS" if report["pass"] else "FAIL")
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
