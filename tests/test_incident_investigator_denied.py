"""A governed call denied in a durable run blocks the run for a human (#39, CA3)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg
import pytest
from test_incident_investigator_http import (
    ADMIN_KEY,
    BLOCKED,
    DATABASE_URL,
    HUMAN_KEY,
    ROOT,
    ScriptedLLM,
    ScriptedMCP,
    _active_state,
    _add_agent_mcp_grants,
    _add_incident,
    _application,
    _context_turns,
    _create_started_run_with_pending_receipt,
    _free_port,
    _grant_run_access,
    _serve,
    _start,
    migrated_database,  # noqa: F401 -- a fresh synthetic DB: this module revokes a grant
)

from sre_agent.gateway.providers import ProviderRequest, ProviderResult
from sre_agent.incident.persistence import DecisionDraft, EventDraft
from sre_agent.incident.runtime import IncidentRuntime
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork


class RevokingLLM(ScriptedLLM):
    """An administrator revokes the agent's tool grant while the model answers."""

    def __init__(self, base_url: str, grant_id: str) -> None:
        super().__init__()
        self.base_url, self.grant_id = base_url, grant_id
        self.revocations: list[int] = []

    async def create(self, request: ProviderRequest) -> ProviderResult:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=15) as admin:
            revoked = await admin.delete(
                f"/v1/grants/{self.grant_id}", headers={"Authorization": f"Bearer {ADMIN_KEY}"}
            )
        self.revocations.append(revoked.status_code)
        return await super().create(request)


def test_tool_grant_revoked_mid_run_blocks_the_run_for_a_human_without_retry() -> None:
    incident_id = "inc-investigator-revoked"
    _add_incident(incident_id)
    _grant_run_access()
    port = _free_port()
    llm = RevokingLLM(f"http://127.0.0.1:{port}", "grant-agent-mcp-prometheus-revoked")
    mcp = ScriptedMCP()
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    human = {"Authorization": f"Bearer {HUMAN_KEY}"}
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "revoked")
        first = _start(client, incident_id, "investigation-revoked-0001")
        assert first.status_code == 201
        run_id = first.json()["run_id"]
        replay = _start(client, incident_id, "investigation-revoked-0001")
        read = client.get(f"/v1/incidents/{incident_id}/runs/{run_id}", headers=human)
        timeline = client.get(f"/v1/incidents/{incident_id}/runs/{run_id}/events", headers=human)

    assert (replay.status_code, read.status_code, timeline.status_code) == (200, 200, 200)
    assert {key: first.json()[key] for key in BLOCKED} == BLOCKED
    assert first.json()["current_state"] == "investigating"
    assert replay.json() == read.json() == first.json()
    # One model answer, the revocation, one denied invocation: nothing upstream, no retry.
    assert llm.revocations == [204] and len(llm.requests) == 1 and mcp.calls == []
    with psycopg.connect(DATABASE_URL) as connection:
        incident = connection.execute(
            "SELECT state, version FROM incident.incidents WHERE incident_id=%s", (incident_id,)
        ).fetchone()
        run = connection.execute(
            "SELECT state, version, updated_at FROM incident.runs WHERE run_id=%s", (run_id,)
        ).fetchone()
        events: list[tuple[str, dict[str, Any]]] = connection.execute(
            "SELECT kind, payload FROM incident.run_events WHERE run_id=%s ORDER BY sequence",
            (run_id,),
        ).fetchall()
        audits = connection.execute(
            "SELECT operation, outcome, reason_code, response_status, "
            "identity->'credential_ref'->>'digest', correlation->>'request_id' FROM audit_events "
            "WHERE operation IN ('mcp.discovery', 'responses.create', 'mcp.invoke') "
            "ORDER BY occurred_at"
        ).fetchall()
    assert [kind for kind, _ in events] == [
        "state_change",
        "dispatch_receipt",
        "dispatch_receipt",
        "escalation",
    ]
    # The incident is exactly what start_investigation left; the run is blocked, not moved.
    assert incident == (events[0][1]["incident_state"], 1)
    assert run[1] == 1 and run[0]["current_state"] == "investigating"
    assert {key: run[0][key] for key in BLOCKED} == BLOCKED
    assert datetime.fromisoformat(run[0]["updated_at"]) == run[2]
    receipt, escalation = events[2][1]["dispatch_receipt"], events[3][1]
    assert (receipt["status"], receipt["reason_code"], receipt["result_status"]) == (
        "confirmed_failure",
        "governed_call_denied",
        "denied",
    )
    assert escalation["reason_code"] == "governed_call_denied"
    assert {key: escalation["run_patch"][key] for key in BLOCKED} == BLOCKED
    assert [row[:4] for row in audits] == [
        ("mcp.discovery", "success", None, 200),
        ("responses.create", "success", None, 200),
        ("mcp.invoke", "denied", "no_matching_grant", 403),
    ]
    # Every governed call used the one configured credential: no other identity was tried.
    assert len({row[4] for row in audits}) == 1
    assert escalation["request_id"] == receipt["request_ids"][-1] == audits[-1][5]
    assert _context_turns(run_id) == 1, "the turn that asked for the tool is the run's context"
    last = timeline.json()["events"][-1]
    assert (last["kind"], last["state"], last["summary"]) == (
        "escalation",
        "investigating",
        "Authorization denied; an administrator must grant the capability, "
        "then a new run may retry.",
    )

    async def rebuild() -> tuple[Any, Any]:
        database = Database(DATABASE_URL)
        workflow = load_incident_workflow(ROOT / "agent/workflows/incident-response.yaml")
        try:
            runtime = IncidentRuntime(workflow, lambda: PostgresIncidentUnitOfWork(database))
            view = await runtime.reconstruct(incident_id, run_id)
        finally:
            await database.dispose()
        return view.incident_state, view.run_state

    assert asyncio.run(rebuild()) == (incident[0], run[0])


@pytest.mark.parametrize(
    ("run_patch", "escalations"),
    [({"current_state": "mitigating"}, 1), (BLOCKED, 0), (None, 1)],
    ids=["moves-the-state", "blocks-silently", "escalates-without-block"],
)
def test_a_dispatch_outcome_blocks_its_run_only_through_one_escalation(
    run_patch: dict[str, Any] | None, escalations: int, request: pytest.FixtureRequest
) -> None:
    incident_id = f"inc-run-patch-{request.node.callspec.id}"
    _add_incident(incident_id)
    run_id = _create_started_run_with_pending_receipt(incident_id, f"start-{incident_id}")
    now = datetime.now(UTC)
    receipt = {"dispatch_id": run_id, "phase": "outcome", "status": "confirmed_failure"}
    events = [
        EventDraft("evt_patchreceipt01", "dispatch_receipt", {"dispatch_receipt": receipt}, now),
        *[EventDraft("evt_patchescalate1", "escalation", {"run_patch": run_patch}, now)]
        * escalations,
    ]

    async def complete() -> None:
        database = Database(DATABASE_URL)
        try:
            async with PostgresIncidentUnitOfWork(database) as work:
                await work.complete_run_dispatch(
                    incident_id,
                    run_id,
                    decision=DecisionDraft("dec_patchoutcome1", {"actor": "system"}, now, run_id),
                    events=events,
                    run_patch=run_patch,
                )
        finally:
            await database.dispose()

    with pytest.raises(ValueError):
        asyncio.run(complete())
    assert _active_state(run_id)[0]["status"] == "running"
