"""Grafana alert intake against the composed API with synthetic deliveries (#765).

scripts/run_real_journeys.sh runs it in the seed container after the other incident journeys,
with the API's ALERT_INTAKE_GRAFANA_SECRET and its operator demo-human. Each delivery has the
shape Grafana Alerting's webhook contact point sends, timed relative to now. Ways intake can fail,
each checked below:
1. a delivery without the right secret is accepted, reads the body, or leaves more than one audit
   event and no other trace;
2. a firing alert opens no incident, or its investigation is never dispatched;
3. the same delivery again opens a second incident or a second episode;
4. a second alert of a service with an open incident opens another incident, also after the
   first episode resolved (a flapping rule paying for a second investigation);
5. one grouped payload with alerts of two services opens one incident, or joins them to the
   first service's incident;
6. a `resolved` that arrives before its `firing` opens an incident, or the late `firing` reopens it;
7. an oversized body or too many alerts is accepted;
8. GET /v1/alerts lists a resolved episode as live, loses a triage decision or the mapped
   severity, or answers a caller without alert.read.
The artifact holds ids, statuses and counts, never a secret.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg

API = os.environ.get("API_URL", "http://api:8000")
INTAKE = f"{API}/v1/alert-intake/grafana"
SECRET = os.environ["ALERT_INTAKE_GRAFANA_SECRET"]
DATABASE = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
OUT = os.environ.get("ARTIFACT_DIR", "/artifacts")
RUN = uuid4().hex[:8]  # Fresh services per run, so a rerun on the same database starts clean.
# Relative to now: GET /v1/alerts keeps an episode resolved only within the last day.
NOW = datetime.now(UTC).replace(microsecond=0)
checks: list[dict] = []


def ago(minutes: int) -> str:
    return (NOW - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def http(method: str, url: str, body: bytes | None = None, key: str | None = None) -> tuple:
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, body, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def alert(service: str, status: str, starts: str, rule: str = "service-error-rate") -> dict:
    return {
        "status": status,
        "labels": {"alertname": rule, "service_name": service, "severity": "critical"},
        "annotations": {"summary": f"{service}: spans failing over the last 2 min."},
        "startsAt": starts,
        "endsAt": ago(1) if status == "resolved" else "0001-01-01T00:00:00Z",
        "fingerprint": f"{rule}-{service}",
    }


def deliver(*alerts: dict, key: str = SECRET) -> tuple:
    payload = {"receiver": "midnight-intake", "groupKey": f"journey-{RUN}", "alerts": list(alerts)}
    return http("POST", INTAKE, json.dumps(payload).encode(), key)


def sql(query: str, *params: object) -> list[tuple]:
    with psycopg.connect(DATABASE) as connection:
        return connection.execute(query, params).fetchall()


def episode(service: str) -> tuple:
    return sql(
        "SELECT episode_id, status, received_count, incident_id, investigation_run_id"
        " FROM incident.alert_episodes WHERE service = %s ORDER BY first_received_at",
        service,
    )


def incidents() -> int:
    return sql("SELECT count(*) FROM incident.incidents")[0][0]


def audits() -> int:
    return sql(
        "SELECT count(*) FROM audit_events WHERE operation = 'credentials.authenticate'"
        " AND response_status = 401"
    )[0][0]


def check(name: str, passed: bool, **facts: object) -> None:
    checks.append({"check": name, "pass": bool(passed), **facts})
    print(f"{'PASS' if passed else 'FAIL'} {name} {json.dumps(facts, default=str)}", flush=True)


def dispatched(run_id: str) -> bool:
    until = time.monotonic() + 60
    while time.monotonic() < until:
        rows = sql(
            "SELECT count(*) FROM incident.run_events WHERE run_id = %s"
            " AND kind = 'dispatch_receipt' AND payload->'dispatch_receipt'->>'phase' = 'intent'",
            run_id,
        )
        if rows[0][0]:
            return True
        time.sleep(1)
    return False


def main() -> None:
    a, b, c, d = (f"{name}-{RUN}" for name in ("cart", "payment", "ad", "email"))

    before = (audits(), incidents())
    status, body = deliver(alert(a, "firing", ago(60)), key="not-the-secret")
    oversized = http("POST", INTAKE, b"{" + b" " * (600 * 1024) + b"}", "not-the-secret")[0]
    after = (audits(), incidents())
    check(
        "401 without the secret, one audit event per delivery, nothing recorded",
        status == 401
        and oversized == 401
        and after == (before[0] + 2, before[1])
        and not episode(a),
        status=status,
        oversized_status=oversized,
        audit_401=[before[0], after[0]],
        code=body["error"]["code"],
    )

    status, body = deliver(alert(a, "firing", ago(60)))
    [(first, state, count, incident, run)] = episode(a)
    check(
        "a firing alert declares an incident and dispatches its investigation",
        status == 200 and state == "firing" and incident and run and dispatched(run),
        episode=first,
        incident=incident,
        run=run,
    )

    total = incidents()
    status, _ = deliver(alert(a, "firing", ago(60)))
    [(_, _, count, again, _)] = episode(a)
    check(
        "the same delivery again opens nothing new",
        status == 200 and count == 2 and again == incident and incidents() == total,
        received_count=count,
        incidents=[total, incidents()],
    )

    status, _ = deliver(alert(a, "firing", ago(59), "service-latency-p95"))
    deliver(alert(a, "resolved", ago(60)))
    flap = deliver(alert(a, "firing", ago(55)))[0]
    rows = episode(a)
    check(
        "later alerts of the service join its open incident, also after the first resolved",
        status == flap == 200
        and len(rows) == 3
        and {row[3] for row in rows} == {incident}
        and incidents() == total
        and [row[1] for row in rows] == ["resolved", "firing", "firing"],
        episodes=[row[:4] for row in rows],
    )

    status, _ = deliver(alert(b, "firing", ago(58)), alert(c, "firing", ago(58)))
    [(_, _, _, for_b, _)], [(_, _, _, for_c, _)] = episode(b), episode(c)
    check(
        "one grouped payload opens one incident per service",
        status == 200 and for_b and for_c and len({for_b, for_c, incident}) == 3,
        incidents=[for_b, for_c],
    )

    total = incidents()
    early = deliver(alert(d, "resolved", ago(57)))[0]
    late = deliver(alert(d, "firing", ago(57)))[0]
    [(late_episode, state, count, opened, _)] = episode(d)
    check(
        "a resolved before its firing opens nothing and stays resolved",
        early == late == 200 and state == "resolved" and opened is None and incidents() == total,
        status=state,
        received_count=count,
    )

    many = deliver(*[alert(f"x{n}-{RUN}", "firing", ago(56)) for n in range(101)])[0]
    large = http("POST", INTAKE, b"{" + b" " * (600 * 1024) + b"}", SECRET)[0]
    check(
        "an oversized body or more than 100 alerts is refused",
        many == large == 413 and not episode(f"x0-{RUN}"),
        statuses=[many, large],
    )

    demo, restricted = os.environ["DEMO_HUMAN_API_KEY"], os.environ["RESTRICTED_HARNESS_API_KEY"]
    status, listed = http("GET", f"{API}/v1/alerts", key=demo)
    live = {item["alert_id"]: item for item in listed["alerts"]}
    resolved = {item["alert_id"] for item in listed["resolved"]}
    ours = [row for service in (a, b, c) for row in episode(service) if row[1] == "firing"]
    check(
        "GET /v1/alerts lists firing episodes live with their decision, resolved ones apart",
        status == 200
        and all(live[row[0]]["incident_id"] == row[3] for row in ours)
        and {live[row[0]]["triage_status"] for row in ours} == {"declared", "linked"}
        and {live[row[0]]["severity"] for row in ours} == {"sev1"}
        and first in resolved
        and late_episode in resolved
        and first not in live,
        live=sorted(row[0] for row in ours),
    )
    forbidden = http("GET", f"{API}/v1/alerts", key=restricted)
    anonymous = http("GET", f"{API}/v1/alerts")[0]
    check(
        "GET /v1/alerts refuses a caller without alert.read and an anonymous one",
        forbidden[0] == 403
        and forbidden[1]["error"]["code"] == "not_authorized"
        and anonymous == 401,
        statuses=[forbidden[0], anonymous],
    )

    passed = all(item["pass"] for item in checks)
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/alert-intake-journey.json", "w") as stream:
        json.dump({"run": RUN, "pass": passed, "checks": checks}, stream, indent=2, default=str)
    print("PASS" if passed else "FAIL", flush=True)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
