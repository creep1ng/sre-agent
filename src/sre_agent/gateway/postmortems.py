"""Write, review and read the incident postmortem over HTTP (issue #335, first cut).

The gateway authenticates, asks the engine for the action and shapes the
response; the artifact rules live in `sre_agent.incident.postmortem` and the
close rule in the runtime. Writers and reviewers are the authenticated human,
never a name in the body. Reading the progress (`run.read`) is not reading the
text: content and review comments leave only with `run.read_context`.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sre_agent.gateway.incidents import WORKFLOW_RESOURCE_TYPE, IncidentWorkflowResourceReader
from sre_agent.gateway.runs import error_envelope
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import Principal
from sre_agent.incident.persistence import IncidentStaleWriteError, IncidentUnitOfWork
from sre_agent.incident.postmortem import (
    REVIEW_OUTCOMES,
    InvalidPostmortemError,
    PostmortemRecord,
    validate_content,
)
from sre_agent.incident.projections import IDENTIFIER_PATTERN
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.memories import PostgresIncidentMemoryRepository
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository

WRITE_ACTION, REVIEW_ACTION, READ_ACTION, CONTENT_ACTION = (
    "run.command",
    "run.approve",
    "run.read",
    "run.read_context",
)
MAX_COMMENT = 2000
DENIED = ("not_authorized", "The principal is not authorized for this postmortem operation.")
NOT_OPEN = ("postmortem_not_open", "The incident is not in the postmortem state.")
NOT_FOUND = ("postmortem_not_found", "The incident has no persisted postmortem.")
CONFLICT = ("postmortem_version_conflict", "The postmortem changed; reload the current version.")
UNKNOWN_EVENT = ("unknown_event_reference", "A cited event does not exist in this incident.")


def project(record: PostmortemRecord, *, with_content: bool) -> dict[str, Any]:
    """Allow-listed fields. Text (content, review comment) only for content readers."""
    review = record.review
    current = review is not None and review.version == record.version
    payload: dict[str, Any] = {
        "postmortem_id": record.postmortem_id,
        "incident_id": record.incident_id,
        "version": record.version,
        "run_ids": list(record.run_ids),
        "updated_by": record.updated_by,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "review": {
            "status": review.outcome if review is not None and current else "pending",
            "reviewed_version": review.version if review is not None else None,
            "reviewer_id": review.reviewer_id if review is not None else None,
            "reviewed_at": review.reviewed_at.isoformat() if review is not None else None,
        },
        "content_included": with_content,
    }
    if with_content:
        payload["content"] = record.content
        payload["review"]["comment"] = review.comment if review is not None else None
    return payload


class PostmortemService:
    def __init__(
        self,
        sessions: Any,
        workflow: IncidentWorkflow,
        units: Callable[[], IncidentUnitOfWork],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions, self.workflow, self.units, self.clock = sessions, workflow, units, clock

    async def _principal(
        self, request_id: UUID, authorization: str | None, actions: tuple[str, ...]
    ) -> tuple[Principal | None, frozenset[str], JSONResponse | None]:
        """Authenticate and evaluate each action; the first one is required."""
        scheme, separator, key = authorization.partition(" ") if authorization else ("", "", "")
        if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
            return None, frozenset(), error_envelope(request_id, 401)
        allowed: set[str] = set()
        try:
            async with self.sessions() as session:
                context = await CredentialRepository(session).authenticate(key)
                if context is None:
                    return None, frozenset(), error_envelope(request_id, 401)
                engine = AuthorizationDecisionEngine(
                    IncidentWorkflowResourceReader(self.workflow), GrantRepository(session)
                )
                for action in actions:
                    evaluation = await engine.evaluate(
                        context.principal, action, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
                    )
                    if evaluation.decision.decision == "allow":
                        allowed.add(action)
        except Exception:
            return None, frozenset(), error_envelope(request_id, 503)
        if actions[0] not in allowed:
            return None, frozenset(), error_envelope(request_id, 403, DENIED)
        return context.principal, frozenset(allowed), None

    async def _human(
        self, request_id: UUID, authorization: str | None, action: str
    ) -> tuple[Principal | None, JSONResponse | None]:
        principal, _, error = await self._principal(request_id, authorization, (action,))
        if error is None and principal is not None and principal.kind != "human":
            return None, error_envelope(request_id, 403, DENIED)
        return principal, error

    async def write(self, incident_id: str, body: Any, authorization: str | None) -> JSONResponse:
        request_id = uuid4()
        version = body.get("expected_version") if isinstance(body, dict) else None
        if (
            re.fullmatch(IDENTIFIER_PATTERN, incident_id) is None
            or not isinstance(body, dict)
            or set(body) != {"expected_version", "content"}
            or type(version) is not int
            or version < 0
        ):
            return error_envelope(request_id, 422)
        try:
            cited = validate_content(body["content"])
        except InvalidPostmortemError as error:
            return error_envelope(request_id, 422, ("invalid_postmortem", str(error)))
        principal, error = await self._human(request_id, authorization, WRITE_ACTION)
        if error is not None:
            return error
        assert principal is not None
        try:
            async with self.units() as work:
                await work.postmortems.get(incident_id, lock=True)
                incident = await work.incidents.get(incident_id)
                if incident is None:
                    return error_envelope(request_id, 404)
                reserved = incident.state.get("postmortem") or {}
                if incident.state.get("state") != "postmortem" or not reserved.get("postmortem_id"):
                    return error_envelope(request_id, 409, NOT_OPEN)
                if cited - await work.postmortems.known_event_ids(incident_id, cited):
                    return error_envelope(request_id, 422, UNKNOWN_EVENT)
                await work.postmortems.save(
                    reserved["postmortem_id"],
                    incident_id,
                    expected_version=version,
                    content=body["content"],
                    run_ids=await work.runs.list_ids(incident_id),
                    actor_id=principal.principal_id,
                    now=self.clock(),
                )
                record = await work.postmortems.get(incident_id)
        except IncidentStaleWriteError:
            return error_envelope(request_id, 409, CONFLICT)
        except Exception:
            return error_envelope(request_id, 503)
        assert record is not None
        return JSONResponse(project(record, with_content=False), 201 if version == 0 else 200)

    async def review(self, incident_id: str, body: Any, authorization: str | None) -> JSONResponse:
        request_id = uuid4()
        version = body.get("version") if isinstance(body, dict) else None
        comment = body.get("comment") if isinstance(body, dict) else None
        if (
            re.fullmatch(IDENTIFIER_PATTERN, incident_id) is None
            or not isinstance(body, dict)
            or not {"version", "outcome"} <= set(body) <= {"version", "outcome", "comment"}
            or type(version) is not int
            or version < 1
            or body["outcome"] not in REVIEW_OUTCOMES
            or (
                comment is not None and (not isinstance(comment, str) or len(comment) > MAX_COMMENT)
            )
        ):
            return error_envelope(request_id, 422)
        principal, error = await self._human(request_id, authorization, REVIEW_ACTION)
        if error is not None:
            return error
        assert principal is not None
        try:
            async with self.units() as work:
                record = await work.postmortems.get(incident_id, lock=True)
                incident = await work.incidents.get(incident_id)
                if incident is None:
                    return error_envelope(request_id, 404)
                if incident.state.get("state") != "postmortem":
                    return error_envelope(request_id, 409, NOT_OPEN)
                if record is None:
                    return error_envelope(request_id, 404, NOT_FOUND)
                if record.version != version:
                    return error_envelope(request_id, 409, CONFLICT)
                await work.postmortems.review(
                    record.postmortem_id,
                    version=version,
                    outcome=body["outcome"],
                    reviewer_id=principal.principal_id,
                    comment=comment,
                    now=self.clock(),
                )
                record = await work.postmortems.get(incident_id)
        except Exception:
            return error_envelope(request_id, 503)
        assert record is not None
        return JSONResponse(project(record, with_content=False), 201)

    async def read(self, incident_id: str, authorization: str | None) -> JSONResponse:
        request_id = uuid4()
        if re.fullmatch(IDENTIFIER_PATTERN, incident_id) is None:
            return error_envelope(request_id, 422)
        _, allowed, error = await self._principal(
            request_id, authorization, (READ_ACTION, CONTENT_ACTION)
        )
        if error is not None:
            return error
        try:
            async with self.units() as work:
                if await work.incidents.get(incident_id) is None:
                    return error_envelope(request_id, 404)
                record = await work.postmortems.get(incident_id)
        except Exception:
            return error_envelope(request_id, 503)
        if record is None:
            return error_envelope(request_id, 404, NOT_FOUND)
        return JSONResponse(project(record, with_content=CONTENT_ACTION in allowed), 200)

    async def memory_changes(self, authorization: str | None) -> JSONResponse:
        """The incident memory change log (#773): what entered, when and from which incident.

        Memory content is postmortem text, so it leaves only with `run.read_context`.
        """
        request_id = uuid4()
        _, _, error = await self._principal(request_id, authorization, (CONTENT_ACTION,))
        if error is not None:
            return error
        try:
            async with self.sessions() as session:
                changes = await PostgresIncidentMemoryRepository(session).changes()
        except Exception:
            return error_envelope(request_id, 503)
        return JSONResponse(
            {
                "changes": [
                    {
                        "memory_id": item.memory_id,
                        "operation": "added",
                        "incident_id": item.incident_id,
                        "source_record": item.source_record,
                        "postmortem_id": item.postmortem_id,
                        "postmortem_version": item.postmortem_version,
                        "close_event_id": item.close_event_id,
                        "service": item.service,
                        "signal": item.signal,
                        "indexed_at": item.indexed_at.isoformat(),
                        "content": item.content,
                    }
                    for item in changes
                ]
            },
            200,
        )


def postmortems_router(service: PostmortemService) -> APIRouter:
    router = APIRouter()

    @router.put("/v1/incidents/{incident_id}/postmortem")
    async def write_postmortem(incident_id: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.write(incident_id, body, request.headers.get("authorization"))

    @router.post("/v1/incidents/{incident_id}/postmortem/reviews")
    async def review_postmortem(incident_id: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.review(incident_id, body, request.headers.get("authorization"))

    @router.get("/v1/incidents/{incident_id}/postmortem")
    async def read_postmortem(incident_id: str, request: Request) -> JSONResponse:
        return await service.read(incident_id, request.headers.get("authorization"))

    @router.get("/v1/incident-memory/changes")
    async def read_memory_changes(request: Request) -> JSONResponse:
        return await service.memory_changes(request.headers.get("authorization"))

    return router
