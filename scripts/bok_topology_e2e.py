#!/usr/bin/env python3
"""E2E of the store-topology BoK collection (#718, compose.bok-topology-e2e.yaml).

With the demo grant, a checkout investigation searches otel-demo-store@1.0.0 and records
fragments naming checkout -> payment and the paymentFailure flag, each with its collection
version and chunk locator. With the collection's index down, the search fails and the run goes
on to a hypothesis. With the grant revoked, the next investigation runs without the collection
and the gateway denies and audits a direct search. Writes a report to $ARTIFACT_DIR; exits 1 on
a failure.
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

API, HUMAN = os.environ["API_URL"], os.environ["DEMO_HUMAN_API_KEY"]
ADMIN, AGENT = os.environ["ADMIN_HUMAN_API_KEY"], os.environ["INCIDENT_HARNESS_API_KEY"]
COLLECTION, GRANT = "otel-demo-store@1.0.0", "grant-setup-agent-otel-demo-store-1-0-0"
VERSION_PATH = "/v1/bok/collections/otel-demo-store/versions/1.0.0"
STAMP = secrets.token_hex(4)
AUDIT = (
    "SELECT outcome, response_status FROM audit_events "
    "WHERE operation = 'bok.search' AND occurred_at >= :since ORDER BY occurred_at"
)
RECEIPT = (
    "SELECT payload->'dispatch_receipt' FROM incident.run_events WHERE run_id = :run "
    "AND kind = 'dispatch_receipt' ORDER BY sequence DESC LIMIT 1"
)
OUTAGE = (
    "UPDATE bok_collection_versions SET status = :status WHERE collection_id = 'otel-demo-store'"
)
CHUNK = (
    "SELECT content FROM bok_section_chunks WHERE collection_id = 'otel-demo-store' "
    "AND version = '1.0.0' AND document_id = :document AND section_id = :section "
    "AND chunk_index = :index"
)
lines = [f"Store-topology BoK E2E, stamp {STAMP}"]
failed: list[str] = []
checks: list[str] = []
report: dict = {}


def call(method: str, path: str, key: str, body: object = None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers["Idempotency-Key"] = f"e2e-718-{STAMP}-{secrets.token_hex(8)}"
    data = None if body is None else json.dumps(body).encode()
    try:
        request = urllib.request.Request(API + path, data, headers, method=method)
        with urllib.request.urlopen(request, timeout=120) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def check(name: str, ok: bool, observed: object) -> None:
    lines.append(f"{'PASS' if ok else 'FAIL'} {name}: {observed}"[:600])
    print(lines[-1])
    checks.append(name)
    if not ok:
        failed.append(name)


def around(text_found: str, needle: str) -> str:
    """The matched substring with some context, as observed."""
    at = text_found.find(needle)
    return text_found[max(0, at - 40) : at + len(needle) + 40] if at >= 0 else "not found"


async def investigate(database: Database, label: str) -> tuple[dict, list, dict]:
    """Open a checkout incident, start its investigation and read its context, audit and
    outcome receipt."""
    now = datetime.now(UTC).isoformat()
    incident = f"inc-e2e-718-{label}-{STAMP}"
    alert = {"alert_id": f"alt-{incident}", "service": "checkout", "severity": "sev2",
             "status": "triaged", "observed_at": now, "source": "synthetic-e2e",
             "summary": "checkout no puede cobrar los pedidos"}  # fmt: skip
    state = {"workflow_id": "incident-response", "workflow_version": "1.0.0", "state": "active",
             "incident_id": incident, "severity": "sev2", "alert": alert, "updated_at": now,
             "impact": "Los clientes no pueden pagar.", "evidence": []}  # fmt: skip
    async with PostgresIncidentUnitOfWork(database) as work:
        await work.incidents.add(incident, state, now=datetime.now(UTC))
    since = datetime.now(UTC)
    body = {"workflow_version": "1.0.0", "objective": "investigate"}
    status, started = call("POST", f"/v1/incidents/{incident}/runs", HUMAN, body)
    check(f"{label}: investigation run accepted", status == 201, status)
    path = f"/v1/incidents/{incident}/runs/{started['run_id']}/context"
    status, context = call("GET", path, HUMAN)
    check(f"{label}: run context readable", status == 200, status)
    async with database.sessions() as session:
        audited = [tuple(row) for row in await session.execute(text(AUDIT), {"since": since})]
        receipt = await session.scalar(text(RECEIPT), {"run": started["run_id"]})
    report[label] = {"incident_id": incident, "context": context, "bok_search_audit": audited}
    report[label]["outcome_receipt"] = receipt
    check(f"{label}: run ended with a recorded receipt", bool(receipt), receipt)
    return context, audited, receipt or {}


def offered(context: dict) -> list:
    first = context["turns"][0]["assembled_input"]
    state = json.loads(first.rsplit("State: ", 1)[1].splitlines()[0])
    return state.get("authorized_bok_collections", [])


def hypotheses(context: dict) -> list:
    return [item["hypothesis_id"] for item in context["reasoning"]["hypotheses"]]


async def main() -> int:
    database = Database(os.environ["DATABASE_URL"])
    try:
        context, audited, receipt = await investigate(database, "granted")
        reasoning = context["reasoning"]
        searches = [
            turn["tool_invocation"]
            for turn in context["turns"]
            if (turn["tool_invocation"] or {}).get("tool") == "bok.search"
        ]
        check("granted: the run offers the collection", offered(context) == [COLLECTION],
              offered(context))  # fmt: skip
        receipt_offer = receipt.get("bok_collections")
        check("granted: the receipt lists it", receipt_offer == [COLLECTION], receipt_offer)
        check("granted: the investigator searched it", len(searches) == 1, searches)
        fragments = [item for item in reasoning["evidence"] if item["source"] == "bok"]
        check(
            "granted: every fragment carries the collection version",
            bool(fragments) and all(item["datasource_uid"] == COLLECTION for item in fragments),
            [item["datasource_uid"] for item in fragments],
        )
        prefix = VERSION_PATH + "/chunks/"
        check(
            "granted: every fragment carries its chunk locator",
            all(item["query"].startswith(prefix) for item in fragments),
            [item["query"] for item in fragments],
        )
        text_found = " ".join(item["summary"] for item in fragments)
        check(
            "granted: fragments name checkout -> payment",
            "checkout depends on payment" in text_found,
            around(text_found, "checkout depends on payment"),
        )
        check(
            "granted: fragments name paymentFailure",
            "paymentFailure" in text_found,
            around(text_found, "paymentFailure"),
        )
        hypothesis = (reasoning["hypotheses"] or [{}])[0]
        cited = {item["evidence_id"]: item["source"] for item in reasoning["evidence"]}
        sources = sorted(cited.get(ref, "?") for ref in hypothesis.get("supporting_evidence", []))
        check(
            "granted: the hypothesis cites a measurement besides the BoK",
            "bok" in sources and any(source != "bok" for source in sources),
            sources,
        )
        check("granted: the gateway audited the search", audited == [("success", 200)], audited)
        async with database.sessions() as session:
            for item in fragments:
                document, section, index = item["query"].removeprefix(prefix).split("/")
                stored = await session.scalar(text(CHUNK), {"document": document,
                                              "section": section, "index": int(index)})  # fmt: skip
                check(
                    f"granted: {document}/{section} is the stored chunk of version 1.0.0",
                    stored is not None and stored in item["summary"],
                    item["summary"][:160],
                )

        async with database.sessions() as session, session.begin():
            await session.execute(text(OUTAGE), {"status": "inactive"})
        try:
            context, audited, receipt = await investigate(database, "unavailable")
        finally:
            async with database.sessions() as session, session.begin():
                await session.execute(text(OUTAGE), {"status": "active"})
        searches = [turn["tool_invocation"] for turn in context["turns"]
                    if (turn["tool_invocation"] or {}).get("tool") == "bok.search"]  # fmt: skip
        results = [item["result_summary"] for item in searches]
        check(
            "unavailable: the model reads that the knowledge base is unavailable",
            results == [f"the knowledge base is unavailable: {COLLECTION} (index_unavailable)"],
            results,
        )
        found = hypotheses(context)
        check("unavailable: the investigation still records a hypothesis", bool(found), found)
        notes = receipt.get("notes")
        check("unavailable: the receipt notes it", notes == ["bok_unavailable"], notes)

        status, _ = call("DELETE", f"/v1/grants/{GRANT}", ADMIN)
        check("the administrator revokes the investigator's grant", status == 204, status)
        context, audited, receipt = await investigate(database, "revoked")
        check("revoked: the run no longer offers the collection", offered(context) == [],
              offered(context))  # fmt: skip
        receipt_offer = receipt.get("bok_collections")
        check("revoked: the receipt lists no collection", receipt_offer == [], receipt_offer)
        found = hypotheses(context)
        check("revoked: the investigation still records a hypothesis", bool(found), found)
        check("revoked: the run made no BoK search", audited == [], audited)
        since = datetime.now(UTC)
        status, body = call("POST", VERSION_PATH + "/search", AGENT, {"query": "checkout payment"})
        async with database.sessions() as session:
            denied = [tuple(row) for row in await session.execute(text(AUDIT), {"since": since})]
        check(
            "revoked: a direct search is denied",
            status == 403 and body["error"]["code"] == "resource_unavailable",
            status,
        )
        check("revoked: the gateway audited the denial", denied == [("denied", 403)], denied)
    finally:
        await database.dispose()

    lines.append(
        f"{'FAIL' if failed else 'PASS'}: {len(checks) - len(failed)}/{len(checks)} checks"
    )
    print(lines[-1])
    artifacts = Path(os.environ.get("ARTIFACT_DIR", "/tmp"))
    (artifacts / "bok-topology-e2e.txt").write_text("\n".join(lines) + "\n")
    (artifacts / "bok-topology-e2e.json").write_text(json.dumps(report, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
