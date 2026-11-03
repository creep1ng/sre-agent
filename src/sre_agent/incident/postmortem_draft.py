"""The agent's first postmortem draft of a resolved incident (#711).

Nothing is asked of a model: each section quotes the record it comes from (the alert, the
impact a person declared, the last hypothesis, the approved plan and what it ran, the
verification check) and the timeline cites the stored state changes. A person reads it,
approves it and closes the incident; what the draft does not know it says so.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from sre_agent.incident.persistence import RunEvent
from sre_agent.incident.postmortem import EVENT_ID_PATTERN, MAX_ITEMS, MAX_TEXT
from sre_agent.incident.projections import TRANSITION_SUMMARIES, event_summary

WORDS = {
    "es": {
        "summary": "Incidente declarado sin alerta registrada.",
        "impact": "Impacto no registrado.",
        "cause": "Causa no establecida.",
        "strategy": "Sin mitigación registrada.",
        "verification": "Se verificó que el servicio quedó estable.",
        "check": "Se verificó que el servicio quedó estable: {check}",
        "unknown": "La causa no se confirmó más allá de la hipótesis de la investigación.",
    },
    "en": {
        "summary": "Incident declared without a recorded alert.",
        "impact": "Impact not recorded.",
        "cause": "Cause not established.",
        "strategy": "No mitigation recorded.",
        "verification": "The service was verified stable.",
        "check": "The service was verified stable: {check}",
        "unknown": "The cause was not confirmed beyond the investigation's hypothesis.",
    },
}


def _text(value: Any, fallback: str) -> str:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) and value.strip() else fallback


def compose(state: Mapping[str, Any], events: Sequence[RunEvent], language: str) -> dict[str, Any]:
    """The draft's content, valid for `validate_content`, citing only the given events."""
    words = WORDS.get(language, WORDS["es"])
    alert = state.get("alert")
    alert = alert if isinstance(alert, Mapping) else {}
    hypotheses = [item for item in state.get("hypotheses") or () if isinstance(item, Mapping)]
    strategy = state.get("mitigation_strategy")
    strategy = strategy if isinstance(strategy, Mapping) else {}
    changes = [
        event
        for event in sorted(events, key=lambda event: (event.occurred_at, event.sequence))
        if re.fullmatch(EVENT_ID_PATTERN, event.event_id)
        and isinstance(event.payload, Mapping)
        and event.payload.get("transition_id") in TRANSITION_SUMMARIES
    ]
    cited = [
        {"event_id": event.event_id, "description": event_summary(event.payload)}
        for event in changes
    ]
    approvals = [item for item in cited if item["description"].startswith("Mitigation approved")]
    statement = hypotheses[-1].get("statement") if hypotheses else None
    check = strategy.get("verification_check")
    return {
        "summary": _text(alert.get("summary"), words["summary"]),
        "impact": _text(state.get("impact"), words["impact"]),
        "timeline": cited[-MAX_ITEMS:],
        "cause": {
            "statement": _text(statement, words["cause"]),
            # A mitigation built on it brought the service back: probable, not confirmed.
            "certainty": "probable" if statement else "unknown",
        },
        "strategy": _text(strategy.get("description"), words["strategy"]),
        "actions_taken": approvals[-1:],
        "verification": words["check"].format(check=check.strip())[:MAX_TEXT]
        if isinstance(check, str) and check.strip()
        else words["verification"],
        "pending": [],
        "unknowns": [words["unknown"]] if statement else [],
    }
