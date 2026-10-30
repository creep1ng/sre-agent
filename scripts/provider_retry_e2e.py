#!/usr/bin/env python3
"""E2E for #719 (compose.provider-retry-e2e.yaml): real API, database and investigator.

1. a provider 503 on the first model call is sent once more and the investigation completes;
2. a second 503 is not retried again; 3. an ambiguous provider timeout is not retried;
4. a tool held past INVESTIGATOR_TOOL_TIMEOUT_SECONDS ends the run with `tool_timeout`.
Writes $ARTIFACT_DIR/issue-719-e2e.txt and exits 1 if a check fails.
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

from sqlalchemy import text

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

API, STANDIN = os.environ["API_URL"], os.environ["STANDIN_URL"]
HUMAN, AGENT = os.environ["DEMO_HUMAN_API_KEY"], os.environ["INCIDENT_HARNESS_API_KEY"]
STAMP, NOW = secrets.token_hex(4), datetime.now(UTC).isoformat()
# One synthetic incident: `active`, with one fixture evidence item or none (the tool case).
INCIDENT = """{"workflow_id": "incident-response", "workflow_version": "1.0.0", "state": "active",
 "severity": "sev2", "impact": "Checkout requests failing.", "hypotheses": [],
 "mitigation_strategy": null, "postmortem": null, "approvals": [],
 "alert": {"service": "checkout", "severity": "sev2", "status": "triaged",
  "summary": "Elevated error rate on checkout.", "source": "synthetic-e2e"},
 "evidence": [{"evidence_id": "ev_error_rate", "source": "fixture", "tool": "query_prometheus",
  "datasource_uid": "webstore-metrics", "query": "sum(rate(http_requests_total[5m]))",
  "time_window": "5m", "summary": "Synthetic fixture: errors rose after the last release.",
  "request_id": null}]}"""
AUDIT = (
    "SELECT response_status, reason_code FROM audit_events WHERE operation = 'responses.create' "
    "AND correlation->>'request_id' = :r"
)
lines = [f"Issue #719 provider-503 and tool-timeout E2E, stamp {STAMP}"]
failed: list[str] = []


def call(method: str, path: str, key: str = "", body: object = None, base: str = API):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if path.endswith("/runs"):
        headers["Idempotency-Key"] = f"e2e-719-{STAMP}-{secrets.token_hex(8)}"
    data = None if body is None else json.dumps(body).encode()
    try:
        request = urllib.request.Request(base + path, data, headers, method=method)
        with urllib.request.urlopen(request, timeout=120) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def check(name: str, ok: bool, observed: object) -> None:
    line = f"{'PASS' if ok else 'FAIL'} {name}: {observed}"
    lines.append(line if len(line) <= 400 else line[:397] + "...")
    print(line)
    if not ok:
        failed.append(name)


def provider_answers(before: int) -> list[int]:
    log = call("GET", "/__log", base=STANDIN)[1][before:]
    return [entry["status"] for entry in log if entry["path"] == "/api/v1/responses"]


async def rows(database: Database, statement: str, **parameters: str) -> list[tuple]:
    async with database.sessions() as session:
        return [tuple(row) for row in await session.execute(text(statement), parameters)]


async def incident(database: Database, name: str, with_evidence: bool) -> str:
    incident_id = f"inc-e2e719-{name}-{STAMP}"
    state = json.loads(INCIDENT) | {"incident_id": incident_id, "updated_at": NOW}
    state["alert"] |= {"alert_id": f"alt-e2e719-{name}-{STAMP}", "observed_at": NOW}
    evidence = [item | {"collected_at": NOW} for item in state["evidence"] if with_evidence]
    state["evidence"] = evidence
    async with PostgresIncidentUnitOfWork(database) as work:
        await work.incidents.add(incident_id, state, now=datetime.now(UTC))
    return incident_id


async def investigate(database: Database, incident_id: str) -> tuple[str, dict]:
    run = {"workflow_version": "1.0.0", "objective": "investigate"}
    status, started = call("POST", f"/v1/incidents/{incident_id}/runs", HUMAN, run)
    check(f"{incident_id}: investigation run accepted", status == 201, status)
    statement = "SELECT payload FROM incident.run_events WHERE run_id = :r ORDER BY sequence"
    events = [row[0] for row in await rows(database, statement, r=started["run_id"])]
    receipts = [event["dispatch_receipt"] for event in events if "dispatch_receipt" in event]
    state = call("GET", f"/v1/incidents/{incident_id}", HUMAN)[1]["state"]
    return state, receipts[-1] if receipts else {}


async def main() -> int:
    database = Database(os.environ["DATABASE_URL"])
    try:
        before = len(call("GET", "/__log", base=STANDIN)[1])
        call("POST", "/__plan", body={"responses": [503]}, base=STANDIN)
        state, receipt = await investigate(database, await incident(database, "retry", True))
        answers = provider_answers(before)
        check("1. the first model call answered 503, then 200", answers[:2] == [503, 200], answers)
        check("1. the investigation completed and reached mitigating", state == "mitigating", state)
        check("1. its receipt is a success", receipt.get("status") == "success", receipt)

        body = {"model": "triage-agent", "input": "Hi"}
        for name, plan, expected, reason, attempts in (
            ("2. a second 503", [503, 503], 503, "upstream_unavailable", [503, 503]),
            ("3. a provider timeout", ["slow"], 504, "upstream_failed", [200]),
        ):
            before = len(call("GET", "/__log", base=STANDIN)[1])
            call("POST", "/__plan", body={"responses": plan}, base=STANDIN)
            status, reply = call("POST", "/v1/responses", AGENT, body)
            check(f"{name} answers {expected}", status == expected, reply)
            audit = await rows(database, AUDIT, r=reply["request_id"])
            check(f"{name} is audited as {reason}", audit == [(expected, reason)], audit)
            await asyncio.sleep(6)  # the slow answer lands after the gateway gave up
            answers = provider_answers(before)
            check(
                f"{name} reached the provider {len(attempts)} time(s)", answers == attempts, answers
            )

        before = len(call("GET", "/__log", base=STANDIN)[1])
        state, receipt = await investigate(database, await incident(database, "tool", False))
        log = call("GET", "/__log", base=STANDIN)[1][before:]
        tool_calls = [entry for entry in log if entry["path"] == "/mcp"]
        check("4. the investigator called the slow tool", bool(tool_calls), tool_calls)
        reason = receipt.get("reason_code")
        check("4. the run ends with reason_code tool_timeout", reason == "tool_timeout", receipt)
    finally:
        await database.dispose()

    lines.append(f"{'FAIL' if failed else 'PASS'}: {len(lines) - 1} checks")
    artifact = Path(os.environ.get("ARTIFACT_DIR", "/tmp")) / "issue-719-e2e.txt"
    artifact.write_text("\n".join(lines) + "\n")
    print(lines[-1])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
