#!/usr/bin/env python3
"""E2E for #758 (compose.consumption-e2e.yaml): an active limit admits calls under it only.

Real API, database and investigator, with scripts/fake_openrouter.py as OpenRouter, under a
200,000-token incident limit and a 100 USD monthly limit; each check() names one scenario. The
incident (state `active`, one fixture evidence item) is written to the database; everything else
goes through HTTP. Writes $ARTIFACT_DIR/issue-758-e2e.txt (default: a new temporary directory)
and exits 1 if a check fails. Without FAKE_OPENROUTER_URL the fake-log checks are skipped.
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

API, FAKE = os.environ["API_URL"], os.environ.get("FAKE_OPENROUTER_URL") or None
ADMIN, HUMAN, AGENT = (
    os.environ[f"{name}_API_KEY"] for name in ("ADMIN_HUMAN", "DEMO_HUMAN", "INCIDENT_HARNESS")
)
MODEL, STAMP = os.environ["TRIAGE_AGENT_MODEL"], secrets.token_hex(4)
PROVIDER = os.environ.get("TRIAGE_AGENT_PROVIDER", "")
INCIDENT_LIMIT, OVERHEAD = 200_000, 64  # OVERHEAD: tokens per message in text_input_bound
INCIDENT, NOW = f"inc-e2e758-{STAMP}", datetime.now(UTC).isoformat()
EVIDENCE = {
    "evidence_id": "ev_payment_error_rate",
    "source": "fixture",
    "tool": "query_prometheus",
    "datasource_uid": "webstore-metrics",
    "query": 'sum(rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m]))',
    "time_window": "5m",
    "summary": "Synthetic fixture: payment error calls rose after paymentFailure was enabled.",
    "collected_at": NOW,
    "request_id": None,
}
ALERT = {
    "alert_id": f"alt-e2e758-{STAMP}",
    "service": "paymentservice",
    "severity": "sev2",
    "status": "triaged",
    "observed_at": NOW,
    "summary": "Elevated error rate on paymentservice.",
    "source": "synthetic-e2e",
}
lines = [f"Issue #758 consumption-limit E2E, incident {INCIDENT}, model {MODEL}"]
checked: list[str] = []
failed: list[str] = []


def call(method: str, path: str, key: str = "", body: object = None, base: str = API):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if method == "PUT" or path.endswith("/runs"):
        headers["Idempotency-Key"] = f"e2e-758-{STAMP}-{secrets.token_hex(8)}"
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
    checked.append(name)
    if not ok:
        failed.append(name)


def set_limits(tokens: int | None, usd: str | None) -> None:
    version = call("GET", "/v1/consumption-limits", ADMIN)[1]["version"]
    body = {"expected_version": version, "incident_token_limit": tokens, "monthly_usd_limit": usd}
    status, policy = call("PUT", "/v1/consumption-limits", ADMIN, body)
    check(f"limits set to tokens={tokens} usd={usd}", status == 200, policy)


async def rows(database: Database, statement: str, **parameters) -> list[dict]:
    async with database.sessions() as session:
        return [dict(row._mapping) for row in await session.execute(text(statement), parameters)]


async def audit_reason(database: Database, request_id: str) -> object:
    found = await rows(
        database,
        "SELECT reason_code FROM audit_events WHERE operation = 'responses.create' "
        "AND correlation->>'request_id' = :r",
        r=request_id,
    )
    return found[0]["reason_code"] if found else None


def bound(text_input: str) -> int:
    return len(text_input.encode("utf-8")) + OVERHEAD


def fake_log() -> list[dict]:
    return call("GET", "/__log", base=FAKE)[1] if FAKE else []


def provider_limits() -> tuple[int, int] | None:
    """Return the worst completion cap and context window across the provider's endpoints."""
    if not FAKE:
        return None
    key = os.environ["FAKE_MANAGEMENT_KEY"]
    endpoints = call("GET", f"/api/v1/models/{MODEL}/endpoints", key, base=FAKE)[1]["data"]
    mine = [
        e
        for e in endpoints["endpoints"]
        if PROVIDER.casefold() in {e["provider_name"].casefold(), e["tag"].split("/")[0]}
    ]
    windows = [e["context_length"] for e in mine]
    caps = [e["max_completion_tokens"] or e["context_length"] for e in mine]
    lines.append(f"provider {PROVIDER}: {len(mine)} endpoints, window {windows}, caps {caps}")
    return min(caps), min(windows)


