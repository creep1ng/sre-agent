#!/usr/bin/env python3
"""E2E for #707 (compose.evidence-verdict-e2e.yaml): each evidence carries a verdict.

Each scenario writes an `active` incident to the database, then investigates it over HTTP as
the demo operator. `metrics-and-logs`: Prometheus has data, the log query none, and the model
says both support it. `logs-only`: it cites only the empty log query, twice, so no hypothesis
is recorded (#760). `bok-and-logs`: the same with a runbook fragment already on the incident,
which is not measured data either. With E2E_REAL_MODEL=1 the gateway's real model runs
`metrics-and-logs` only, checked for what any model must respect. Writes a report and the
reasoning read back (for capture_evidence_verdict.mjs) to $ARTIFACT_DIR; exits 1 on a failure.
"""

import asyncio
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

API, HUMAN = os.environ["API_URL"], os.environ["DEMO_HUMAN_API_KEY"]
STAMP, NOW = secrets.token_hex(4), datetime.now(UTC).isoformat()
EMPTY = {"empty": True, "verdict": "inconclusive", "finding": "La consulta no devolvió datos."}
# What the scripted model says of the Prometheus answer.
FINDING = "checkout registra 12 llamadas con error y payment ninguna."
REJECTED = "Your previous reply was rejected: no cited evidence is measured data"
ENDED = "Investigation dispatch ended: no cited evidence had measured data."
# A runbook fragment a previous run found in the knowledge base: data from a document.
RUNBOOK = {"evidence_id": "ev_e2e760_runbook", "source": "bok", "tool": "bok.search",
           "datasource_uid": "runbooks@1.0.0", "query": "payment no responde", "collected_at": NOW,
           "summary": "Si payment no responde, reiniciarlo restablece los cobros."}  # fmt: skip
REAL = os.environ.get("E2E_REAL_MODEL") == "1"
VERDICTS = ("supports", "contradicts", "inconclusive")
lines = [f"Evidence-verdict E2E (#707), stamp {STAMP}"]
failed: list[str] = []


def call(method: str, path: str, body: object = None):
    headers = {"Authorization": f"Bearer {HUMAN}", "Content-Type": "application/json"}
    headers["Idempotency-Key"] = f"e2e-707-{STAMP}-{secrets.token_hex(8)}"
    data = None if body is None else json.dumps(body).encode()
    try:
        request = urllib.request.Request(API + path, data, headers, method=method)
        with urllib.request.urlopen(request, timeout=120) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def check(name: str, ok: bool, observed: object) -> None:
    lines.append(f"{'PASS' if ok else 'FAIL'} {name}: {observed}"[:400])
    print(lines[-1])
    if not ok:
        failed.append(name)


async def investigate(database: Database, scenario: str, evidence: tuple = ()) -> dict:
    incident = f"inc-e2e707-{scenario}-{STAMP}"
    alert = {"alert_id": f"alt-{incident}", "service": "checkout", "severity": "sev2",
             "status": "triaged", "observed_at": NOW, "source": "synthetic-e2e",
             "summary": f"checkout no puede cobrar [e2e:{scenario}]"}  # fmt: skip
    state = {"workflow_id": "incident-response", "workflow_version": "1.0.0", "state": "active",
             "incident_id": incident, "severity": "sev2", "alert": alert, "updated_at": NOW,
             "impact": "Los clientes no pueden pagar.", "evidence": list(evidence)}  # fmt: skip
    async with PostgresIncidentUnitOfWork(database) as work:
        await work.incidents.add(incident, state, now=datetime.now(UTC))
    run = {"workflow_version": "1.0.0", "objective": "investigate"}
    status, started = call("POST", f"/v1/incidents/{incident}/runs", run)
    check(f"{scenario}: investigation run accepted", status == 201, status)
    run_id = started["run_id"]
    found = call("GET", f"/v1/incidents/{incident}/runs/{run_id}/context")[1]
    state = call("GET", f"/v1/incidents/{incident}")[1]["state"]
    told = any(REJECTED in (turn.get("assembled_input") or "") for turn in found["turns"])
    events = call("GET", f"/v1/incidents/{incident}/runs/{run_id}/events")[1]["events"]
    ended = [event["summary"] for event in events if event["kind"] == "dispatch_receipt"][-1]
    reasoning = found["reasoning"]
    return {"incident": incident, "run_id": run_id, "state": state, "told": told,
            "ended": ended, **reasoning}  # fmt: skip


def verdict(found: dict, tool: str) -> dict:
    item = next((item for item in found["evidence"] if item.get("tool") == tool), {})
    return {key: item.get(key) for key in EMPTY}


def any_model(found: dict) -> None:
    evidence = {item["evidence_id"]: item for item in found["evidence"]}
    shown = [[item.get(key) for key in ("tool", *EMPTY)] for item in evidence.values()]
    judged = all(
        item.get("verdict") in VERDICTS and item.get("finding") for item in evidence.values()
    )
    check("every evidence has a verdict and a finding", bool(evidence) and judged, shown)
    empty = [item.get("verdict") for item in evidence.values() if item.get("empty")]
    check("every empty evidence is inconclusive", set(empty) <= {"inconclusive"}, empty)
    cited = found["hypotheses"][-1]["supporting_evidence"] if found["hypotheses"] else []
    with_data = [ref for ref in cited if not evidence.get(ref, {}).get("empty", True)]
    check("a hypothesis is recorded and cites evidence with data", bool(with_data), cited)


async def main() -> int:
    database = Database(os.environ["DATABASE_URL"])
    try:
        full = await investigate(database, "metrics-and-logs")
        logs_only = {} if REAL else await investigate(database, "logs-only")
        bok = {} if REAL else await investigate(database, "bok-and-logs", (RUNBOOK,))
    finally:
        await database.dispose()
    any_model(full)
    if REAL:
        return report(full, logs_only, bok)

    check("metrics-and-logs: reached mitigating", full["state"] == "mitigating", full["state"])
    cited = full["hypotheses"][-1]["supporting_evidence"] if full["hypotheses"] else []
    check("the hypothesis cites the metrics and the logs", len(cited) == 2, cited)
    shown = verdict(full, "query_prometheus")
    expected = {"empty": False, "verdict": "supports", "finding": FINDING}
    check("Prometheus with data arrives as supports, with its finding", shown == expected, shown)
    shown = verdict(full, "query_elasticsearch")
    check("the empty log query is inconclusive, not supports", shown == EMPTY, shown)
    for name, run in (("logs-only", logs_only), ("bok-and-logs", bok)):
        recorded, state = run["hypotheses"], run["state"]
        check(f"{name}: no hypothesis is recorded", not recorded, recorded)
        check(f"{name}: the incident stays investigating", state == "investigating", state)
        check(f"{name}: the model was told why on its retry", run["told"], run["told"])
        check(f"{name}: the receipt names the reason", run["ended"] == ENDED, run["ended"])
    return report(full, logs_only, bok)


def report(full: dict, logs_only: dict, bok: dict | None = None) -> int:
    lines.append(f"{'FAIL' if failed else 'PASS'}: {len(lines) - 1} lines")
    artifacts = Path(os.environ.get("ARTIFACT_DIR", "/tmp"))
    (artifacts / "evidence-verdict-e2e.txt").write_text("\n".join(lines) + "\n")
    runs = {"metrics-and-logs": full, "logs-only": logs_only, "bok-and-logs": bok or {}}
    runs = json.dumps(runs, indent=2)
    (artifacts / "evidence-verdict-e2e.json").write_text(runs + "\n")
    print(lines[-1])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
