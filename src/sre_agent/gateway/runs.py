"""Start and resume incident runs over HTTP (HT-INC-COMMANDS, issue #330).

Delivery lives in the gateway: bearer authentication, `run.start` on the pinned
workflow resource, idempotency taken from the request header, and the contract
error envelope. Every state rule, transition and unit of work stays in the
runtime (#26) and its authoritative store (#146): this module decides no state
change and owns no second state machine.

The actor comes from the authenticated credential. A body cannot name a
different actor, so a browser can never assert authority it was not granted.
"""

import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sre_agent.gateway.incidents import (
    RETRY_AFTER_SECONDS,
    WORKFLOW_RESOURCE_TYPE,
    IncidentWorkflowResourceReader,
)
from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationEvaluation,
)
from sre_agent.governance.dto import Principal
from sre_agent.incident.persistence import (
    IncidentIdempotencyConflictError,
    IncidentStaleWriteError,
    IncidentUnitOfWork,
)
from sre_agent.incident.projections import (
    IDENTIFIER_PATTERN,
    RUN_ID_PATTERN,
    UnsupportedWorkflowDataError,
    project_run_state,
)
from sre_agent.incident.runtime import (
    OBJECTIVE_TRANSITIONS,
    ActorReference,
    ApprovalRequiredError,
    IncidentNotFoundError,
    IncidentRuntime,
    InvalidTransitionError,
    PreconditionFailedError,
    RunNotFoundError,
    RunStart,
)
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository

START_ACTION = "run.start"
# The range the contract admits. The store follows it: migration 20260928_14
# widens transition_commits.command_id to varchar(200), so the boundary no
# longer refuses a key the contract allows, nor accepts one the store cannot
# hold.
IDEMPOTENCY_KEY_PATTERN = r"^\S{8,200}$"
START_REQUEST_FIELDS = frozenset({"workflow_version", "objective", "resume_from_run_id"})

ERRORS = {
    401: ("authentication_failed", "Authentication is required."),
    403: ("not_authorized", "The principal is not authorized to start runs on this workflow."),
    404: ("incident_not_found", "The requested incident was not found."),
    409: ("run_conflict", "The request conflicts with the current state of the run."),
    422: ("validation_error", "The request is invalid."),
    503: ("storage_unavailable", "Incident storage is temporarily unavailable."),
}
RUN_NOT_FOUND = ("run_not_found", "The requested incident run was not found.")

Authorizer = Callable[[Any, Principal], Awaitable[AuthorizationEvaluation]]


