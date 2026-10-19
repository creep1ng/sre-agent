"""run-command:2.1.0 over HTTP against real PostgreSQL (#41 CA3/CA4, #43 CA8).

Written from the ways verifying and closing could fail before the route knew
these commands:

1. A command maps to the wrong edge: `stable` returns to investigating, or
   `not_stable` resolves the incident.
2. A closure moves to closed without a postmortem, or the guard rejects it but
   the version, a decision or an event is still written.
3. A closure is accepted without the explicit approval assertion, or under the
   `run.command` action, so asking for something replaces approving it.
4. An identity holding only `run.command` closes the incident.
5. An agent credential issues a human command, by grant or by naming a human.
6. A replayed Idempotency-Key writes a second event or re-evaluates the state.
7. A stale `expected_incident_version` overwrites a newer incident, or a
   versionless verification/closure is accepted as a blind write.
8. A guard rejection is indistinguishable from a state conflict.
9. The 2.0.0 release is edited in place, breaking clients pinned to it.

Case 9 lives in scripts/validate_run_api.py. Principals and grants come from
the #330 suite: demo-human holds run.command and run.approve, sender-human only
run.command, approving-harness is an agent holding run.approve.
"""

import asyncio
import uuid

import psycopg
import yaml
from test_incident_command_http import (  # noqa: F401  (module fixture)
    DATABASE_URL,
    INITIAL_STATE_PATH,
    MITIGATION,
    NOW,
    RUNS,
    _body,
    _send,
    authorized_database,
)

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

EVIDENCE = {
    "evidence_id": "ev_payment_error_rate",
    "source": "grafana-mcp",
    "summary": "Payment error rate back under one percent for ten minutes.",
    "collected_at": NOW.isoformat(),
    "request_id": str(uuid.UUID(int=41)),
}
POSTMORTEM = {
    "postmortem_id": "pm_payment_flag",
    "summary": "paymentFailure flag disabled; error rate recovered.",
    "status": "declared",
    "created_by": "agent",
    "created_at": NOW.isoformat(),
}
APPROVE = {
    "action": "run.approve",
    "resource": {"type": "incident_workflow", "id": "incident-response"},
}


def _seed(incident_id: str, state: str, **fields: object) -> None:
    document = yaml.safe_load(INITIAL_STATE_PATH.read_text())
    document.update(state=state, incident_id=incident_id, severity="sev2", **fields)
    RUNS[incident_id] = f"run_{incident_id.replace('-', '')}"
    run = {"workflow_version": "1.0.0", "current_state": state, "status": "awaiting_human"}

    async def _add() -> None:
        database = Database(DATABASE_URL)
        try:
            async with PostgresIncidentUnitOfWork(database) as work:
                await work.incidents.add(incident_id, document, now=NOW)
                await work.runs.add(RUNS[incident_id], incident_id, run, now=NOW)
        finally:
            await database.dispose()

    asyncio.run(_add())


def _verifying(incident_id: str) -> None:
    strategy = MITIGATION | {"approval_status": "approved"}
    _seed(incident_id, "verifying", evidence=[EVIDENCE], mitigation_strategy=strategy)


def _row(incident_id: str) -> tuple[str, int, int]:
    """State, incident version and event count, read straight from the store."""

    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT i.state->>'state', i.version, "
            "(SELECT count(*) FROM incident.run_events e WHERE e.run_id = %s) "
            "FROM incident.incidents i WHERE i.incident_id = %s",
            (RUNS[incident_id], incident_id),
        ).fetchone()
    assert row is not None
    return str(row[0]), int(row[1]), int(row[2])


def _command(name: str, principal: str = "demo-human", **extra: object) -> dict:
    return _body(name, principal, expected_incident_version=0, **extra)


def _close(incident_id: str, key: str, principal: str = "demo-human", bearer=None, **extra):
    """Close with the explicit approval assertion unless a case drops it (None)."""

    fields = {name: value for name, value in ({"authorization": APPROVE} | extra).items() if value}
    body = _command("close_incident", principal, **fields)
    return _send(incident_id, key, body, bearer=bearer or principal)


