"""The daily digest: what Midnight decided without writing to you (issue #771).

Each digest covers the decisions taken since the previous one (or the last day), the period
GET /v1/event-decisions lists, and opens with «N eventos, M mensajes»: every event decided and
the immediate messages among them. A period with no event sends nothing. The gateway queues one
a day at TELEGRAM_DIGEST_HOUR; `python -m sre_agent.chat.telegram digest` queues one now.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_LINES = 15
_PREVIOUS = text("""SELECT max(CAST(payload ->> 'until' AS timestamptz))
    FROM incident.chat_outbox WHERE kind = 'daily_digest'""")
_QUEUE = text("""INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
    SELECT chat_id, 'daily_digest', :dedup_key, CAST(:payload AS jsonb) FROM incident.chat_links
    ON CONFLICT (chat_id, dedup_key) DO NOTHING""")
_DECIDED = text("""SELECT decision, title, reason, count(*) AS times
    FROM incident.event_decisions
    WHERE decided_at >= :since AND decided_at < :until AND decision IN ('interrupt', 'digest')
    GROUP BY decision, title, reason ORDER BY decision DESC, min(decided_at)""")
_TOTALS = text("""SELECT count(*), count(*) FILTER (WHERE decision = 'interrupt')
    FROM incident.event_decisions WHERE decided_at >= :since AND decided_at < :until""")


async def queue_digest(session: AsyncSession, until: datetime, timezone: str) -> bool:
    """Queue the digest of the decisions up to `until`; False when there is nothing to tell."""
    previous = await session.scalar(_PREVIOUS)
    if previous is not None and previous >= until:
        return False
    since = previous or until - timedelta(days=1)
    if not (await session.execute(_TOTALS, {"since": since, "until": until})).one()[0]:
        return False
    payload = {"since": since.isoformat(), "until": until.isoformat(), "timezone": timezone}
    key = f"daily_digest:{until.isoformat()}"
    await session.execute(_QUEUE, {"dedup_key": key, "payload": json.dumps(payload)})
    return True


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


async def render_digest(session: AsyncSession, payload: Mapping[str, Any]) -> str:
    zone = ZoneInfo(payload.get("timezone") or "UTC")
    since, until = (datetime.fromisoformat(payload[key]) for key in ("since", "until"))
    period = {"since": since, "until": until}
    events, messages = (await session.execute(_TOTALS, period)).one()
    lines = [
        f"Resumen: {_plural(events, 'evento')}, {_plural(messages, 'mensaje')}.",
        f"Del {since.astimezone(zone):%d/%m %H:%M} al {until.astimezone(zone):%d/%m %H:%M} "
        f"({zone.key}).",
    ]
    rows = (await session.execute(_DECIDED, period)).all()
    heading = None
    for row in rows[:MAX_LINES]:
        if row.decision != heading:
            heading = row.decision
            lines.append("Te escribí:" if heading == "interrupt" else "Sin escribirte:")
        repeated = f" (×{row.times})" if row.times > 1 else ""
        lines.append(f"• {row.title}{repeated} — {row.reason}")
    if len(rows) > MAX_LINES:
        lines.append(f"… y {len(rows) - MAX_LINES} más en GET /v1/event-decisions.")
    if not rows:
        lines.append("Nada que contar: todo lo demás quedó registrado sin avisarte.")
    return "\n".join(lines)
