"""GET /v1/event-decisions: what Midnight decided about each event, and why (issue #771).

Every alert episode, resolution, change event and investigation result ends in one decision,
ignore, remember, digest or interrupt, recorded by the policy triggers of migration
20261030_771. This route lists them by the period in which they were decided, the same axis the
daily digest counts, so an inbox section and the digest agree on «N eventos, M mensajes».
``alert.read`` over the incident workflow gates it: the decisions describe the alerts. Each row
carries what an inbox renders (kind, service, time, decision, reason) and the API path of its
event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import text

from sre_agent.gate.pipeline import Admission, Released, Scope, declare, failing_as
from sre_agent.gateway.changes import (
    INVALID,
    REFUSALS,
    WORKFLOW,
    ChangeEventsService,
    validated,
)

DECISIONS = ("ignore", "remember", "digest", "interrupt")
LIST = declare("GET", "/v1/event-decisions", action="alert.read", resource_type=WORKFLOW[0],
               resource_id=WORKFLOW[1])  # fmt: skip
_LIST = text("""SELECT d.decision_id, d.event_kind, d.event_id, d.service,
    COALESCE(d.incident_id, e.incident_id) AS incident_id, d.title, d.occurred_at, d.decision,
    d.rule, d.reason, d.decided_at
    FROM incident.event_decisions d LEFT JOIN incident.alert_episodes e
      ON d.event_kind IN ('alert', 'resolution') AND e.episode_id = d.event_id
    WHERE d.decided_at >= :since AND d.decided_at < :until
      AND (CAST(:decision AS text) IS NULL OR d.decision = :decision)
    ORDER BY d.decided_at DESC, d.decision_id DESC LIMIT :limit""")
_COUNTS = text("""SELECT decision, count(*) FROM incident.event_decisions
    WHERE decided_at >= :since AND decided_at < :until GROUP BY decision""")


class DecisionQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    decision: Literal["ignore", "remember", "digest", "interrupt"] | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 100


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def event_link(row: Any) -> str:
    """The API path that shows the event itself."""
    match row["event_kind"]:
        case "alert" | "resolution":
            return f"/v1/alerts/{row['event_id']}/triage"
        case "investigation":
            return f"/v1/incidents/{row['incident_id']}/runs/{row['event_id']}"
        case _:
            # since = until = the change's own instant: the list holds that change.
            moment = row["occurred_at"].astimezone(UTC).isoformat()
            return "/v1/changes?" + urlencode(
                {"service": row["service"], "since": moment, "until": moment}
            )


def _view(row: Any) -> dict[str, Any]:
    decision = {key: row[key] for key in row.keys() if key not in ("occurred_at", "decided_at")}
    decision["occurred_at"], decision["decided_at"] = (
        _iso(row["occurred_at"]),
        _iso(row["decided_at"]),
    )
    return decision | {"link": event_link(row)}


class EventDecisionsService(ChangeEventsService):
    """Shares the change routes' gate and error bodies; only `list` is routed."""

    async def list(self, authorization: str | None, params: dict[str, str]) -> Response:
        return await self._gate.run(
            LIST,
            authorization,
            Scope("alert.read", *WORKFLOW),
            self._decisions,
            validate=lambda: self._period(params),
        )

    @staticmethod
    def _period(params: dict[str, str]) -> tuple[DecisionQuery, datetime, datetime]:
        query = validated(DecisionQuery, params)
        until = query.until or datetime.now(UTC)
        since = query.since or until - timedelta(days=1)
        if since >= until:
            raise INVALID.with_message("since: not < until")
        return query, since, until

    async def _decisions(
        self, admission: Admission, period: tuple[DecisionQuery, datetime, datetime]
    ) -> Released:
        query, since, until = period
        values = query.model_dump() | {"since": since, "until": until}
        with failing_as(REFUSALS.unavailable):
            async with self._sessions() as session:
                rows = (await session.execute(_LIST, values)).mappings().all()
                counts = dict((await session.execute(_COUNTS, values)).tuples().all())
        totals = {name: counts.get(name, 0) for name in DECISIONS}
        body = {
            "period": {"since": _iso(since), "until": _iso(until)},
            "counts": {"events": sum(totals.values()), "messages": totals["interrupt"]} | totals,
            "decisions": [_view(row) for row in rows],
            "request_id": str(admission.request_id),
        }
        return Released(body, headers={"Cache-Control": "no-store"})


def event_decisions_router(service: EventDecisionsService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/event-decisions")
    async def list_event_decisions(request: Request) -> Response:
        return await service.list(request.headers.get("authorization"), dict(request.query_params))

    return router
