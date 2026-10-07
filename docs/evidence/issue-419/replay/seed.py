import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from os import environ

import yaml

from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork

NOW = datetime.now(UTC) - timedelta(minutes=10)
MITIGATION = {
    "mitigation_id": "mit-disable-payment-flag",
    "description": "Disable the paymentFailure flag in flagd.",
    "steps": ["Ask the operator to set paymentFailure to off."],
    "risk": "low",
    "verification_check": "Payment error rate stays below one percent for ten minutes.",
    "approval_status": "pending",
    "execution_mode": "human",
    "created_by": "agent",
    "created_at": NOW.isoformat(),
}
FIXTURE = yaml.safe_load(Path("/fixtures/initial-state.yaml").read_text())
SCENARIOS = (
    ("inc-issue419-final-browser", "run_incissue419finalbrowser"),
    ("inc-issue419-final-mismatch", "run_incissue419finalmismatch"),
)

async def main() -> None:
    database = Database(environ["DATABASE_URL"])
    try:
        async with PostgresIncidentUnitOfWork(database) as work:
            for incident_id, run_id in SCENARIOS:
                document = deepcopy(FIXTURE)
                document.update(
                    state="mitigating",
                    incident_id=incident_id,
                    severity="sev2",
                    mitigation_strategy=dict(MITIGATION),
                    updated_at=NOW.isoformat(),
                )
                await work.incidents.add(incident_id, document, now=NOW)
                await work.runs.add(
                    run_id,
                    incident_id,
                    {
                        "workflow_version": "1.0.0",
                        "current_state": "mitigating",
                        "status": "awaiting_human",
                        "pending_command": "approve_mitigation",
                    },
                    now=NOW,
                )
    finally:
        await database.dispose()

asyncio.run(main())
print("seeded two synthetic incidents/runs using the existing tracked fixture pattern")
