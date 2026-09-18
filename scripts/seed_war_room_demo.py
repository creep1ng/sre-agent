"""Seed one war-room demo incident for HU-OPS-03 evidence (issue #36).

Evidence-only helper, not production bootstrap: creates the incident and run
once, then drives three transitions through the real IncidentRuntime with
fixed command identities and a fixed clock, so reruns replay instead of
duplicating. Requires DATABASE_URL on a migrated database. Grants are
intentionally out of scope here: reads stay denied until run.read grants are
seeded through the governed grant model, never globally.
"""

from __future__ import annotations

import asyncio
import os
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

INCIDENT_ID = "inc-war-room-demo"
RUN_ID = "run_warroomdemo01"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

ALERT = {
    "alert_id": "alt-payment-error-rate",
    "service": "paymentservice",
    "severity": "sev2",
    "status": "new",
    "observed_at": "2026-08-24T14:05:00Z",
    "summary": "Elevated error rate on paymentservice.",
    "source": "grafana-alerting",
    "origin": {
        "signal": "traces_span_metrics_calls_total",
        "condition": "error rate above threshold",
        "detector": "webstore-metrics",
        "observed_at": "2026-08-24T14:04:30Z",
    },
}

OPERATOR = ActorReference(principal_id="demo-operator", display_name="Demo on-call engineer")

COMMANDS = (
    IncidentCommand(
        command_id="cmd_warroom_open",
        incident_id=INCIDENT_ID,
        run_id=RUN_ID,
        transition_id="open_triage",
        actor="system",
    ),
    IncidentCommand(
        command_id="cmd_warroom_declare",
        incident_id=INCIDENT_ID,
        run_id=RUN_ID,
        transition_id="triage_declare",
        actor="human",
        actor_reference=OPERATOR,
        outcome="declare",
        inputs={"severity": "sev2"},
    ),
    IncidentCommand(
        command_id="cmd_warroom_investigate",
        incident_id=INCIDENT_ID,
        run_id=RUN_ID,
        transition_id="start_investigation",
        actor="agent",
    ),
)


def _base_state() -> dict:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "detected",
        "severity": None,
        "impact": None,
        "alert": dict(ALERT),
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": NOW.isoformat(),
    }


def _base_run() -> dict:
    return {"workflow_version": "1.0.0", "current_state": "detected", "status": "running"}


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    workflow = load_incident_workflow(
        REPOSITORY_ROOT / "agent" / "workflows" / "incident-response.yaml"
    )
    database = Database(dsn)
    try:
        async with PostgresIncidentUnitOfWork(database) as work:
            if await work.incidents.get(INCIDENT_ID) is None:
                await work.incidents.add(INCIDENT_ID, _base_state(), now=NOW)
                await work.runs.add(RUN_ID, INCIDENT_ID, _base_run(), now=NOW)
        runtime = IncidentRuntime(
            workflow,
            lambda: PostgresIncidentUnitOfWork(database),
            clock=lambda: NOW,
        )
        for command in COMMANDS:
            result = await runtime.execute(command)
            print(
                f"{command.command_id}: incident v{result.incident.version} "
                f"{result.incident.state['state']} (replayed={result.replayed})"
            )
        print(f"seeded {INCIDENT_ID} / {RUN_ID}")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
