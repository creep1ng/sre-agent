"""The agent investigates again after a failed verification (#710, maintainer 2026-11-03).

A failed verification, the agent's (#723) or a person's «Sigue fallando», returns the incident to
`investigating` and ends its run. The dispatcher then starts a new run as the system, at most
`MAX_REINVESTIGATIONS` times per incident, each told what ran and failed; after that it stops and
writes to the linked chats that a person is needed. Everything here is read from the incident's
own events: the `verification_failed` state change keeps the mitigation that ran.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from sre_agent.chat.outbox import enqueue
from sre_agent.incident.persistence import IncidentUnitOfWork, RunEvent
from sre_agent.investigator.contract import FailedMitigation

MAX_REINVESTIGATIONS = 2
# What the new run is told when a person, not the agent, judged the verification.
PERSON_SAID = "A person reported that the service still fails after it ran."


def _verdict(events: list[RunEvent], failed: RunEvent) -> str:
    """The agent's verdict that failed it, from the same run; else a person's."""
    for event in reversed(events):
        outcome = event.payload.get("outcome") if event.kind == "investigation_result" else None
        if (
            event.run_id == failed.run_id
            and event.sequence < failed.sequence
            and isinstance(outcome, Mapping)
            and outcome.get("action") == "verify_mitigation"
            and outcome.get("passed") is False
            and outcome.get("summary")
        ):
            return str(outcome["summary"])[:2000]
    return PERSON_SAID


async def failed_mitigations(work: IncidentUnitOfWork, incident_id: str) -> list[FailedMitigation]:
    """Every mitigation of the incident that ran and whose verification failed, oldest first."""
    events = [
        event
        for run_id in await work.runs.list_ids(incident_id)
        for event in await work.events.list_after(run_id)
    ]
    events.sort(key=lambda event: (event.occurred_at, event.sequence))
    found: list[FailedMitigation] = []
    for event in events:
        if event.kind != "state_change" or event.payload.get("transition_id") != (
            "verification_failed"
        ):
            continue
        state: Any = event.payload.get("incident_state") or {}
        strategy = state.get("mitigation_strategy") if isinstance(state, Mapping) else None
        if not isinstance(strategy, Mapping) or not strategy.get("description"):
            continue
        found.append(
            FailedMitigation(
                description=str(strategy["description"])[:4000],
                operation=strategy.get("operation"),
                verification=_verdict(events, event),
            )
        )
    return found[-8:]


async def notify_gave_up(sessions: Any, incident_id: str, failed: int) -> None:
    """Wake the linked chats once: the retries are spent and a person decides what follows."""
    async with sessions() as session, session.begin():
        chats = (await session.execute(text("SELECT chat_id FROM incident.chat_links"))).all()
        for (chat_id,) in chats:
            await enqueue(
                session,
                chat_id=chat_id,
                kind="reinvestigation_exhausted",
                dedup_key=f"reinvestigation_exhausted:{incident_id}",
                payload={"incident_id": incident_id, "failed": failed},
            )
