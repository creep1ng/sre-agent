#!/usr/bin/env python3
"""E2E of the investigator timeout (compose.investigator-timeout-e2e.yaml).

The provider timeout is OPENROUTER_TIMEOUT_SECONDS=60 and the model answers after 50 s. The run
must wait for that answer: it completes, and its receipt carries the request id of the gateway
call that the audit log recorded and charged. Writes a report to $ARTIFACT_DIR; exits 1 on a
failure.
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

from sqlalchemy import text

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.settings import Settings

API, HUMAN = os.environ["API_URL"], os.environ["DEMO_HUMAN_API_KEY"]
STAMP, NOW = secrets.token_hex(4), datetime.now(UTC).isoformat()
AUDIT = (
    "SELECT response_status, correlation->>'request_id' AS request_id FROM audit_events "
    "WHERE operation = 'responses.create' AND occurred_at >= :since ORDER BY occurred_at"
)  # this stack runs only this investigation, and the incident id is stored as an HMAC ref
RECEIPT = (
    "SELECT payload->'dispatch_receipt' FROM incident.run_events "
    "WHERE run_id = :run AND kind = 'dispatch_receipt' ORDER BY sequence DESC LIMIT 1"
)
lines = [f"Investigator-timeout E2E, stamp {STAMP}"]
failed: list[str] = []


def call(method: str, path: str, body: object = None):
    headers = {"Authorization": f"Bearer {HUMAN}", "Content-Type": "application/json"}
    headers["Idempotency-Key"] = f"e2e-timeout-{STAMP}-{secrets.token_hex(8)}"
    data = None if body is None else json.dumps(body).encode()
    try:
        request = urllib.request.Request(API + path, data, headers, method=method)
        with urllib.request.urlopen(request, timeout=300) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def check(name: str, ok: bool, observed: object) -> None:
    lines.append(f"{'PASS' if ok else 'FAIL'} {name}: {observed}"[:400])
    print(lines[-1])
    if not ok:
        failed.append(name)


def timeout(provider: str, management_key: bool) -> float | None:
    environment = {"DATABASE_URL": "postgresql://unused", "OPENROUTER_TIMEOUT_SECONDS": provider}
    environment |= {"INVESTIGATOR_GATEWAY_URL": "http://api:8000", "INVESTIGATOR_MODEL_ALIAS":
                    "triage-agent", "INVESTIGATOR_GATEWAY_API_KEY": "unused"}  # fmt: skip
    if management_key:
        environment["OPENROUTER_MANAGEMENT_API_KEY"] = "unused"
    gateway = Settings.from_environment(environment).investigator_gateway
    return gateway.timeout_seconds if gateway else None


async def main() -> int:
    for provider, catalog, expected in (("60", False, 75), ("60", True, 135), ("120", True, 180)):
        found = timeout(provider, catalog)
        label = f"provider {provider} s{' with the endpoint catalog' if catalog else ''}"
        check(f"investigator timeout for {label} is {expected} s", found == expected, found)

    incident = f"inc-e2e-timeout-{STAMP}"
    alert = {"alert_id": f"alt-{incident}", "service": "checkout", "severity": "sev2",
             "status": "triaged", "observed_at": NOW, "source": "synthetic-e2e",
             "summary": "checkout no puede cobrar"}  # fmt: skip
    state = {"workflow_id": "incident-response", "workflow_version": "1.0.0", "state": "active",
             "incident_id": incident, "severity": "sev2", "alert": alert, "updated_at": NOW,
             "impact": "Los clientes no pueden pagar.", "evidence": []}  # fmt: skip
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(incident, state, now=datetime.now(UTC))
        since, started_at = datetime.now(UTC), time.monotonic()
        status, started = call(
            "POST",
            f"/v1/incidents/{incident}/runs",
            {"workflow_version": "1.0.0", "objective": "investigate"},
        )
        elapsed = time.monotonic() - started_at
        check("investigation run accepted", status == 201, status)
        lines.append(f"INFO run returned after {elapsed:.1f} s")
        print(lines[-1])
        run_id = started["run_id"]
        await asyncio.sleep(15)  # an abandoned call would still be writing its audit row
        async with database.sessions() as session:
            payload = (await session.execute(text(RECEIPT), {"run": run_id})).scalar_one()
            audited = (await session.execute(text(AUDIT), {"since": since})).all()
        lines.append(f"INFO receipt: {json.dumps(payload)}"[:1200])
        print(lines[-1])
    finally:
        await database.dispose()

    check("the run waited for the 50 s answer", elapsed >= 50, f"{elapsed:.1f} s")
    outcome = (payload.get("status"), payload.get("reason_code"))
    check("the receipt ends in success", outcome[0] == "success", outcome)
    rows = [(row.response_status, row.request_id) for row in audited]
    check("the gateway audited one completed model call", [r[0] for r in rows] == [200], rows)
    recorded = {str(item) for item in payload.get("request_ids", [])}
    check(
        "the receipt names the audited request id",
        bool(rows) and rows[0][1] in recorded,
        sorted(recorded),
    )
    lines.append(f"{'FAIL' if failed else 'PASS'}: {len(lines) - 1} lines")
    print(lines[-1])
    artifacts = Path(os.environ.get("ARTIFACT_DIR", "/tmp"))
    (artifacts / "investigator-timeout-e2e.txt").write_text("\n".join(lines) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
