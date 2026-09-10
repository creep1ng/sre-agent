# ruff: noqa: E501, I001
"""Authoritative incident query endpoints: detail, timeline and public snapshot (HT-INC-RUNTIME-B, issue #189).

Delivery lives in the gateway: bearer authentication, workflow-scoped
authorization (run.read on incident_workflow, pinned workflow as the stable
resource fact so no business joins cross into gateway tables) and the
contract error envelope. Read projections come from
sre_agent.incident.projections; reads never mutate aggregates.
"""

import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationEvaluation,
    ResourceAuthorizationFact,
)
from sre_agent.governance.dto import Principal, PrincipalContext, ResourceType
from sre_agent.incident.persistence import IncidentRecord, IncidentUnitOfWork, RunRecord
from sre_agent.incident.projections import (
    IDENTIFIER_PATTERN,
    RUN_ID_PATTERN,
    MissingDecisionError,
    UnsupportedWorkflowDataError,
    decode_cursor,
    encode_cursor,
    project_detail,
    project_event,
    project_snapshot,
)
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository

WORKFLOW_RESOURCE_TYPE: ResourceType = "incident_workflow"
READ_ACTION = "run.read"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
RETRY_AFTER_SECONDS = "5"

ERRORS = {
    401: ("authentication_failed", "Authentication is required."),
    403: ("not_authorized", "The principal is not authorized to read this incident."),
    404: ("incident_not_found", "The requested incident was not found."),
    422: ("validation_error", "The request is invalid."),
    503: ("storage_unavailable", "Incident storage is temporarily unavailable."),
}
NOT_FOUND_CODES = {
    "run_absent": "The incident has no runs yet.",
    "run_not_found": "The requested incident run was not found.",
    "snapshot_absent": "No snapshot exists for this run yet.",
}


class IncidentWorkflowResourceReader:
    """Resource facts for the pinned workflow without touching gateway tables."""

    def __init__(self, workflow: IncidentWorkflow) -> None:
        self._workflow = workflow

    async def authorization_view(
        self, resource_type: str, resource_id: str
    ) -> ResourceAuthorizationFact | None:
        if (resource_type, resource_id) == (
            WORKFLOW_RESOURCE_TYPE,
            self._workflow.workflow_id,
        ):
            return ResourceAuthorizationFact(WORKFLOW_RESOURCE_TYPE, resource_id, "active")
        return None


Authorizer = Callable[[Any, Principal], Awaitable[AuthorizationEvaluation]]