def test_stable_verification_resolves_and_not_stable_returns_to_investigating() -> None:
    _verifying("inc-v21-stable")
    _verifying("inc-v21-unstable")
    passed = _send("inc-v21-stable", "key-v21-stable-01", _command("verification_passed"))
    failed = _send("inc-v21-unstable", "key-v21-unstable1", _command("verification_failed"))
    assert (passed.status_code, passed.json()["current_state"]) == (202, "resolved")
    assert (failed.status_code, failed.json()["current_state"]) == (202, "investigating")
    assert _row("inc-v21-stable") == ("resolved", 1, 1)
    assert _row("inc-v21-unstable") == ("investigating", 1, 1)
    blind = _send("inc-v21-stable", "key-v21-blind-001", _body("verification_passed"))
    assert blind.status_code == 422


def test_closure_without_a_postmortem_fails_its_precondition_and_changes_nothing() -> None:
    _seed("inc-v21-nopm", "postmortem")
    refused = _close("inc-v21-nopm", "key-v21-nopm-0001")
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "precondition_failed")
    assert _row("inc-v21-nopm") == ("postmortem", 0, 0)


def test_closure_without_the_explicit_approval_is_refused() -> None:
    _seed("inc-v21-noappr", "postmortem", postmortem=POSTMORTEM)
    implicit = _close("inc-v21-noappr", "key-v21-noappr-01", authorization=None)
    downgraded = _close(
        "inc-v21-noappr", "key-v21-noappr-02", authorization=APPROVE | {"action": "run.command"}
    )
    assert (implicit.status_code, downgraded.status_code) == (422, 422)
    assert _row("inc-v21-noappr") == ("postmortem", 0, 0)


def test_approved_closure_with_a_postmortem_closes_once_even_when_replayed() -> None:
    _seed("inc-v21-close", "postmortem", postmortem=POSTMORTEM)
    closed = _close("inc-v21-close", "key-v21-close-001", comment="Postmortem reviewed.")
    assert (closed.status_code, closed.json()["current_state"]) == (202, "closed")
    replayed = _close("inc-v21-close", "key-v21-close-001", comment="Postmortem reviewed.")
    assert replayed.status_code == 202 and replayed.json() == closed.json()
    assert _row("inc-v21-close") == ("closed", 1, 1)
    with psycopg.connect(DATABASE_URL) as connection:
        approvals = connection.execute(
            "SELECT document->'approval' FROM incident.decisions WHERE run_id = %s",
            (RUNS["inc-v21-close"],),
        ).fetchall()
    assert [
        (row[0]["postmortem_id"], row[0]["actor_reference"]["principal_id"]) for row in approvals
    ] == [("pm_payment_flag", "demo-human")]


def test_a_stale_version_conflicts_without_overwriting() -> None:
    _verifying("inc-v21-stale")
    _seed("inc-v21-stalepm", "postmortem", postmortem=POSTMORTEM)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE incident.incidents SET version = 3, updated_at = now() "
            "WHERE incident_id IN ('inc-v21-stale', 'inc-v21-stalepm')"
        )
    stale = _send("inc-v21-stale", "key-v21-stale-001", _command("verification_passed"))
    stale_close = _close("inc-v21-stalepm", "key-v21-stalepm1")
    assert (stale.status_code, stale_close.status_code) == (409, 409)
    assert stale_close.json()["error"]["code"] == "run_conflict"
    assert _row("inc-v21-stale") == ("verifying", 3, 0)
    assert _row("inc-v21-stalepm") == ("postmortem", 3, 0)


def test_closing_needs_run_approve_and_a_human() -> None:
    _seed("inc-v21-perm", "postmortem", postmortem=POSTMORTEM)
    _verifying("inc-v21-agent")
    sender = _close("inc-v21-perm", "key-v21-sender-01", "sender-human")
    assert (sender.status_code, sender.json()["error"]["code"]) == (403, "not_authorized")
    agent = _close("inc-v21-perm", "key-v21-agent-001", "approving-harness")
    # Naming a human in the body does not turn an agent credential into one.
    spoofed = _close("inc-v21-perm", "key-v21-agent-002", bearer="approving-harness")
    assert (agent.status_code, spoofed.status_code) == (403, 403)
    assert _row("inc-v21-perm") == ("postmortem", 0, 0)
    for index, name in enumerate(("verification_passed", "verification_failed")):
        body = _command(name, "approving-harness")
        refused = _send(
            "inc-v21-agent", f"key-v21-agentv-{index}", body, bearer="approving-harness"
        )
        assert refused.status_code == 403
    assert _row("inc-v21-agent") == ("verifying", 0, 0)
