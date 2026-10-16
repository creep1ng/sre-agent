"""A durable run writes its sensitive context; only run.read_context reads it back (#39)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg
import pytest
import yaml
from jsonschema import Draft202012Validator
from test_incident_investigator_http import (
    ADMIN_KEY,
    DATABASE_URL,
    HUMAN_KEY,
    ROOT,
    ScriptedLLM,
    ScriptedMCP,
    _add_agent_mcp_grants,
    _add_incident,
    _application,
    _context_turns,
    _create_started_run_with_pending_receipt,
    _database_rows,
    _free_port,
    _grant_run_access,
    _receipts,
    _serve,
    _start,
    migrated_database,  # noqa: F401 -- a fresh synthetic DB: this module adds a principal
)

from sre_agent.incident.persistence import (
    DecisionDraft,
    EventDraft,
    IncidentStaleWriteError,
    TextContextRecord,
)
from sre_agent.incident.runtime import IncidentRuntime
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

SCHEMA = yaml.safe_load((ROOT / "agent/schemas/run-context.schema.yaml").read_text())
# Only the context may carry these: the prompt and a tool argument.
SENSITIVE = ("You investigate one incident", "rate(http_requests_total[5m])")


def _auditor(client: httpx.Client) -> dict[str, str]:
    """An administrator creates a principal whose only incident grant is run.read_context."""
    admin = {"Authorization": f"Bearer {ADMIN_KEY}"}
    created = client.post(
        "/v1/principals",
        headers=admin | {"Idempotency-Key": "create-incident-auditor"},
        json={"principal_id": "incident-auditor", "kind": "human", "display_name": "Auditor"},
    )
    issued = client.post(
        "/v1/principals/incident-auditor/credentials",
        headers=admin | {"Idempotency-Key": "issue-incident-auditor"},
        json={"expires_at": "2031-01-01T00:00:00Z"},
    )
    granted = client.post(
        "/v1/grants",
        headers=admin | {"Idempotency-Key": "grant-incident-auditor-context"},
        json={
            "grant_id": "grant-incident-auditor-run-read-context",
            "principal_id": "incident-auditor",
            "action": "run.read_context",
            "resource": {"resource_type": "incident_workflow", "resource_id": "incident-response"},
            "effect": "allow",
        },
    )
    assert (created.status_code, issued.status_code, granted.status_code) == (201, 201, 201)
    return {"Authorization": f"Bearer {issued.json()['key']}"}


def test_the_run_writes_its_context_and_only_run_read_context_reads_it_after_restart() -> None:
    incident_id, other_id = "inc-context-run", "inc-context-other"
    _add_incident(incident_id)
    _add_incident(other_id)
    _grant_run_access()
    port = _free_port()
    llm, mcp = ScriptedLLM(), ScriptedMCP()
    human = {"Authorization": f"Bearer {HUMAN_KEY}"}
    app = _application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp)
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "context")
        auditor = _auditor(client)
        started = _start(client, incident_id, "investigation-context-0001")
        assert started.status_code == 201
        path = f"/v1/incidents/{incident_id}/runs/{started.json()['run_id']}"
        read = client.get(f"{path}/context", headers=auditor)
        # Watching the run (run.read) is not reading it; nor is naming the run of another incident.
        watcher = client.get(f"{path}/context", headers=human)
        crossed = client.get(path.replace(incident_id, other_id) + "/context", headers=auditor)
        anonymous = client.get(f"{path}/context")
        public = [client.get(path, headers=human), client.get(f"{path}/events", headers=human)]
    port = _free_port()
    with (
        _serve(_application(f"http://127.0.0.1:{port}", llm=llm, mcp=mcp), port) as base_url,
        httpx.Client(base_url=base_url, timeout=15) as client,
    ):
        reread = client.get(f"{path}/context", headers=auditor)

    assert (read.status_code, reread.status_code) == (200, 200)
    assert read.headers["cache-control"] == "no-store"
    Draft202012Validator(SCHEMA).validate(read.json())
    turns = read.json()["turns"]
    assert reread.json()["turns"] == turns
    assert [turn["assembled_input"] for turn in turns] == [item.input for item in llm.requests]
    actions = [json.loads(turn["model_output"])["action"] for turn in turns]
    assert actions == ["use_tool", "propose_hypothesis"]
    assert turns[0]["tool_invocation"]["arguments"]["expr"] == SENSITIVE[1]
    assert turns[1]["tool_invocation"] is None
    assert [turn["task_id"] for turn in turns] == [
        "task_" + turn["turn_id"].removeprefix("turn_") for turn in turns
    ]
    assert (watcher.status_code, crossed.status_code, anonymous.status_code) == (403, 404, 401)
    assert crossed.json()["error"]["code"] == "run_not_found"
    assert [response.status_code for response in public] == [200, 200]
    for response in (watcher, crossed, anonymous, *public):
        assert not any(marker in response.text for marker in SENSITIVE)
    with psycopg.connect(DATABASE_URL) as connection:
        audited = connection.execute(
            "SELECT operation, correlation->>'request_id', row_to_json(audit_events)::text "
            "FROM audit_events ORDER BY occurred_at"
        ).fetchall()
    # Each turn names the gateway request that answered it, and no audit event keeps content.
    assert [turn["request_id"] for turn in turns] == [
        row[1] for row in audited if row[0] == "responses.create"
    ]
    assert not any(marker in row[2] for row in audited for marker in SENSITIVE)


def test_a_turn_context_is_written_only_with_its_run_and_even_with_a_nul() -> None:
    incident_id = "inc-context-foreign"
    _add_incident(incident_id)
    run_id = _create_started_run_with_pending_receipt(incident_id, "start-inc-context-foreign")
    now = datetime.now(UTC)
    receipt = {"dispatch_id": run_id, "phase": "outcome", "status": "unknown"}
    event = EventDraft("evt_contextforeign", "dispatch_receipt", {"dispatch_receipt": receipt}, now)
    content = {"model_output": "\x00{", "tool_invocation": {"arguments": {"q\x00": ["\x00"]}}}

    async def complete(run: str) -> Any:
        database = Database(DATABASE_URL)
        try:
            async with PostgresIncidentUnitOfWork(database) as work:
                await work.complete_run_dispatch(
                    incident_id,
                    run_id,
                    decision=DecisionDraft("dec_contextforeign", {"actor": "system"}, now, run_id),
                    events=[event],
                    contexts=[
                        TextContextRecord("turn_contextnul", incident_id, run, 0, content, now)
                    ],
                )
                return await work.text_context.list(run_id)
        finally:
            await database.dispose()

    with pytest.raises(ValueError):
        asyncio.run(complete("run_contextforeign"))
    # PostgreSQL cannot store U+0000: the turn keeps U+FFFD and the outcome is not lost with it.
    assert [item.content for item in asyncio.run(complete(run_id))] == [
        {"model_output": "\ufffd{", "tool_invocation": {"arguments": {"q\ufffd": ["\ufffd"]}}}
    ]


@pytest.mark.parametrize(
    ("error", "reason_code"),
    [
        (IncidentStaleWriteError("changed"), "stale_incident_snapshot"),
        (RuntimeError("lost"), "result_persistence_uncertain"),
    ],
    ids=["stale", "uncertain"],
)
def test_a_result_the_runtime_could_not_apply_still_keeps_its_turns(
    error: Exception, reason_code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    incident_id = "inc-context-" + reason_code.replace("_", "-")
    _add_incident(incident_id)
    _grant_run_access()

    async def refuse(self: IncidentRuntime, command: Any) -> Any:
        raise error

    monkeypatch.setattr(IncidentRuntime, "execute", refuse)
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=ScriptedLLM(), mcp=ScriptedMCP())
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "context")
        started = _start(client, incident_id, f"investigation-{incident_id}")
    run_id = started.json()["run_id"]
    receipt = _receipts(_database_rows(incident_id, run_id)[1])[-1]
    assert (receipt["status"], receipt["reason_code"]) == ("unknown", reason_code)
    assert _context_turns(run_id) == 2