async def reserved_tokens(database: Database) -> int:
    found = await rows(
        database,
        "SELECT COALESCE(SUM(CASE WHEN state = 'settled' THEN settled_tokens "
        "ELSE token_exposure END), 0) AS used FROM consumption_reservations "
        "WHERE incident_id = :i",
        i=INCIDENT,
    )
    return int(found[0]["used"])


async def main() -> int:
    database = Database(os.environ["DATABASE_URL"])
    state = {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "active",
        "incident_id": INCIDENT,
        "severity": "sev2",
        "impact": "Checkout failing at payment.",
        "alert": ALERT,
        "hypotheses": [],
        "evidence": [EVIDENCE],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": NOW,
    }
    try:
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(INCIDENT, state, now=datetime.now(UTC))
        limits = provider_limits()

        set_limits(INCIDENT_LIMIT, "100")
        before = len(fake_log())
        run = {"workflow_version": "1.0.0", "objective": "investigate"}
        status, _ = call("POST", f"/v1/incidents/{INCIDENT}/runs", HUMAN, run)
        check("investigation run accepted", status == 201, status)
        reached = call("GET", f"/v1/incidents/{INCIDENT}", HUMAN)[1]["state"]
        check("incident reached mitigating under both limits", reached == "mitigating", reached)
        # A reservation shares its id with the request_id of the call it admitted.
        calls = await rows(
            database,
            "SELECT r.model, r.state, r.token_exposure, r.settled_usd_cost::text AS settled_usd, "
            "a.response_status, a.consumption->>'billed_usd' AS audited_usd "
            "FROM consumption_reservations r "
            "JOIN audit_events a ON a.correlation->>'request_id' = r.reservation_id "
            "AND a.operation = 'responses.create' WHERE r.incident_id = :i ORDER BY r.created_at",
            i=INCIDENT,
        )
        settled = bool(calls) and all(
            c["model"] == MODEL
            and c["state"] == "settled"
            and c["response_status"] == 200
            and float(c["settled_usd"]) == float(c["audited_usd"] or "nan")
            for c in calls
        )
        check("every model call was reserved, settled at its audited cost", settled, calls)
        if limits:
            sent = [e for e in fake_log()[before:] if e["method"] == "POST"]
            # Exposure = input bound + admitted output cap, so the cap sent must equal the rest.
            expected_caps = [
                c["token_exposure"] - e["prompt_bytes"] - OVERHEAD
                for c, e in zip(calls, sent, strict=False)
            ]
            caps = [e["max_output_tokens"] for e in sent]
            check(
                "each call sent max_output_tokens equal to its admitted cap",
                len(sent) == len(calls)
                and caps == expected_caps
                and all(e["status"] == 200 for e in sent),
                {"sent": caps, "admitted": expected_caps},
            )

        # Spend the incident's balance with maximal inputs until one no longer fits.
        large = "x" * 65_536
        body = {"model": "triage-agent", "input": large, "incident_id": INCIDENT}
        admitted_caps: list[tuple[int, object]] = []
        admitted = 0
        for _ in range(20):
            remaining = INCIDENT_LIMIT - await reserved_tokens(database)
            before = len(fake_log())
            status, reply = call("POST", "/v1/responses", AGENT, body)
            if status != 200:
                break
            admitted += 1
            if limits:
                expected = min(limits[0], limits[1] - bound(large), remaining - bound(large))
                sent = [
                    e["max_output_tokens"] for e in fake_log()[before:] if e["method"] == "POST"
                ]
                admitted_caps.append((expected, sent))
        check("calls on the incident were admitted until then", admitted > 0, admitted)
        if limits:
            matches = all([expected] == got for expected, got in admitted_caps)
            check(
                "each cap was the tightest of endpoint, window and incident balance",
                matches,
                admitted_caps,
            )
        code = (reply.get("error") or {}).get("code")
        check(
            "the call over the incident limit answers 429 consumption_limit_exceeded",
            (status, code) == (429, "consumption_limit_exceeded"),
            reply,
        )
        reason = await audit_reason(database, reply["request_id"])
        check(
            "the refusal is audited as incident_limit_exceeded",
            reason == "incident_limit_exceeded",
            reason,
        )
        check(
            "the incident balance could not cover the refused call's input bound",
            remaining <= bound(large),
            {"remaining": remaining, "input_bound": bound(large)},
        )
        if FAKE:
            posts = [e for e in fake_log()[before:] if e["method"] == "POST"]
            check("the refused call never reached the provider", not posts, posts)

        before = len(fake_log())
        set_limits(INCIDENT_LIMIT, "0")
        status, refused = call(
            "POST", "/v1/responses", AGENT, {"model": "triage-agent", "input": "Hi"}
        )
        code = (refused.get("error") or {}).get("code")
        over = (status, code) == (429, "consumption_limit_exceeded")
        check("at 0 USD a call answers 429 consumption_limit_exceeded", over, refused)
        reason = await audit_reason(database, refused["request_id"])
        check(
            "the refusal is audited as monthly_limit_exceeded",
            reason == "monthly_limit_exceeded",
            reason,
        )
        if FAKE:
            posts = [e for e in fake_log()[before:] if e["method"] == "POST"]
            check("the refused call never reached the provider", not posts, posts)

        set_limits(INCIDENT_LIMIT, "100")
        body = {"model": "triage-agent", "input": "Hi", "incident_id": f"inc-missing-{STAMP}"}
        status, unknown = call("POST", "/v1/responses", AGENT, body)
        code = (unknown.get("error") or {}).get("code")
        check(
            "an unknown incident_id answers 422 incident_not_found, not a 500 or 429",
            (status, code) == (422, "incident_not_found"),
            unknown,
        )
        reason = await audit_reason(database, unknown["request_id"])
        check("its audit names resource_not_found", reason == "resource_not_found", reason)

        if limits:
            # 65,536 three-byte characters: only the window minus the input leaves room.
            wide = "\u20ac" * 65_536
            set_limits(None, "100")
            before = len(fake_log())
            status, _ = call(
                "POST", "/v1/responses", AGENT, {"model": "triage-agent", "input": wide}
            )
            got = [e["max_output_tokens"] for e in fake_log()[before:] if e["method"] == "POST"]
            expected = min(limits[0], limits[1] - bound(wide))
            check(
                "a large multi-byte input gets an output cap that fits the context window",
                status == 200 and got == [expected],
                {"status": status, "sent": got, "window_minus_input": expected},
            )
            log = fake_log()
            paths = sorted({e["path"] for e in log if "/models/" in e["path"]})
            check(
                "the catalog was queried with the routed model, every call authenticated",
                paths == [f"/api/v1/models/{MODEL}/endpoints"]
                and all(e["status"] != 401 for e in log),
                paths,
            )
    finally:
        set_limits(None, None)
        await database.dispose()

    lines.append(f"{'FAIL' if failed else 'PASS'}: {len(checked)} checks, {len(failed)} failed")
    directory = os.environ.get("ARTIFACT_DIR") or tempfile.mkdtemp(prefix="issue-758-")
    artifact = Path(directory) / "issue-758-e2e.txt"
    artifact.write_text("\n".join(lines) + "\n")
    print(lines[-1])
    print(f"Summary: {artifact}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
