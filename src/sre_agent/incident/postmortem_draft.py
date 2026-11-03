"""The record's side of a resolved incident's postmortem draft (#711).

`compose` writes a draft from what the incident recorded, without a model: each section quotes
the record it comes from (the alert, the impact a person declared, the last hypothesis, the
approved plan and what it ran, the verification check) and the timeline cites the stored state
changes. It is the fallback when the model's draft (`investigator/postmortem.py`) is missing, and
the source of everything the model does not write. `facts` is what that model is given.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from sre_agent.incident.persistence import RunEvent
from sre_agent.incident.postmortem import EVENT_ID_PATTERN, MAX_ITEMS, MAX_TEXT
from sre_agent.incident.projections import TRANSITION_SUMMARIES, event_summary

# The longest text of one fact the model is given (#711).
MAX_FACT = 600
# Who a draft composed from the record names as its author: no model wrote it (#711).
RECORD_AUTHOR = "system"

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


def _cut(value: Any) -> str | None:
    return value.strip()[:MAX_FACT] if isinstance(value, str) and value.strip() else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def facts(state: Mapping[str, Any], events: Sequence[RunEvent]) -> dict[str, Any]:
    """What the model may use: the alert, the impact, the last hypothesis, the measured
    evidence, the approved plan with what it ran, the check, and the state changes in order."""
    alert = _mapping(state.get("alert"))
    hypotheses = [item for item in state.get("hypotheses") or () if isinstance(item, Mapping)]
    strategy = _mapping(state.get("mitigation_strategy"))
    ran = _mapping(strategy.get("execution"))
    evidence = [_mapping(item) for item in state.get("evidence") or ()]
    moved = [e for e in events if _mapping(e.payload).get("transition_id") in TRANSITION_SUMMARIES]
    changes = sorted(moved, key=lambda event: (event.occurred_at, event.sequence))
    operation = strategy.get("operation")
    return {
        "alert": {key: _cut(alert.get(key)) for key in ("service", "severity", "summary")},
        "impact": _cut(state.get("impact")),
        "hypothesis": _cut(hypotheses[-1].get("statement")) if hypotheses else None,
        "evidence": [
            {
                "source": _cut(item.get("tool") or item.get("source")),
                "finding": _cut(item.get("finding") or item.get("summary")),
            }
            for item in evidence[-12:]
        ],
        "mitigation": {
            "plan": _cut(strategy.get("description")),
            "operation": operation if isinstance(operation, Mapping) else None,
            "ran": {key: _cut(ran.get(key)) for key in ("outcome", "before_image", "after_image")}
            if ran
            else None,
            "verification_check": _cut(strategy.get("verification_check")),
        },
        "state_changes": [event_summary(event.payload) for event in changes],
    }
