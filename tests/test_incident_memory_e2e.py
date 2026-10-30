"""Issue #773: closing an incident indexes its approved postmortem as one memory, with its source.

Real PostgreSQL and the HTTP routes of the postmortem flow, from a resolved incident: open the
postmortem, write it, approve it and close. Ways this can fail:
1. The close indexes nothing, or indexes outside the close transaction.
2. The change log does not say what entered, when, and from which incident, postmortem
   version and close event.
3. The source record the memory names does not resolve to the approved postmortem.
4. An entry can be rewritten after the fact.
The run leaves `memory-change.json` in RECALL_ARTIFACT_DIR/issue-773 (default: the
temporary directory).
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient
from test_incident_closure_http import APPROVE, _seed
from test_incident_command_http import (  # noqa: F401  (module fixture)
    BEARERS,
    DATABASE_URL,
    INITIAL_STATE_PATH,
    _body,
    _send,
    authorized_database,
)

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import GrantRepository
from sre_agent.settings import Settings

ARTIFACTS = Path(os.environ.get("RECALL_ARTIFACT_DIR") or tempfile.gettempdir()) / "issue-773"
INCIDENT = "inc-memory-closed"
CONTENT = {
    "summary": "Release 1.5.0 of sre-checkout failed orders; the rollback restored them.",
    "impact": "42% of checkout orders failed for about five minutes.",
    "cause": {"statement": "Release 1.5.0 answers HTTP 500 on orders.", "certainty": "confirmed"},
    "strategy": "Roll back sre-checkout to the previous release 1.4.0.",
    "verification": "The 5xx ratio of checkout_requests_total stayed at 0 for 5 minutes.",
    "pending": [],
    "unknowns": [],
}


def _grant_context_read() -> None:
    async def grant() -> None:
        database = Database(DATABASE_URL)
        async with database.transaction() as session:
            await GrantRepository(session).create(
                "grant-demo-human-read-context-memory",
                "demo-human",
                "run.read_context",
                "incident_workflow",
                "incident-response",
            )
        await database.dispose()

    asyncio.run(grant())


def _one(query: str) -> object:
    with psycopg.connect(DATABASE_URL) as connection:
        [(value,)] = connection.execute(query, (INCIDENT,)).fetchall()
    return value


def test_closing_through_the_postmortem_flow_writes_one_memory_with_its_source() -> None:
    alert = yaml.safe_load(INITIAL_STATE_PATH.read_text())["alert"]
    alert |= {"service": "sre-checkout", "origin": {"signal": "checkout.requests"}}
    _seed(INCIDENT, "resolved", alert=alert)
    _grant_context_read()
    auth = {"Authorization": BEARERS["demo-human"]}
    path = f"/v1/incidents/{INCIDENT}/postmortem"
    with TestClient(create_application(Settings(DATABASE_URL))) as client:
        opened = client.post(
            f"/v1/incidents/{INCIDENT}/runs",
            headers=auth | {"Idempotency-Key": "memory-open-postmortem-0001"},
            json={"workflow_version": "1.0.0", "objective": "postmortem"},
        )
        assert opened.status_code == 201, opened.text
        run_id = opened.json()["run_id"]
        started = _one("SELECT event_id FROM incident.run_events WHERE incident_id=%s")
        cited = [{"event_id": started, "description": "Postmortem opened."}]
        body = {
            "expected_version": 0,
            "content": CONTENT | {"timeline": cited, "actions_taken": []},
        }
        assert client.put(path, headers=auth, json=body).status_code == 201
        review = {"version": 1, "outcome": "approved"}
        assert client.post(f"{path}/reviews", headers=auth, json=review).status_code == 201
        assert client.get("/v1/incident-memory/changes", headers=auth).json() == {"changes": []}
        version = _one("SELECT version FROM incident.incidents WHERE incident_id=%s")
        close = _body("close_incident", expected_incident_version=version, authorization=APPROVE)
        closed = _send(INCIDENT, "memory-close-incident-0001", close, run_id=run_id)
        assert closed.status_code == 202, closed.text
        [change] = client.get("/v1/incident-memory/changes", headers=auth).json()["changes"]
        source = client.get(change["source_record"], headers=auth).json()
    close_event = _one(
        "SELECT event_id FROM incident.run_events WHERE incident_id=%s"
        " AND payload->>'transition_id'='close_incident'"
    )
    with psycopg.connect(DATABASE_URL) as connection, pytest.raises(psycopg.Error):
        connection.execute("UPDATE incident.incident_memories SET content='rewritten'")
    assert change["incident_id"] == INCIDENT and change["operation"] == "added"
    assert change["service"] == "sre-checkout" and change["signal"] == "checkout.requests"
    assert change["postmortem_version"] == 1 and change["close_event_id"] == close_event
    assert CONTENT["strategy"] in change["content"] and "(confirmed)" in change["content"]
    assert source["postmortem_id"] == change["postmortem_id"]
    assert source["version"] == 1 and source["review"]["status"] == "approved"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "memory-change.json").write_text(
        json.dumps({"change": change, "source_record": source}, indent=2)
    )
