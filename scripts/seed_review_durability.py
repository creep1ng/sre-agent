"""Seed review-durability incidents for issue #41 slice 41b journeys.

Evidence-setup helper, not production bootstrap: creates three incidents with
one run each in mitigating/awaiting_human with a pending approve_mitigation,
mirroring the ``_seed`` helper in tests/test_incident_command_http.py. Takes
``--stamp`` so every capture run owns disposable ids and never depends on
residual data; reruns with the same stamp converge by skipping existing rows.
Requires DATABASE_URL on a migrated and seeded database (grants come from the
governed seed/provision path, never from here). Setup only: assertions about
application behavior live in tests/browser/review-durability.spec.js.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from sre_agent.persistence.database import Database  # noqa: E402
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork  # noqa: E402

INITIAL_STATE_PATH = (
    REPOSITORY_ROOT / "agent/fixtures/incidents/otel-payment-failure/initial-state.yaml"
)
MITIGATION = {
    "mitigation_id": "mit-disable-payment-flag",
    "description": "Disable the paymentFailure flag in flagd.",
    "steps": ["Ask the operator to set paymentFailure to off."],
    "risk": "low",
    "verification_check": "Payment error rate stays below one percent for ten minutes.",
    "approval_status": "pending",
    "execution_mode": "human",
    "created_by": "agent",
}


def _run_id(n: int, stamp: str) -> str:
    return f"run_41bj{n}001" + stamp.replace("-", "")


async def _seed(database_url: str, stamp: str) -> None:
    now = datetime.now(UTC)
    base = yaml.safe_load(INITIAL_STATE_PATH.read_text())
    database = Database(database_url)
    try:
        for n in (1, 2, 3):
            incident_id = f"inc-41b-j{n}-{stamp}"
            run_id = _run_id(n, stamp)
            document = dict(base)
            document.update(
                state="mitigating",
                incident_id=incident_id,
                severity="sev2",
                impact="Checkout failing at payment.",
                mitigation_strategy=dict(
                    MITIGATION, created_at=now.isoformat()
                ),
                updated_at=now.isoformat(),
            )
            async with PostgresIncidentUnitOfWork(database) as work:
                existing = await work.incidents.get(incident_id)
                if existing is not None:
                    print(f"exists {incident_id} {run_id}")
                    continue
                await work.incidents.add(incident_id, document, now=now)
                await work.runs.add(
                    run_id,
                    incident_id,
                    {
                        "workflow_version": "1.0.0",
                        "current_state": "mitigating",
                        "status": "awaiting_human",
                        "pending_command": "approve_mitigation",
                    },
                    now=now,
                )
            print(f"seeded {incident_id} {run_id}")
    finally:
        await database.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stamp", required=True, help="disposable id suffix, e.g. t9")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("seed_review_durability: DATABASE_URL is required", file=sys.stderr)
        return 2
    asyncio.run(_seed(database_url, args.stamp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
