#!/usr/bin/env python3
"""E2E for #719 (compose.provider-retry-e2e.yaml): real API, database and investigator.

Under an active consumption limit, with scripts/fake_openrouter.py as OpenRouter:
1. a 503 on the first model call is sent once more and the investigation completes;
2. a direct call answered [503, 200] holds exactly one reservation, settled once;
3. a second 503, a timeout, a 503 after 5 s or a 503 that reports usage is not retried;
4. a tool held past INVESTIGATOR_TOOL_TIMEOUT_SECONDS ends the run with `tool_timeout`.
Writes $ARTIFACT_DIR/issue-719-e2e.txt (default: a new temporary directory), exits 1 on failure.
"""

import asyncio
import json
import os
import secrets
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

API, FAKE = os.environ["API_URL"], os.environ["FAKE_OPENROUTER_URL"]
ADMIN, HUMAN, AGENT = (
    os.environ[f"{name}_API_KEY"] for name in ("ADMIN_HUMAN", "DEMO_HUMAN", "INCIDENT_HARNESS")
)
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
# A reservation shares its id with the request_id of the call it admitted; `once` is true when
# it was settled at exactly the usage audited for that call's 200.
RESERVATIONS = (
    "SELECT r.reservation_id AS id, r.state, r.settled_tokens AS tokens, a.response_status, "
    "r.state = 'settled' AND a.response_status = 200 AND r.settled_tokens = "
    "(a.consumption->>'total_tokens')::bigint AND r.settled_usd_cost = "
    "(a.consumption->>'billed_usd')::numeric AS once FROM consumption_reservations r "
    "LEFT JOIN audit_events a ON a.correlation->>'request_id' = r.reservation_id "
    "AND a.operation = 'responses.create' WHERE r.incident_id = :i ORDER BY r.created_at"
)
HI = {"model": "triage-agent", "input": "Hi"}
lines = [f"Issue #719 provider-503 and tool-timeout E2E, stamp {STAMP}"]
failed: list[str] = []


def call(method: str, path: str, key: str = "", body: object = None, base: str = API):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if method == "PUT" or path.endswith("/runs"):
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


def set_limits(tokens: int | None, usd: str | None) -> None:
    version = call("GET", "/v1/consumption-limits", ADMIN)[1]["version"]
    body = {"expected_version": version, "incident_token_limit": tokens, "monthly_usd_limit": usd}
    status, policy = call("PUT", "/v1/consumption-limits", ADMIN, body)
    check(f"limits set to tokens={tokens} usd={usd}", status == 200, policy)


def plan(responses: list[object]) -> int:
    call("POST", "/__plan", body={"responses": responses}, base=FAKE)
    return len(call("GET", "/__log", base=FAKE)[1])


def provider_answers(before: int) -> list[int]:
    log = call("GET", "/__log", base=FAKE)[1][before:]
    return [entry["status"] for entry in log if entry["path"] == "/api/v1/responses"]


async def rows(database: Database, statement: str, **parameters: str) -> list[dict]:
    async with database.sessions() as session:
        return [dict(row._mapping) for row in await session.execute(text(statement), parameters)]


async def incident(database: Database, name: str, evidence: bool) -> str:
    incident_id = f"inc-e2e719-{name}-{STAMP}"
    state = json.loads(INCIDENT) | {"incident_id": incident_id, "updated_at": NOW}
    state["alert"] |= {"alert_id": f"alt-e2e719-{name}-{STAMP}", "observed_at": NOW}
    state["evidence"] = [item | {"collected_at": NOW} for item in state["evidence"] if evidence]
    async with PostgresIncidentUnitOfWork(database) as work:
        await work.incidents.add(incident_id, state, now=datetime.now(UTC))
    return incident_id


