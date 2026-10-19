"""Seed the issue-37 T1 acceptance incidents for the war room run slice.

Evidence-only helper (not production bootstrap), stamped with SEED_STAMP so
reruns replay instead of duplicating: three incidents in `active` state with
severity and alert context and NO runs, one per acceptance journey:

- inc-37-start-<stamp>: the operator starts the investigation once (AC1, AC2).
- inc-37-double-<stamp>: a double click must create exactly one run (AC3).
- inc-37-restricted-<stamp>: restricted-harness must stay at 403 (AC4).
- inc-37-decide-<stamp>: its run reaches a pending mitigation through the real
  IncidentRuntime, so the war room must send the operator to Decisiones.

Requires DATABASE_URL on a migrated database (compose `migrate` runs first).
Authorization stays out of scope here: read and start grants belong to the demo
bundle, never to a global allow.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from sre_agent.application import INCIDENT_WORKFLOW_PATH  # noqa: E402
from sre_agent.incident.runtime import (  # noqa: E402
    ActorReference,
    IncidentCommand,
    IncidentRuntime,
)
from sre_agent.incident.workflow import load_incident_workflow  # noqa: E402
from sre_agent.persistence.database import Database  # noqa: E402
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
STAMP_PATTERN = re.compile(r"^[a-z0-9-]{4,32}$")
JOURNEYS = ("start", "double", "restricted")


def incident_state(stamp: str) -> dict:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "active",
        "severity": "sev2",
        "impact": "Checkout failing at payment.",
        "alert": {
            "alert_id": f"alt-37-{stamp}",
            "service": "paymentservice",
            "severity": "sev2",
            "status": "triaged",
            "observed_at": "2026-10-16T11:55:00Z",
            "summary": "Elevated error rate on paymentservice.",
            "source": "grafana-alerting",
        },
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": NOW.isoformat(),
    }


def decide_commands(incident_id: str, run_id: str) -> list[IncidentCommand]:
    """Start, a hypothesis citing evidence, then a pending simulated mitigation."""
    evidence = [{"evidence_id": "ev_37_5xx", "summary": "paymentservice 5xx above 5 %."}]
    hypothesis = {"hypothesis_id": "hyp_37", "supporting_evidence": ["ev_37_5xx"]}
    mitigation = {"mitigation_id": "mit_37", "approval_status": "pending"}
    agent = ActorReference(principal_id="incident-harness")

    def command(step: str, actor: str, **extra: Any) -> IncidentCommand:
        prefix = (f"cmd-37-{step}-{run_id}", incident_id, run_id, step, actor)
        return IncidentCommand(*prefix, actor_reference=agent if extra else None, **extra)

    hypothesize = {"hypotheses": [hypothesis], "evidence": evidence}
    propose = {"mitigation_strategy": mitigation, "evidence": evidence}
    return [
        command("start_investigation", "system"),
        command(
            "continue_investigation",
            "agent",
            outcome="continue_investigation",
            inputs={"remaining_step_budget": 2, "incident_patch": hypothesize},
        ),
        command(
            "propose_mitigation",
            "agent",
            outcome="propose_mitigation",
            inputs={"incident_patch": propose},
        ),
    ]


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    stamp = os.environ.get("SEED_STAMP", "")
    if not STAMP_PATTERN.fullmatch(stamp):
        raise SystemExit("SEED_STAMP must match ^[a-z0-9-]{4,32}$")
    database = Database(dsn)
    try:
        async with PostgresIncidentUnitOfWork(database) as work:
            for prefix in JOURNEYS:
                incident_id = f"inc-37-{prefix}-{stamp}"
                if await work.incidents.get(incident_id) is None:
                    await work.incidents.add(incident_id, incident_state(stamp), now=NOW)
                print(incident_id)
            decide = f"inc-37-decide-{stamp}"
            run_id = "run_" + hashlib.sha256(stamp.encode()).hexdigest()[:16]
            if await work.incidents.get(decide) is None:
                await work.incidents.add(decide, incident_state(stamp), now=NOW)
                run = {"workflow_version": "1.0.0", "current_state": "active", "status": "running"}
                await work.runs.add(run_id, decide, run, now=NOW)
        workflow = load_incident_workflow(INCIDENT_WORKFLOW_PATH)
        runtime = IncidentRuntime(
            workflow, lambda: PostgresIncidentUnitOfWork(database), clock=lambda: NOW
        )
        for command in decide_commands(decide, run_id):
            await runtime.execute(command)
        print(decide)
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
