"""Seed one incident awaiting mitigation approval for the #41 verify/close journey.

Evidence-only helper, not production bootstrap (same pattern as
seed_war_room_demo.py): creates the incident and its run once, then drives the
steps before the human review through the real IncidentRuntime with fixed
command identities and a fixed clock, so reruns replay instead of duplicating:
open_triage, triage_declare, start_investigation, continue_investigation (one
hypothesis citing one evidence item) and propose_mitigation (a pending
mitigation with its verification_check). The agent steps use the same command
shape as the investigator; the evidence is a labelled fixture (source: fixture),
never an observed query. Every later step is human and goes through the HTTP
API or the console. Requires DATABASE_URL and SEED_STAMP ([a-z0-9-]{4,32}).
SEED_UNTIL=<transition> stops after that step (e.g. start_investigation leaves the
run investigating); a later run without it replays those steps and finishes.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from sre_agent.incident.runtime import (  # noqa: E402
    ActorReference,
    IncidentCommand,
    IncidentRuntime,
)
from sre_agent.incident.workflow import load_incident_workflow  # noqa: E402
from sre_agent.persistence.database import Database  # noqa: E402
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork  # noqa: E402

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)  # fixed and in the past: replays match
AT = NOW.isoformat()
RUN = {"workflow_version": "1.0.0", "current_state": "detected", "status": "running"}
OPERATOR = ActorReference(principal_id="demo-human")
AGENT = ActorReference(principal_id="incident-harness")
EVIDENCE = {
    "evidence_id": "ev_payment_error_rate",
    "source": "fixture",
    "tool": "query_prometheus",
    "datasource_uid": "webstore-metrics",
    "query": 'sum(rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m]))',
    "time_window": "5m",
    "summary": "Synthetic fixture: payment error calls rose after paymentFailure was enabled.",
    "collected_at": AT,
    "request_id": None,
}
HYPOTHESIS = {
    "hypothesis_id": "hyp_payment_flag",
    "statement": "The paymentFailure feature flag makes PaymentService/Charge fail.",
    "confidence": "medium",
    "status": "open",
    "supporting_evidence": ["ev_payment_error_rate"],
    "created_by": "agent",
    "created_at": AT,
}
MITIGATION = {
    "mitigation_id": "mit_disable_payment_flag",
    "description": "Turn the paymentFailure feature flag off.",
    "steps": ["The operator sets paymentFailure to off in the flag service."],
    "risk": "low",
    "verification_check": "paymentservice error rate below 1% for ten minutes.",
    "approval_status": "pending",
    "execution_mode": "human",
    "based_on_hypothesis": "hyp_payment_flag",
    "created_by": "agent",
    "created_at": AT,
}


def commands(incident_id: str, run_id: str) -> list[IncidentCommand]:
    steps = [
        ("open_triage", "system", None, None, None),
        ("triage_declare", "human", OPERATOR, "declare",
         {"severity": "sev2", "impact": "Checkout failing at payment."}),
        ("start_investigation", "agent", AGENT, None, None),
        ("continue_investigation", "agent", AGENT, "continue_investigation",
         {"remaining_step_budget": 4,
          "incident_patch": {"hypotheses": [HYPOTHESIS], "evidence": [EVIDENCE]}}),
        ("propose_mitigation", "agent", AGENT, "propose_mitigation",
         {"incident_patch": {"mitigation_strategy": MITIGATION, "evidence": [EVIDENCE]}}),
    ]  # fmt: skip
    return [
        IncidentCommand(
            command_id=f"cmd_{run_id}_{transition}",
            incident_id=incident_id,
            run_id=run_id,
            transition_id=transition,
            actor=actor,
            actor_reference=reference,
            outcome=outcome,
            inputs=inputs,
        )
        for transition, actor, reference, outcome, inputs in steps
    ]


async def main() -> None:
    dsn, stamp = os.environ.get("DATABASE_URL"), os.environ.get("SEED_STAMP", "")
    if not dsn or re.fullmatch(r"[a-z0-9-]{4,32}", stamp) is None:
        raise SystemExit("DATABASE_URL and SEED_STAMP ([a-z0-9-]{4,32}) are required")
    incident_id, run_id = f"inc-vc-{stamp}", "run_vc" + stamp.replace("-", "")
    alert = {
        "alert_id": f"alt-vc-{stamp}",
        "service": "paymentservice",
        "severity": "sev2",
        "status": "new",
        "observed_at": AT,
        "summary": "Elevated error rate on paymentservice.",
        "source": "grafana-alerting",
    }
    workflow = load_incident_workflow(
        REPOSITORY_ROOT / "agent" / "workflows" / "incident-response.yaml"
    )
    database = Database(dsn)
    try:
        async with PostgresIncidentUnitOfWork(database) as work:
            if await work.incidents.get(incident_id) is None:
                state = {
                    "workflow_id": "incident-response",
                    "workflow_version": "1.0.0",
                    "state": "detected",
                    "severity": None,
                    "impact": None,
                    "alert": alert,
                    "hypotheses": [],
                    "evidence": [],
                    "mitigation_strategy": None,
                    "postmortem": None,
                    "approvals": [],
                    "updated_at": AT,
                }
                await work.incidents.add(incident_id, state, now=NOW)
                await work.runs.add(run_id, incident_id, dict(RUN), now=NOW)
        runtime = IncidentRuntime(
            workflow, lambda: PostgresIncidentUnitOfWork(database), clock=lambda: NOW
        )
        until = os.environ.get("SEED_UNTIL")
        for command in commands(incident_id, run_id):
            result = await runtime.execute(command)
            print(
                f"{command.transition_id}: incident v{result.incident.version} "
                f"{result.incident.state['state']} (replayed={result.replayed})"
            )
            if command.transition_id == until:
                break
        print(f"seeded {incident_id} / {run_id}")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
