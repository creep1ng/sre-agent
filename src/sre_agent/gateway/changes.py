"""POST and GET /v1/changes: what changed in a service, and when (issue #770).

A change event is a deploy, a rollback or a CI result, sent by an integration (the reusable
GitHub Actions step in .github/actions/record-change, or the deploy-executor after a rollback).
``change.write`` gates the record and ``change.read`` the list, both over the incident workflow.
The source's own run id makes the record idempotent: resending the same
(source, external_id, service) with the same payload returns the stored event with 200 and adds
nothing, while the same key with a different payload answers 409, so a colliding key is never
dropped silently. Recording never opens an incident nor interrupts anyone; a failed CI run is
just a change with ``status: failed`` for the readers that weigh it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from sre_agent.gate.errors import AuthenticationFailed, GovernedError
from sre_agent.gate.pipeline import Admission, Gate, Refusals, Released, Scope, declare, failing_as

WORKFLOW = ("incident_workflow", "incident-response")
REFUSALS = Refusals(
    unauthenticated=AuthenticationFailed(),
    denied=GovernedError(403, "not_authorized"),
    unavailable=GovernedError(503, "storage_unavailable", retryable=True, retry_after="15"),
)
INVALID = GovernedError(422, "contract_validation_failed")
RECORD = declare("POST", "/v1/changes", action="change.write", resource_type=WORKFLOW[0],
                 resource_id=WORKFLOW[1])  # fmt: skip
LIST = declare("GET", "/v1/changes", action="change.read", resource_type=WORKFLOW[0],
               resource_id=WORKFLOW[1])  # fmt: skip
Service = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
# A clock a little ahead is tolerated; an event dated later than this is refused.
FUTURE_SKEW = timedelta(minutes=5)
_COLUMNS = (
    "change_id, source, external_id, service, kind, status, version, commit_sha, ref, author,"
    " url, occurred_at, recorded_at, recorded_by"
)
_INSERT = text(
    f"INSERT INTO incident.change_events ({_COLUMNS}) VALUES ("
    + ", ".join(f":{name.strip()}" for name in _COLUMNS.split(","))
    + f") ON CONFLICT ON CONSTRAINT uq_change_event_external DO NOTHING RETURNING {_COLUMNS}"
)
_STORED = text(
    f"SELECT {_COLUMNS} FROM incident.change_events"
    " WHERE source = :source AND external_id = :external_id AND service = :service"
)
_LIST = text(
    f"SELECT {_COLUMNS} FROM incident.change_events"
    " WHERE (CAST(:service AS text) IS NULL OR service = :service)"
    " AND (CAST(:since AS timestamptz) IS NULL OR occurred_at >= :since)"
    " AND (CAST(:until AS timestamptz) IS NULL OR occurred_at <= :until)"
    " ORDER BY occurred_at DESC, change_id LIMIT :limit"
)


class ChangeEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,31}$")]
    external_id: Annotated[str, Field(min_length=1, max_length=200)]
    service: Service
    kind: Literal["deploy", "rollback", "ci"]
    status: Literal["succeeded", "failed"] = "succeeded"
    version: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    commit_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{7,64}$")] | None = None
    ref: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    author: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    url: Annotated[str, Field(pattern=r"^https?://", max_length=500)] | None = None
    occurred_at: AwareDatetime | None = None


class ChangeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: Service | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _view(row: Any) -> dict[str, Any]:
    event = dict(row)
    event["occurred_at"], event["recorded_at"] = _iso(row["occurred_at"]), _iso(row["recorded_at"])
    return event


def validated(model: type[Any], raw: Any) -> Any:
    """The request as `model`, or the 422 naming each field that failed."""
    try:
        return model.model_validate(raw)
    except ValidationError as error:
        detail = "; ".join(
            ".".join(map(str, item["loc"])) + ": " + item["msg"] for item in error.errors()
        )
        raise INVALID.with_message(detail) if detail else INVALID from None


class ChangeEventsService:
    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions
        self._gate: Gate[Any] = Gate(sessions, REFUSALS)

    async def record(self, authorization: str | None, body: Any) -> Response:
        return await self._gate.run(
            RECORD,
            authorization,
            Scope("change.write", *WORKFLOW),
            self._record,
            validate=lambda: self._change(body),
        )

    @staticmethod
    def _change(body: Any) -> ChangeEventIn:
        event = validated(ChangeEventIn, body)
        if event.occurred_at is not None and event.occurred_at > datetime.now(UTC) + FUTURE_SKEW:
            raise INVALID.with_message("occurred_at: more than 5 minutes in the future")
        return event

    async def _record(self, admission: Admission, event: ChangeEventIn) -> Released:
        now = datetime.now(UTC)
        values = event.model_dump() | {
            "change_id": f"chg_{token_hex(8)}",
            "occurred_at": event.occurred_at or now,
            "recorded_at": now,
            "recorded_by": admission.context.principal.principal_id,
        }
        with failing_as(REFUSALS.unavailable):
            async with self._sessions() as session, session.begin():
                inserted = (await session.execute(_INSERT, values)).mappings().one_or_none()
                row = inserted or (await session.execute(_STORED, values)).mappings().one()
        # Without its own time, a resend keeps the stored one; every other field must match.
        sent = event.model_dump(exclude={"occurred_at"} if event.occurred_at is None else None)
        if inserted is None and any(row[name] != value for name, value in sent.items()):
            detail = "This (source, external_id, service) was recorded with another payload."
            raise GovernedError(409, "change_conflict", detail)
        return Released(
            {"change": _view(row), "created": inserted is not None,
             "request_id": str(admission.request_id)},
            status=201 if inserted is not None else 200,
        )  # fmt: skip

    async def list(self, authorization: str | None, params: dict[str, str]) -> Response:
        return await self._gate.run(
            LIST,
            authorization,
            Scope("change.read", *WORKFLOW),
            self._list,
            validate=lambda: validated(ChangeQuery, params),
        )

    async def _list(self, admission: Admission, query: ChangeQuery) -> Released:
        with failing_as(REFUSALS.unavailable):
            async with self._sessions() as session:
                rows = (await session.execute(_LIST, query.model_dump())).mappings()
                changes = [_view(row) for row in rows]
        return Released(
            {"changes": changes, "request_id": str(admission.request_id)},
            headers={"Cache-Control": "no-store"},
        )


def changes_router(service: ChangeEventsService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/changes")
    async def record_change(request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.record(request.headers.get("authorization"), body)

    @router.get("/v1/changes")
    async def list_changes(request: Request) -> Response:
        return await service.list(request.headers.get("authorization"), dict(request.query_params))

    return router
