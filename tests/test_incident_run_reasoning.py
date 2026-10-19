"""The incident's recorded reasoning reaches only run.read_context readers (console, #39).

Ways this can fail, written before the code:
1. A principal holding only run.read, an anonymous caller or a run named under another
   incident reads the hypothesis or the mitigation text.
2. A safe projection (detail, run, events, timeline, snapshot) starts carrying that text.
3. The reasoning shown is not what the runtime recorded: the raw model output instead of
   the validated artifact, or the links between artifacts are lost (cited evidence ids,
   based_on_hypothesis, execution_mode, the governed request id of the evidence).
4. A run whose incident holds no hypothesis yet fails instead of answering an explicit
   empty reasoning.
5. The human decision is not reflected: approval_status stays pending after approval.
"""

from __future__ import annotations

import json

import httpx
import psycopg
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
    _create_started_run_with_pending_receipt,
    _free_port,
    _grant_run_access,
    _serve,
    _start,
    migrated_database,  # noqa: F401 -- a fresh synthetic DB: this module adds a principal
)

SCHEMA = yaml.safe_load((ROOT / "agent/schemas/run-context.schema.yaml").read_text())
STATEMENT = "A synthetic payment error-rate increase is visible."
MITIGATION = "Keep the synthetic payment path simulated."


def _reader(client: httpx.Client) -> dict[str, str]:
    """A human whose only incident grant is run.read_context."""
    admin = {"Authorization": f"Bearer {ADMIN_KEY}"}
    created = client.post(
        "/v1/principals",
        headers=admin | {"Idempotency-Key": "create-reasoning-reader"},
        json={"principal_id": "reasoning-reader", "kind": "human", "display_name": "Reader"},
    )
    issued = client.post(
        "/v1/principals/reasoning-reader/credentials",
        headers=admin | {"Idempotency-Key": "issue-reasoning-reader"},
        json={"expires_at": "2031-01-01T00:00:00Z"},
    )
    granted = client.post(
        "/v1/grants",
        headers=admin | {"Idempotency-Key": "grant-reasoning-reader-context"},
        json={
            "grant_id": "grant-reasoning-reader-run-read-context",
            "principal_id": "reasoning-reader",
            "action": "run.read_context",
            "resource": {"resource_type": "incident_workflow", "resource_id": "incident-response"},
            "effect": "allow",
        },
    )
    assert (created.status_code, issued.status_code, granted.status_code) == (201, 201, 201)
    return {"Authorization": f"Bearer {issued.json()['key']}"}


def _stored_state(incident_id: str) -> dict:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state FROM incident.incidents WHERE incident_id = %s", (incident_id,)
        ).fetchone()
    assert row is not None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def test_the_recorded_reasoning_reaches_only_context_readers_and_follows_the_decision() -> None:
    incident_id, other_id, empty_id = "inc-reasoning", "inc-reasoning-other", "inc-reasoning-new"
    for incident in (incident_id, other_id, empty_id):
        _add_incident(incident)
    _grant_run_access()
    empty_run = _create_started_run_with_pending_receipt(empty_id, "start-inc-reasoning-new")
    human = {"Authorization": f"Bearer {HUMAN_KEY}"}
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=ScriptedLLM(), mcp=ScriptedMCP())
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        _add_agent_mcp_grants(client, "reasoning")
        reader = _reader(client)
        started = _start(client, incident_id, "investigation-reasoning-0001")
        assert started.status_code == 201
        run_id = started.json()["run_id"]
        incident_path = f"/v1/incidents/{incident_id}"
        path = f"{incident_path}/runs/{run_id}"
        proposed = client.get(f"{path}/context", headers=reader)
        refused = [
            client.get(f"{path}/context", headers=human),
            client.get(path.replace(incident_id, other_id) + "/context", headers=reader),
            client.get(f"{path}/context"),
        ]
        safe = [
            client.get(incident_path, headers=human),
            client.get(path, headers=human),
            client.get(f"{path}/events", headers=human),
            client.get(f"{incident_path}/timeline?run_id={run_id}", headers=human),
            client.get(f"{incident_path}/snapshot?run_id={run_id}", headers=human),
        ]
        empty = client.get(f"/v1/incidents/{empty_id}/runs/{empty_run}/context", headers=reader)
        version = safe[0].json()["version"]
        approved = client.post(
            f"{path}/commands",
            headers=human | {"Idempotency-Key": "approve-reasoning-0001"},
            json={
                "command": "approve_mitigation",
                "expected_incident_version": version,
                "actor": "human",
                "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
            },
        )
        after = client.get(f"{path}/context", headers=reader)

    assert proposed.status_code == 200
    assert proposed.headers["cache-control"] == "no-store"
    Draft202012Validator(SCHEMA).validate(proposed.json())
    reasoning = proposed.json()["reasoning"]
    stored = _stored_state(incident_id)
    # The validated artifacts the runtime recorded, not the model's raw text.
    assert [item["statement"] for item in reasoning["hypotheses"]] == [STATEMENT]
    hypothesis = reasoning["hypotheses"][0]
    assert hypothesis["hypothesis_id"] == stored["hypotheses"][0]["hypothesis_id"]
    assert hypothesis["confidence"] == "medium"
    evidence_ids = [item["evidence_id"] for item in reasoning["evidence"]]
    assert evidence_ids == [item["evidence_id"] for item in stored["evidence"]]
    assert set(hypothesis["supporting_evidence"]) <= set(evidence_ids)
    cited = reasoning["evidence"][0]
    assert (cited["tool"], cited["datasource_uid"]) == ("query_prometheus", "webstore-metrics")
    assert "rate(http_requests_total[5m])" in cited["query"]
    assert cited["request_id"] == stored["evidence"][0]["request_id"] is not None
    assert cited["summary"]
    strategy = reasoning["mitigation_strategy"]
    assert strategy["description"] == MITIGATION
    assert strategy["steps"] == ["Keep the change simulated."]
    assert strategy["verification_check"] == "The synthetic payment error rate returns to zero."
    assert (strategy["risk"], strategy["execution_mode"]) == ("low", "simulated")
    assert strategy["approval_status"] == "pending"
    assert strategy["based_on_hypothesis"] == hypothesis["hypothesis_id"]

    assert [response.status_code for response in refused] == [403, 404, 401]
    assert [response.status_code for response in safe] == [200, 200, 200, 200, 200]
    for response in (*refused, *safe):
        assert STATEMENT not in response.text and MITIGATION not in response.text

    assert empty.status_code == 200
    Draft202012Validator(SCHEMA).validate(empty.json())
    assert empty.json()["reasoning"] == {
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
    }

    assert approved.status_code == 202, approved.text
    assert after.json()["reasoning"]["mitigation_strategy"]["approval_status"] == "approved"