class IncidentQueryService:
    """Read-only incident queries over the authoritative unit of work."""

    def __init__(
        self,
        sessions: Any,
        workflow: IncidentWorkflow,
        units: Callable[[], IncidentUnitOfWork],
        authorizer: Authorizer | None = None,
    ) -> None:
        self.sessions, self.workflow, self.units = sessions, workflow, units
        self._authorizer = authorizer or self._default_authorizer

    async def _default_authorizer(self, session: Any, principal: Principal) -> AuthorizationEvaluation:  # fmt: skip
        engine = AuthorizationDecisionEngine(
            IncidentWorkflowResourceReader(self.workflow), GrantRepository(session)
        )
        return await engine.evaluate(
            principal, READ_ACTION, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
        )

    async def _authenticate(self, authorization: str | None) -> PrincipalContext | None:
        scheme, separator, key = authorization.partition(" ") if authorization else ("", "", "")
        if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
            return None
        async with self.sessions() as session:
            return await CredentialRepository(session).authenticate(key)

    def _error(
        self,
        request_id: UUID,
        status: int,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        default_code, message = ERRORS[status][0], ERRORS[status][1]
        code = code or default_code
        if code in NOT_FOUND_CODES:
            message = NOT_FOUND_CODES[code]
        response = JSONResponse(
            {
                "error": {"code": code, "message": message},
                "request_id": str(request_id),
                "retryable": status == 503,
            },
            status,
        )
        merged = dict(headers or {})
        if status == 503:
            merged.setdefault("Retry-After", RETRY_AFTER_SECONDS)
        for name, value in merged.items():
            response.headers[name] = value
        return response

    async def _authorized_principal(
        self, request_id: UUID, authorization: str | None
    ) -> tuple[Principal | None, JSONResponse | None]:
        context = await self._authenticate(authorization)
        if context is None:
            return None, self._error(request_id, 401, headers={"WWW-Authenticate": "Bearer"})
        try:
            async with self.sessions() as session:
                evaluation = await self._authorizer(session, context.principal)
        except Exception:
            return None, self._error(request_id, 503)
        if evaluation.decision.decision != "allow":
            return None, self._error(request_id, 403)
        return context.principal, None

    @staticmethod
    def _valid_identifier(value: str, pattern: str) -> bool:
        return re.fullmatch(pattern, value) is not None

    async def _incident_or_error(
        self, request_id: UUID, incident_id: str
    ) -> tuple[IncidentRecord | None, JSONResponse | None]:
        try:
            async with self.units() as work:
                record = await work.incidents.get(incident_id)
        except Exception:
            return None, self._error(request_id, 503)
        if record is None:
            return None, self._error(request_id, 404, "incident_not_found")
        return record, None

    async def _resolve_run(
        self, request_id: UUID, incident_id: str, run_id: str | None
    ) -> tuple[RunRecord | None, JSONResponse | None]:
        try:
            async with self.units() as work:
                if run_id is not None:
                    run = await work.runs.get(run_id)
                    if run is None or run.incident_id != incident_id:
                        return None, self._error(request_id, 404, "run_not_found")
                    return run, None
                run_ids = await work.runs.list_ids(incident_id)
                if not run_ids:
                    return None, self._error(request_id, 404, "run_absent")
                run = await work.runs.get(run_ids[-1])
                if run is None:
                    return None, self._error(request_id, 404, "run_not_found")
                return run, None
        except Exception:
            return None, self._error(request_id, 503)

    async def get_detail(self, incident_id: str, authorization: str | None) -> JSONResponse:
        request_id = uuid4()
        if not self._valid_identifier(incident_id, IDENTIFIER_PATTERN):
            return self._error(request_id, 422)
        _, error = await self._authorized_principal(request_id, authorization)
        if error is not None:
            return error
        record, error = await self._incident_or_error(request_id, incident_id)
        if error is not None:
            return error
        assert record is not None
        try:
            async with self.units() as work:
                run_ids = await work.runs.list_ids(incident_id)
                fetched = [await work.runs.get(run_id) for run_id in run_ids]
            runs = [run for run in fetched if run is not None]
            payload = project_detail(record, runs, self.workflow)
        except UnsupportedWorkflowDataError:
            return self._error(request_id, 422, "validation_error")
        except Exception:
            return self._error(request_id, 503)
        return JSONResponse(payload, status_code=200)

    async def get_timeline(
        self,
        incident_id: str,
        run_id: str | None,
        after: str | None,
        limit: Any,
        authorization: str | None,
    ) -> JSONResponse:
        request_id = uuid4()
        if not self._valid_identifier(incident_id, IDENTIFIER_PATTERN):
            return self._error(request_id, 422)
        if run_id is not None and not self._valid_identifier(run_id, RUN_ID_PATTERN):
            return self._error(request_id, 422)
        try:
            parsed_limit = int(limit) if limit is not None else DEFAULT_LIMIT
        except (TypeError, ValueError):
            return self._error(request_id, 422)
        if not 1 <= parsed_limit <= MAX_LIMIT:
            return self._error(request_id, 422)
        try:
            sequence = decode_cursor(after)
        except ValueError:
            return self._error(request_id, 422, "invalid_cursor")
        _, error = await self._authorized_principal(request_id, authorization)
        if error is not None:
            return error
        record, error = await self._incident_or_error(request_id, incident_id)
        if error is not None:
            return error
        run, error = await self._resolve_run(request_id, incident_id, run_id)
        if error is not None:
            return error
        assert run is not None
        try:
            async with self.units() as work:
                stored = await work.events.list_after(
                    run.run_id, sequence=sequence, limit=parsed_limit + 1
                )
                decisions: dict[str, Any] = {}
                for event in stored[:parsed_limit]:
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    decision_id = payload.get("decision_id")
                    if isinstance(decision_id, str) and decision_id not in decisions:
                        decision = await work.decisions.get(decision_id)
                        decisions[decision_id] = decision.document if decision is not None else None
                page = []
                for event in stored[:parsed_limit]:
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    decision_id = payload.get("decision_id")
                    document = decisions.get(decision_id) if isinstance(decision_id, str) else None
                    page.append(project_event(event, document))
        except (MissingDecisionError, UnsupportedWorkflowDataError):
            return self._error(request_id, 503)
        except Exception:
            return self._error(request_id, 503)
        watermark = max([sequence] + [item["sequence"] for item in page])
        return JSONResponse(
            {
                "events": page,
                "next_cursor": encode_cursor(watermark),
                "has_more": len(stored) > parsed_limit,
            },
            status_code=200,
        )

    async def get_snapshot(
        self, incident_id: str, run_id: str | None, authorization: str | None
    ) -> JSONResponse:
        request_id = uuid4()
        if not self._valid_identifier(incident_id, IDENTIFIER_PATTERN):
            return self._error(request_id, 422)
        if run_id is not None and not self._valid_identifier(run_id, RUN_ID_PATTERN):
            return self._error(request_id, 422)
        _, error = await self._authorized_principal(request_id, authorization)
        if error is not None:
            return error
        record, error = await self._incident_or_error(request_id, incident_id)
        if error is not None:
            return error
        run, error = await self._resolve_run(request_id, incident_id, run_id)
        if error is not None:
            return error
        assert record is not None
        assert run is not None
        try:
            async with self.units() as work:
                snapshot = await work.snapshots.latest(run.run_id)
                if snapshot is None:
                    return self._error(request_id, 404, "snapshot_absent")
                run_ids = await work.runs.list_ids(incident_id)
                fetched = [await work.runs.get(candidate) for candidate in run_ids]
            runs = [candidate for candidate in fetched if candidate is not None]
            detail = project_detail(record, runs, self.workflow)
            payload = project_snapshot(snapshot, detail, run)
        except UnsupportedWorkflowDataError:
            return self._error(request_id, 422, "validation_error")
        except Exception:
            return self._error(request_id, 503)
        return JSONResponse(payload, status_code=200)


def incident_router(service: IncidentQueryService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/incidents/{incident_id}")
    async def detail(incident_id: str, request: Request) -> JSONResponse:
        return await service.get_detail(incident_id, request.headers.get("authorization"))

    @router.get("/v1/incidents/{incident_id}/timeline")
    async def timeline(incident_id: str, request: Request) -> JSONResponse:
        params = request.query_params
        return await service.get_timeline(
            incident_id,
            params.get("run_id"),
            params.get("after"),
            params.get("limit"),
            request.headers.get("authorization"),
        )

    @router.get("/v1/incidents/{incident_id}/snapshot")
    async def snapshot(incident_id: str, request: Request) -> JSONResponse:
        return await service.get_snapshot(
            incident_id,
            request.query_params.get("run_id"),
            request.headers.get("authorization"),
        )

    return router