class RunStartService:
    """Open a run for an objective, or return the run a caller asks to resume."""

    def __init__(
        self,
        sessions: Any,
        workflow: IncidentWorkflow,
        runtime: IncidentRuntime,
        units: Callable[[], IncidentUnitOfWork],
        authorizer: Authorizer | None = None,
    ) -> None:
        self.sessions, self.workflow, self.runtime, self.units = sessions, workflow, runtime, units
        self._authorizer = authorizer or self._default_authorizer

    async def _default_authorizer(
        self, session: Any, principal: Principal
    ) -> AuthorizationEvaluation:
        engine = AuthorizationDecisionEngine(
            IncidentWorkflowResourceReader(self.workflow), GrantRepository(session)
        )
        return await engine.evaluate(
            principal, START_ACTION, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
        )

    def _error(
        self,
        request_id: UUID,
        status: int,
        code_and_message: tuple[str, str] | None = None,
    ) -> JSONResponse:
        code, message = code_and_message or ERRORS[status]
        response = JSONResponse(
            {
                "error": {"code": code, "message": message},
                "request_id": str(request_id),
                "retryable": status == 503,
            },
            status,
        )
        if status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        if status == 503:
            response.headers["Retry-After"] = RETRY_AFTER_SECONDS
        return response

    async def _authorized_principal(
        self, request_id: UUID, authorization: str | None
    ) -> tuple[Principal | None, JSONResponse | None]:
        scheme, separator, key = authorization.partition(" ") if authorization else ("", "", "")
        if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
            return None, self._error(request_id, 401)
        try:
            async with self.sessions() as session:
                context = await CredentialRepository(session).authenticate(key)
                if context is None:
                    return None, self._error(request_id, 401)
                evaluation = await self._authorizer(session, context.principal)
        except Exception:
            return None, self._error(request_id, 503)
        if evaluation.decision.decision != "allow":
            return None, self._error(request_id, 403)
        return context.principal, None

    def _invalid_request(self, incident_id: str, idempotency_key: str | None, body: Any) -> bool:
        if re.fullmatch(IDENTIFIER_PATTERN, incident_id) is None:
            return True
        if idempotency_key is None:
            return True
        if re.fullmatch(IDEMPOTENCY_KEY_PATTERN, idempotency_key) is None:
            return True
        if not isinstance(body, dict) or not set(body) <= START_REQUEST_FIELDS:
            return True
        if body.get("workflow_version") != self.workflow.version:
            return True
        objective = body.get("objective")
        if not isinstance(objective, str) or objective not in OBJECTIVE_TRANSITIONS:
            return True
        resume = body.get("resume_from_run_id")
        return resume is not None and re.fullmatch(RUN_ID_PATTERN, str(resume)) is None

    async def start(
        self,
        incident_id: str,
        body: Any,
        authorization: str | None,
        idempotency_key: str | None,
    ) -> JSONResponse:
        request_id = uuid4()
        if self._invalid_request(incident_id, idempotency_key, body):
            return self._error(request_id, 422)
        principal, error = await self._authorized_principal(request_id, authorization)
        if error is not None:
            return error
        assert principal is not None and idempotency_key is not None
        resume = body.get("resume_from_run_id")
        if resume is not None:
            return await self._resume(request_id, incident_id, str(resume))
        return await self._open(request_id, incident_id, body, principal, idempotency_key)

    async def _open(
        self,
        request_id: UUID,
        incident_id: str,
        body: dict[str, Any],
        principal: Principal,
        idempotency_key: str,
    ) -> JSONResponse:
        human = principal.kind == "human"
        try:
            result = await self.runtime.start_run(
                RunStart(
                    command_id=idempotency_key,
                    incident_id=incident_id,
                    objective=str(body["objective"]),
                    actor="human" if human else "agent",
                    actor_reference=(
                        ActorReference(principal_id=principal.principal_id) if human else None
                    ),
                )
            )
        except IncidentNotFoundError:
            return self._error(request_id, 404)
        except RunNotFoundError:
            return self._error(request_id, 404, RUN_NOT_FOUND)
        except (
            ApprovalRequiredError,
            IncidentIdempotencyConflictError,
            IncidentStaleWriteError,
            InvalidTransitionError,
            PreconditionFailedError,
        ):
            return self._error(request_id, 409)
        except Exception:
            return self._error(request_id, 503)
        sequence = max((event.sequence for event in result.events), default=-1)
        try:
            payload = project_run_state(result.run, self.workflow, event_sequence=sequence)
        except UnsupportedWorkflowDataError:
            return self._error(request_id, 422)
        return JSONResponse(payload, 200 if result.replayed else 201)

    async def _resume(self, request_id: UUID, incident_id: str, run_id: str) -> JSONResponse:
        """Return the run the caller asks to resume, from the authoritative store.

        Resuming reads: the run keeps its identity and its correlation, and the
        caller drives it further with commands. Nothing is transitioned here.
        """

        try:
            async with self.units() as work:
                incident = await work.incidents.get(incident_id)
                if incident is None:
                    return self._error(request_id, 404)
                run = await work.runs.get(run_id)
                if run is None or run.incident_id != incident_id:
                    return self._error(request_id, 404, RUN_NOT_FOUND)
                snapshot = await work.snapshots.latest(run_id)
                # The state comes from the run record, which reflects every
                # committed transition; snapshots are taken periodically, so the
                # last one can lag behind it. Reading the events after the
                # snapshot gives a cursor for the state actually returned, and a
                # consumer that continues from it never re-applies what it can
                # already see.
                covered = snapshot.event_sequence if snapshot is not None else -1
                later = await work.events.list_after(run_id, sequence=covered)
                sequence = later[-1].sequence if later else covered
        except Exception:
            return self._error(request_id, 503)
        try:
            payload = project_run_state(run, self.workflow, event_sequence=sequence)
        except UnsupportedWorkflowDataError:
            return self._error(request_id, 422)
        return JSONResponse(payload, 200)


def runs_router(service: RunStartService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/incidents/{incident_id}/runs")
    async def start_run(incident_id: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.start(
            incident_id,
            body,
            request.headers.get("authorization"),
            request.headers.get("idempotency-key"),
        )

    return router
