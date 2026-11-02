#!/usr/bin/env python3
"""Measure one real investigation of the seeded `triage-agent` model (#880).

Runs inside compose.evidence-verdict-e2e.yaml's `verdict-e2e` service, whose API keeps the
gateway's real OpenRouter provider when E2E_REAL_MODEL=1 and scripts Grafana MCP. It writes an
`active` incident, investigates it once over HTTP as the demo operator and records the total
time, then reads each model call's latency, tokens and billed cost from the gateway's audit rows
and its credited model and provider from /v1/usage/requests, as the admin. Appends one record to
$ARTIFACT_DIR/measurements.jsonl; never retries.
"""

import asyncio
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

API, HUMAN = os.environ["API_URL"], os.environ["DEMO_HUMAN_API_KEY"]
ADMIN = os.environ["ADMIN_HUMAN_API_KEY"]
STAMP, NOW = secrets.token_hex(4), datetime.now(UTC).isoformat()
CALLS = sa.text(
    "SELECT correlation ->> 'request_id' AS request_id, stage, outcome, reason_code,"
    " response_status, latency_ms, consumption"
    " FROM audit_events WHERE operation = 'responses.create'"
    " AND correlation ->> 'request_id' = ANY(:ids) ORDER BY occurred_at"
)


def call(method: str, path: str, body: object = None, timeout: float = 30, key: str = HUMAN):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers["Idempotency-Key"] = f"e2e-880-{STAMP}-{secrets.token_hex(8)}"
    data = None if body is None else json.dumps(body).encode()
    try:
        request = urllib.request.Request(API + path, data, headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def action(turn: dict) -> dict:
    """The action a turn's output asked for, without the output itself."""
    try:
        reply = json.loads(turn.get("model_output") or "")
    except json.JSONDecodeError:
        reply = None
    name = reply.get("action") if isinstance(reply, dict) else None
    tool = (turn.get("tool_invocation") or {}).get("tool")
    return {"sequence": turn["sequence"], "json_object": isinstance(reply, dict),
            "action": name, "tool": tool}  # fmt: skip


def credited(request_id: str) -> dict:
    """The model and provider the gateway credited for one call, as the admin reads them."""
    status, body = call("GET", f"/v1/usage/requests?request_id={request_id}", key=ADMIN)
    item = (body or {}).get("items", [{}])[0] if status == 200 else {}
    return {"credited_model": item.get("credited_model"),
            "credited_provider": item.get("credited_provider")}  # fmt: skip


async def main() -> int:
    incident = f"inc-e2e880-{STAMP}"
    alert = {"alert_id": f"alt-{incident}", "service": "checkout", "severity": "sev2",
             "status": "triaged", "observed_at": NOW, "source": "synthetic-e2e",
             "summary": "checkout no puede cobrar: llamadas a payment con error"}  # fmt: skip
    state = {"workflow_id": "incident-response", "workflow_version": "1.0.0", "state": "active",
             "incident_id": incident, "severity": "sev2", "alert": alert, "updated_at": NOW,
             "impact": "Los clientes no pueden pagar.", "evidence": []}  # fmt: skip
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(incident, state, now=datetime.now(UTC))
        run = {"workflow_version": "1.0.0", "objective": "investigate"}
        started_at = time.monotonic()
        status, started = call("POST", f"/v1/incidents/{incident}/runs", run, timeout=600)
        total_s = round(time.monotonic() - started_at, 1)
        run_id = started["run_id"]
        context = call("GET", f"/v1/incidents/{incident}/runs/{run_id}/context")[1]
        events = call("GET", f"/v1/incidents/{incident}/runs/{run_id}/events")[1]["events"]
        final = call("GET", f"/v1/incidents/{incident}")[1]["state"]
        receipts = [event for event in events if event["kind"] == "dispatch_receipt"]
        # A failed model call leaves no turn; its receipt still names the request.
        ids = [turn["request_id"] for turn in context["turns"] if turn.get("request_id")]
        ids += [event["request_id"] for event in receipts if event.get("request_id") not in ids]
        async with database.engine.connect() as connection:
            rows = (await connection.execute(CALLS, {"ids": ids})).mappings().all()
    finally:
        await database.dispose()
    calls = [{"latency_s": row["latency_ms"] / 1000, "stage": row["stage"],
              "outcome": row["outcome"], "reason_code": row["reason_code"],
              "status": row["response_status"],
              "consumption": row["consumption"], **credited(row["request_id"])}
             for row in rows]  # fmt: skip
    record = {
        "measured_at": NOW, "model": os.environ["MODEL"], "provider": os.environ["PROVIDER"],
        "start_status": status, "total_investigation_s": total_s, "incident_state": final,
        "turns": [action(turn) for turn in context["turns"]],
        "receipt": receipts[-1] if receipts else None,
        "hypotheses": [item.get("statement") for item in context["reasoning"]["hypotheses"]],
        "mitigation": context["reasoning"]["mitigation_strategy"],
        "calls": calls,
    }  # fmt: skip
    path = Path(os.environ.get("ARTIFACT_DIR", "/tmp")) / "measurements.jsonl"
    with path.open("a") as artifact:
        artifact.write(json.dumps(record, default=str) + "\n")
    print(json.dumps(record, default=str, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
