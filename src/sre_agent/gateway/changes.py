"""POST and GET /v1/changes: what changed in a service, and when (issue #770).

A change event is a deploy, a rollback or a CI result, sent by an integration (the reusable
GitHub Actions step in .github/actions/record-change, or the deploy-executor after a rollback).
``change.write`` gates the record and ``change.read`` the list, both over the incident workflow.
The source's own run id makes the record idempotent: resending the same
(source, external_id, service) returns the stored event with 200 and adds nothing, so the
first write wins. Recording never opens an incident nor interrupts anyone; a failed CI run is
just a change with ``status: failed`` for the readers that weigh it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_hex
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access

WORKFLOW = ("incident_workflow", "incident-response")
Service = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
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
    limit: Annotated[int, Field(ge=1, le=100)] = 20


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _view(row: Any) -> dict[str, Any]:
    event = dict(row)
    event["occurred_at"], event["recorded_at"] = _iso(row["occurred_at"]), _iso(row["recorded_at"])
    return event


class ChangeEventsService:
    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions

    @staticmethod
    def _error(request_id: str, status: int, code: str, detail: str | None = None) -> JSONResponse:
        headers = {401: {"WWW-Authenticate": "Bearer"}, 503: {"Retry-After": "15"}}.get(status)
        error = {"code": code, "message": detail or code.replace("_", " ").capitalize() + "."}
        body = {"error": error, "request_id": request_id, "retryable": status == 503}
        return JSONResponse(body, status_code=status, headers=headers)

    def _invalid(self, request_id: str, error: ValidationError) -> JSONResponse:
        detail = "; ".join(
            ".".join(map(str, item["loc"])) + ": " + item["msg"] for item in error.errors()
        )
        return self._error(request_id, 422, "contract_validation_failed", detail or None)

    async def _authorize(self, request_id: str, authorization: str | None, action: str) -> Any:
        try:
            context, evaluation = await authorize_governed_access(
                self._sessions, authorization, action, *WORKFLOW
            )
        except AuthenticationFailed:
            return self._error(request_id, 401, "authentication_failed")
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        if evaluation.decision.decision != "allow":
            return self._error(request_id, 403, "not_authorized")
        return context

    async def record(self, authorization: str | None, body: Any) -> JSONResponse:
        request_id = str(uuid4())
        context = await self._authorize(request_id, authorization, "change.write")
        if isinstance(context, JSONResponse):
            return context
        try:
            event = ChangeEventIn.model_validate(body)
        except ValidationError as error:
            return self._invalid(request_id, error)
        now = datetime.now(UTC)
        values = event.model_dump() | {
            "change_id": f"chg_{token_hex(8)}",
            "occurred_at": event.occurred_at or now,
            "recorded_at": now,
            "recorded_by": context.principal.principal_id,
        }
        try:
            async with self._sessions() as session, session.begin():
                inserted = (await session.execute(_INSERT, values)).mappings().one_or_none()
                row = inserted or (await session.execute(_STORED, values)).mappings().one()
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        return JSONResponse(
            {"change": _view(row), "created": inserted is not None, "request_id": request_id},
            status_code=201 if inserted is not None else 200,
        )

    async def list(self, authorization: str | None, params: dict[str, str]) -> JSONResponse:
        request_id = str(uuid4())
        context = await self._authorize(request_id, authorization, "change.read")
        if isinstance(context, JSONResponse):
            return context
        try:
            query = ChangeQuery.model_validate(params)
        except ValidationError as error:
            return self._invalid(request_id, error)
        try:
            async with self._sessions() as session:
                rows = (await session.execute(_LIST, query.model_dump())).mappings()
                changes = [_view(row) for row in rows]
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        return JSONResponse(
            {"changes": changes, "request_id": request_id}, headers={"Cache-Control": "no-store"}
        )


def changes_router(service: ChangeEventsService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/changes")
    async def record_change(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.record(request.headers.get("authorization"), body)

    @router.get("/v1/changes")
    async def list_changes(request: Request) -> JSONResponse:
        return await service.list(request.headers.get("authorization"), dict(request.query_params))

    return router
