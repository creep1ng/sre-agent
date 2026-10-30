"""Incident memory: closed incidents recalled when a new investigation starts (issue #773).

A closed incident enters memory in the same transaction as its close, from the postmortem
version a human approved. Each row is append-only and is the memory change log: what entered,
when, and from which incident, postmortem version and close event. Recall reuses the BoK's
PostgreSQL English full-text search (docs/bok-retrieval.md), only within the same service, and
only through the approved revision a citation links to: a memory without that source record
is never returned, so it can never be cited.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from secrets import token_hex
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SOURCE = "incident_memory"
RECALL_LIMIT = 3
MAX_CONTENT = 6000
# Recall hands over at most this much of each memory: 3 x 2000 characters per turn.
RECALL_CONTENT = 2000
_WORD = re.compile(r"[a-z0-9]{3,}")
_COLUMNS = """m.memory_id, m.incident_id, m.postmortem_id, m.postmortem_version,
  m.close_event_id, m.service, m.signal, m.content, m.indexed_at"""


@dataclass(frozen=True, slots=True)
class IncidentMemory:
    memory_id: str
    incident_id: str
    postmortem_id: str
    postmortem_version: int
    close_event_id: str
    service: str
    signal: str | None
    content: str
    indexed_at: datetime

    @property
    def source_record(self) -> str:
        """The approved postmortem this memory came from, as the API serves it."""
        return f"/v1/incidents/{self.incident_id}/postmortem"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def memory_content(state: Mapping[str, Any], postmortem: Mapping[str, Any]) -> str:
    """What the next investigation reads: the alert, the cause and what fixed it."""
    alert = _mapping(state.get("alert"))
    strategy = _mapping(state.get("mitigation_strategy"))
    cause = _mapping(postmortem.get("cause"))
    steps = [_text(step) for step in strategy.get("steps") or [] if _text(step)]
    lines = [
        f"Incident {_text(state.get('incident_id'))} on {_text(alert.get('service'))}, closed.",
        f"Alert: {_text(alert.get('summary'))}",
        f"Cause ({_text(cause.get('certainty'))}): {_text(cause.get('statement'))}",
        f"Mitigation approved: {_text(strategy.get('description'))}"
        + (f" Steps: {'; '.join(steps)}" if steps else ""),
        f"Postmortem strategy: {_text(postmortem.get('strategy'))}",
        f"Verification: {_text(postmortem.get('verification'))}",
        f"Summary: {_text(postmortem.get('summary'))}",
    ]
    return "\n".join(line for line in lines if not line.endswith(": "))[:MAX_CONTENT]


def recall_query(service: str, signal: str | None, summary: str) -> str:
    """Any word of the signal or the alert, in websearch syntax (`a or b`).

    The service's own words are left out: every memory of the service would match them.
    """
    words = dict.fromkeys(_WORD.findall(f"{signal or ''} {summary}".casefold()))
    skip = {"or", *_WORD.findall(service.casefold())}
    return " or ".join(word for word in list(words)[:40] if word not in skip)


def _memory(row: Any) -> IncidentMemory:
    return IncidentMemory(**{field: row[field] for field in IncidentMemory.__dataclass_fields__})


class PostgresIncidentMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def remember(
        self,
        state: Mapping[str, Any],
        approval: Mapping[str, Any],
        close_event_id: str,
        now: datetime,
    ) -> None:
        """Index the approved postmortem version of a closing incident; a replay adds nothing."""
        alert = _mapping(state.get("alert"))
        origin = _mapping(alert.get("origin"))
        postmortem = await self._session.scalar(
            text("""SELECT content FROM incident.postmortem_revisions
              WHERE postmortem_id=:postmortem_id AND version=:version"""),
            {"postmortem_id": approval["postmortem_id"], "version": approval["postmortem_version"]},
        )
        await self._session.execute(
            text("""INSERT INTO incident.incident_memories
              (memory_id, incident_id, postmortem_id, postmortem_version, close_event_id,
               service, signal, content, indexed_at)
              VALUES (:memory_id, :incident_id, :postmortem_id, :version, :close_event_id,
                      :service, :signal, :content, :now)
              ON CONFLICT (incident_id) DO NOTHING"""),
            {
                "memory_id": f"mem_{token_hex(8)}",
                "incident_id": state["incident_id"],
                "postmortem_id": approval["postmortem_id"],
                "version": approval["postmortem_version"],
                "close_event_id": close_event_id,
                "service": _text(alert.get("service")),
                "signal": _text(origin.get("signal")) or None,
                "content": memory_content(state, _mapping(postmortem)),
                "now": now,
            },
        )

    async def recall(
        self, service: str, signal: str | None, summary: str, incident_id: str
    ) -> list[IncidentMemory]:
        """Closed incidents of exactly this service: the same signal, or the alert's words.

        The same signal ranks first, then the text rank; another signal is not filtered out.
        """
        query = recall_query(service, signal, summary)
        if not query and not signal:
            return []
        rows = await self._session.execute(
            text(f"""SELECT {_COLUMNS} FROM incident.incident_memories m
              JOIN incident.postmortem_revisions r
                ON r.postmortem_id = m.postmortem_id AND r.version = m.postmortem_version
              CROSS JOIN websearch_to_tsquery('english', :query) q
              WHERE m.service = :service AND m.incident_id <> :incident_id
                AND (to_tsvector('english', m.content) @@ q
                     OR m.signal = CAST(:signal AS text))
              ORDER BY (m.signal IS NOT DISTINCT FROM CAST(:signal AS text)) DESC,
                       ts_rank_cd(to_tsvector('english', m.content), q) DESC,
                       m.indexed_at DESC, m.memory_id
              LIMIT :limit"""),
            {
                "query": query,
                "service": service,
                "signal": signal,
                "incident_id": incident_id,
                "limit": RECALL_LIMIT,
            },
        )
        return [_memory(row) for row in rows.mappings()]

    async def changes(self, limit: int = 100) -> list[IncidentMemory]:
        """The change log, newest first."""
        rows = await self._session.execute(
            text(f"""SELECT {_COLUMNS} FROM incident.incident_memories m
              ORDER BY m.indexed_at DESC, m.memory_id LIMIT :limit"""),
            {"limit": limit},
        )
        return [_memory(row) for row in rows.mappings()]
