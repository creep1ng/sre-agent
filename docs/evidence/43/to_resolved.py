"""Drive a new incident from an alert to `resolved` for postmortem evidence (#43), without a model.

Run in the seed service, which already holds the database URL and the demo keys:

    docker compose run --rm --no-deps -v "$PWD/docs/evidence/43:/evidence:ro" \
        seed python /evidence/to_resolved.py <alert-id> [--written]

Every human step goes through the HTTP API as demo-human: triage, declaration, the
investigation run, the mitigation approval and `verification_passed`. The two model turns
(hypothesis, mitigation proposal) are stood in by the same IncidentRuntime transitions the
investigator executes, attributed to the harness, with fixed text: no LLM, no SQL.
`--written` also opens the postmortem (objective postmortem) and writes version 1 through
PUT /postmortem. Grants: run.read_context for demo-human and run.read for incident-harness,
through the governed grants API. Keys are read from the environment and never printed.
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4

from sre_agent.application import INCIDENT_WORKFLOW_PATH
from sre_agent.incident.runtime import ActorReference, IncidentCommand, IncidentRuntime
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

API = "http://api:8000"
HUMAN = {"reference_version": "1.0.0", "principal_id": "demo-human"}
WORKFLOW = {"type": "incident_workflow", "id": "incident-response"}


def call(method: str, path: str, body: dict | None = None, key: str = "DEMO_HUMAN_API_KEY") -> dict:
    headers = {"Authorization": f"Bearer {os.environ[key]}", "Content-Type": "application/json"}
    headers["Idempotency-Key"] = f"evidence-43-{uuid4().hex}"
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(API + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, payload = response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        status, payload = error.code, json.loads(error.read() or b"{}")
    print(f"{method} {path} -> HTTP {status}")
    if status >= 300 and not (path == "/v1/grants" and status == 409):
        raise SystemExit(json.dumps(payload))
    return payload


def grant(principal: str, action: str) -> None:
    resource = {"resource_type": "incident_workflow", "resource_id": "incident-response"}
    grant_id = f"grant-evidence-43-{principal}-{action.replace('.', '-')}"
    body = {"grant_id": grant_id, "principal_id": principal, "action": action, "resource": resource}
    call("POST", "/v1/grants", body | {"effect": "allow"}, key="ADMIN_HUMAN_API_KEY")


async def agent_turns(incident_id: str, run_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    evidence = {
        "evidence_id": "ev_evidence43",
        "source": "simulated",
        "collected_at": now,
        "summary": "Payment charge calls time out since the last config push (simulated).",
    }
    hypothesis = {
        "hypothesis_id": "hyp_evidence43",
        "confidence": "medium",
        "status": "open",
        "statement": "A config push removed the payment client timeout (simulated turn).",
        "supporting_evidence": ["ev_evidence43"],
        "created_by": "agent",
        "created_at": now,
    }
    mitigation = {
        "mitigation_id": "mit_evidence43",
        "risk": "low",
        "approval_status": "pending",
        "description": "Roll back the payment client config.",
        "execution_mode": "simulated",
        "steps": ["Ask the operator to roll back the payment client config."],
        "verification_check": "Payment error rate below 1% for 15 minutes.",
        "based_on_hypothesis": "hyp_evidence43",
        "created_by": "agent",
        "created_at": now,
    }
    turns = (
        (
            "continue_investigation",
            {
                "remaining_step_budget": 3,
                "incident_patch": {"hypotheses": [hypothesis], "evidence": [evidence]},
            },
        ),
        (
            "propose_mitigation",
            {"incident_patch": {"mitigation_strategy": mitigation, "evidence": [evidence]}},
        ),
    )
    database = Database(os.environ["DATABASE_URL"])
    try:
        workflow = load_incident_workflow(INCIDENT_WORKFLOW_PATH)
        runtime = IncidentRuntime(workflow, lambda: PostgresIncidentUnitOfWork(database))
        for transition_id, inputs in turns:
            command = IncidentCommand(
                command_id=f"evidence-43-{transition_id}-{run_id}",
                incident_id=incident_id,
                run_id=run_id,
                transition_id=transition_id,
                actor="agent",
                outcome=transition_id,
                actor_reference=ActorReference(principal_id="incident-harness"),
                inputs=inputs,
            )
            result = await runtime.execute(command)
            print(f"agent turn {transition_id} (simulated) -> {result.incident.state['state']}")
    finally:
        await database.dispose()


def command(incident_id: str, run_id: str, name: str, extra: dict) -> None:
    version = call("GET", f"/v1/incidents/{incident_id}")["version"]
    body = {
        "command": name,
        "actor": "human",
        "actor_reference": HUMAN,
        "expected_incident_version": version,
    }
    call("POST", f"/v1/incidents/{incident_id}/runs/{run_id}/commands", body | extra)


def main(alert_id: str, written: bool) -> None:
    grant("demo-human", "run.read_context")
    grant("incident-harness", "run.read")
    triage = f"/v1/alerts/{alert_id}/triage/commands"
    call("POST", triage, {"operation": "open_triage", "expected_version": 1})
    context = {
        "service": "paymentservice",
        "summary": "Elevated error rate on paymentservice.",
        "observed_at": "2026-10-19T03:50:00Z",
        "source": "grafana-alerting",
        "severity": "sev2",
    }
    incident_id = call(
        "POST",
        triage,
        {
            "operation": "triage_declare",
            "expected_version": 1,
            "severity": "sev2",
            "alert_context": context,
            "reason": "Checkout payment errors above threshold",
            "impact": "About 3% of checkouts fail at payment.",
        },
    )["incident_id"]
    runs = f"/v1/incidents/{incident_id}/runs"
    run_id = call("POST", runs, {"workflow_version": "1.0.0", "objective": "investigate"})["run_id"]
    asyncio.run(agent_turns(incident_id, run_id))
    approval = {
        "comment": "Rollback plan is low risk.",
        "authorization": {"action": "run.approve", "resource": WORKFLOW},
    }
    command(incident_id, run_id, "approve_mitigation", approval)
    command(
        incident_id,
        run_id,
        "verification_passed",
        {"comment": "Error rate below 1% for 15 minutes."},
    )
    if written:
        call("POST", runs, {"workflow_version": "1.0.0", "objective": "postmortem"})
        events = call("GET", f"/v1/incidents/{incident_id}/timeline?run_id={run_id}&limit=200")[
            "events"
        ]
        cite = {
            event["state"]: event["event_id"] for event in events if event["kind"] == "state_change"
        }
        content = {
            "summary": "Checkout payments failed at the payment step after a config push.",
            "impact": "About 3% of checkouts failed at payment.",
            "timeline": [{"event_id": cite["resolved"], "description": "Service verified stable."}],
            "cause": {
                "statement": "A config push removed the payment client timeout.",
                "certainty": "hypothesis",
            },
            "strategy": "Roll back the payment client config.",
            "actions_taken": [
                {"event_id": cite["verifying"], "description": "A human approved the rollback."}
            ],
            "verification": "Payment error rate below 1% for 15 minutes.",
            "pending": ["Add a config lint for client timeouts."],
            "unknowns": ["Exact revenue impact."],
        }
        call(
            "PUT",
            f"/v1/incidents/{incident_id}/postmortem",
            {"expected_version": 0, "content": content},
        )
    print(f"incident {incident_id}")


if __name__ == "__main__":
    main(sys.argv[1], "--written" in sys.argv[2:])
