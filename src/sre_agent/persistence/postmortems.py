"""PostgreSQL adapter for the versioned postmortem artifact (issue #335)."""

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.incident.persistence import IncidentStaleWriteError
from sre_agent.incident.postmortem import PostmortemRecord, PostmortemReview

_CURRENT = """SELECT p.postmortem_id, p.incident_id, p.version, p.run_ids, p.created_at,
  p.updated_at, r.content, r.edited_by,
  v.version AS review_version, v.outcome, v.reviewer_id, v.comment, v.reviewed_at
FROM incident.postmortems p
JOIN incident.postmortem_revisions r ON r.postmortem_id = p.postmortem_id AND r.version = p.version
LEFT JOIN LATERAL (SELECT * FROM incident.postmortem_reviews x
  WHERE x.postmortem_id = p.postmortem_id ORDER BY x.sequence DESC LIMIT 1) v ON true
WHERE p.incident_id = :incident_id"""


def _record(row: Mapping[str, Any]) -> PostmortemRecord:
    review = None
    if row["outcome"] is not None:
        review = PostmortemReview(
            version=row["review_version"],
            outcome=row["outcome"],
            reviewer_id=row["reviewer_id"],
            comment=row["comment"],
            reviewed_at=row["reviewed_at"],
        )
    return PostmortemRecord(
        postmortem_id=row["postmortem_id"],
        incident_id=row["incident_id"],
        version=row["version"],
        content=row["content"],
        run_ids=tuple(row["run_ids"]),
        updated_by=row["edited_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        review=review,
    )


class PostgresPostmortemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, incident_id: str, *, lock: bool = False) -> PostmortemRecord | None:
        """The current version and its latest review. ``lock`` serializes edits with close."""
        if lock:
            await self._session.execute(
                text(
                    "SELECT 1 FROM incident.postmortems WHERE incident_id=:incident_id FOR UPDATE"
                ),
                {"incident_id": incident_id},
            )
        found = await self._session.execute(text(_CURRENT), {"incident_id": incident_id})
        row = found.mappings().one_or_none()
        return _record(row) if row else None

    async def known_event_ids(self, incident_id: str, event_ids: Iterable[str]) -> frozenset[str]:
        statement = text(
            "SELECT event_id FROM incident.run_events "
            "WHERE incident_id=:incident_id AND event_id = ANY(:event_ids)"
        ).bindparams(bindparam("event_ids", type_=ARRAY(String())))
        rows = await self._session.execute(
            statement, {"incident_id": incident_id, "event_ids": list(event_ids)}
        )
        return frozenset(row[0] for row in rows)

    async def save(
        self,
        postmortem_id: str,
        incident_id: str,
        *,
        expected_version: int,
        content: Mapping[str, Any],
        run_ids: Sequence[str],
        actor_id: str,
        now: datetime,
    ) -> int:
        """Write the next version; ``expected_version`` 0 creates. Stale writes raise."""
        version = expected_version + 1
        values = {
            "postmortem_id": postmortem_id,
            "incident_id": incident_id,
            "expected": expected_version,
            "version": version,
            "run_ids": json.dumps(list(run_ids)),
            "now": now,
        }
        if expected_version == 0:
            statement = """INSERT INTO incident.postmortems
              (postmortem_id, incident_id, version, run_ids, created_at, updated_at)
              VALUES (:postmortem_id, :incident_id, 1, CAST(:run_ids AS jsonb), :now, :now)
              ON CONFLICT DO NOTHING RETURNING version"""
        else:
            statement = """UPDATE incident.postmortems SET version=:version,
              run_ids=CAST(:run_ids AS jsonb), updated_at=:now
              WHERE postmortem_id=:postmortem_id AND incident_id=:incident_id
                AND version=:expected RETURNING version"""
        if (await self._session.execute(text(statement), values)).scalar_one_or_none() is None:
            raise IncidentStaleWriteError(
                f"postmortem {postmortem_id} is not at {expected_version}"
            )
        await self._session.execute(
            text("""INSERT INTO incident.postmortem_revisions
              (postmortem_id, version, content, edited_by, edited_at)
              VALUES (:postmortem_id, :version, CAST(:content AS jsonb), :actor_id, :now)"""),
            {**values, "content": json.dumps(content, sort_keys=True), "actor_id": actor_id},
        )
        return version
