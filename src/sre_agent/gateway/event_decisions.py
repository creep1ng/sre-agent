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
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from sre_agent.gateway.changes import ChangeEventsService

DECISIONS = ("ignore", "remember", "digest", "interrupt")
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
    """Reuses the change routes' authorization and error bodies; only `list` is routed."""

    async def list(self, authorization: str | None, params: dict[str, str]) -> JSONResponse:
        request_id = str(uuid4())
        context = await self._authorize(request_id, authorization, "alert.read")
        if isinstance(context, JSONResponse):
            return context
        try:
            query = DecisionQuery.model_validate(params)
        except ValidationError as error:
            return self._invalid(request_id, error)
        until = query.until or datetime.now(UTC)
        since = query.since or until - timedelta(days=1)
        if since >= until:
            return self._error(request_id, 422, "contract_validation_failed", "since: not < until")
        values = query.model_dump() | {"since": since, "until": until}
        try:
            async with self._sessions() as session:
                rows = (await session.execute(_LIST, values)).mappings().all()
                counts = dict((await session.execute(_COUNTS, values)).tuples().all())
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        totals = {name: counts.get(name, 0) for name in DECISIONS}
        body = {
            "period": {"since": _iso(since), "until": _iso(until)},
            "counts": {"events": sum(totals.values()), "messages": totals["interrupt"]} | totals,
            "decisions": [_view(row) for row in rows],
            "request_id": request_id,
        }
        return JSONResponse(body, headers={"Cache-Control": "no-store"})


def event_decisions_router(service: EventDecisionsService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/event-decisions")
    async def list_event_decisions(request: Request) -> JSONResponse:
        return await service.list(request.headers.get("authorization"), dict(request.query_params))

    return router