async def investigate(database: Database, incident_id: str) -> tuple[str, dict]:
    run = {"workflow_version": "1.0.0", "objective": "investigate"}
    status, started = call("POST", f"/v1/incidents/{incident_id}/runs", HUMAN, run)
    check(f"{incident_id}: investigation run accepted", status == 201, status)
    statement = "SELECT payload FROM incident.run_events WHERE run_id = :r ORDER BY sequence"
    events = [row["payload"] for row in await rows(database, statement, r=started["run_id"])]
    receipts = [event["dispatch_receipt"] for event in events if "dispatch_receipt" in event]
    state = call("GET", f"/v1/incidents/{incident_id}", HUMAN)[1]["state"]
    return state, receipts[-1] if receipts else {}


async def main() -> int:
    database = Database(os.environ["DATABASE_URL"])
    try:
        set_limits(200_000, "100")
        incident_id = await incident(database, "retry", True)
        before = plan([503])
        state, receipt = await investigate(database, incident_id)
        answers = provider_answers(before)
        check("1. the first model call answered 503, then 200", answers[:2] == [503, 200], answers)
        check("1. the investigation completed and reached mitigating", state == "mitigating", state)
        check("1. its receipt is a success", receipt.get("status") == "success", receipt)
        reservations = await rows(database, RESERVATIONS, i=incident_id)
        check(
            "1. one reservation per answered call, each settled at its audited usage",
            len(reservations) == answers.count(200) and all(r["once"] for r in reservations),
            reservations,
        )

        incident_id = await incident(database, "direct", True)
        before = plan([503])
        status, reply = call("POST", "/v1/responses", AGENT, HI | {"incident_id": incident_id})
        answers = provider_answers(before)
        check("2. a direct call answered [503, 200] returns 200", status == 200, (answers, status))
        reservations = await rows(database, RESERVATIONS, i=incident_id)
        check(
            "2. it holds exactly one reservation, settled once at the 200's usage",
            [(r["id"], r["once"]) for r in reservations] == [(reply["request_id"], True)],
            reservations,
        )

        for name, planned, expected, reason, attempts in (
            ("3. a second 503", [503, 503], 503, "upstream_unavailable", [503, 503]),
            ("3. a provider timeout", ["slow"], 504, "upstream_failed", [200]),
            ("3. a 503 after 5 s", ["late503", 200], 503, "upstream_unavailable", [503]),
            ("3. a 503 reporting usage", ["charged503", 200], 503, "upstream_unavailable", [503]),
        ):
            before = plan(planned)
            status, reply = call("POST", "/v1/responses", AGENT, HI)
            check(f"{name} answers {expected}", status == expected, reply)
            audit = await rows(database, AUDIT, r=reply["request_id"])
            audited = [{"response_status": expected, "reason_code": reason}]
            check(f"{name} is audited as {reason}", audit == audited, audit)
            await asyncio.sleep(3)  # the slow answer lands after the gateway gave up
            answers = provider_answers(before)
            check(f"{name} reached the provider {attempts}", answers == attempts, answers)
            plan([])

        before = plan([])
        state, receipt = await investigate(database, await incident(database, "tool", False))
        await asyncio.sleep(4)  # the held tools/call is logged when the stand-in answers it
        log = call("GET", "/__log", base=FAKE)[1][before:]
        tool_calls = [entry for entry in log if entry.get("rpc") == "tools/call"]
        check("4. the investigator called the slow tool", bool(tool_calls), tool_calls)
        reason = receipt.get("reason_code")
        check("4. the run ends with reason_code tool_timeout", reason == "tool_timeout", receipt)
    finally:
        set_limits(None, None)
        await database.dispose()

    lines.append(f"{'FAIL' if failed else 'PASS'}: {len(lines) - 1} checks, {len(failed)} failed")
    directory = os.environ.get("ARTIFACT_DIR") or tempfile.mkdtemp(prefix="issue-719-")
    artifact = Path(directory) / "issue-719-e2e.txt"
    artifact.write_text("\n".join(lines) + "\n")
    print(lines[-1])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
