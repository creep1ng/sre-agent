"""Seed the issue-37 T1 acceptance incidents for the war room run slice.

Evidence-only helper (not production bootstrap), stamped with SEED_STAMP so
reruns replay instead of duplicating: three incidents in `active` state with
severity and alert context and NO runs, one per acceptance journey:

- inc-37-start-<stamp>: the operator starts the investigation once (AC1, AC2).
- inc-37-double-<stamp>: a double click must create exactly one run (AC3).
- inc-37-restricted-<stamp>: restricted-harness must stay at 403 (AC4).

Requires DATABASE_URL on a migrated database (compose `migrate` runs first).
Authorization stays out of scope here: read and start grants belong to the demo
bundle, never to a global allow.
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
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
