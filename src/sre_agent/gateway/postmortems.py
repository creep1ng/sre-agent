"""Write, review and read the incident postmortem over HTTP (issue #335, first cut).

The gateway authenticates, asks the engine for the action and shapes the
response; the artifact rules live in `sre_agent.incident.postmortem` and the
close rule in the runtime. Writers and reviewers are the authenticated human,
never a name in the body. Reading the progress (`run.read`) is not reading the
text: content and review comments leave only with `run.read_context`.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, Response

from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import Admission, Gate, Refusals, Released, Scope
from sre_agent.gateway.incidents import (
    INVALID,
    NOT_FOUND,
    UNAUTHENTICATED,
    UNAVAILABLE,
    WORKFLOW_RESOURCE_TYPE,
    IncidentWorkflowResourceReader,
)
from sre_agent.governance.dto import Principal
from sre_agent.incident.persistence import IncidentStaleWriteError, IncidentUnitOfWork
from sre_agent.incident.postmortem import (
    REVIEW_OUTCOMES,
    InvalidPostmortemError,
    PostmortemRecord,
    validate_content,
)
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.memories import PostgresIncidentMemoryRepository
from sre_agent.vocabulary import IncidentState, is_identifier

WRITE_ACTION, REVIEW_ACTION, READ_ACTION, CONTENT_ACTION = (
    "run.command",
    "run.approve",
    "run.read",
    "run.read_context",
)
MAX_COMMENT = 2000
DENIED = GovernedError(
    403, "not_authorized", "The principal is not authorized for this postmortem operation."
)
REFUSALS = Refusals(unauthenticated=UNAUTHENTICATED, denied=DENIED, unavailable=UNAVAILABLE)
NOT_OPEN = GovernedError(409, "postmortem_not_open", "The incident is not in the postmortem state.")
ABSENT = GovernedError(404, "postmortem_not_found", "The incident has no persisted postmortem.")
CONFLICT = GovernedError(
    409, "postmortem_version_conflict", "The postmortem changed; reload the current version."
)
UNKNOWN_EVENT = GovernedError(
    422, "unknown_event_reference", "A cited event does not exist in this incident."
)
INCIDENT_NOT_FOUND = NOT_FOUND["incident_not_found"]


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
        self._gate: Gate[Any] = Gate(
            sessions, REFUSALS, facts=lambda _: IncidentWorkflowResourceReader(workflow)
        )

    def _scope(self, action: str) -> Scope:
        return Scope(action, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id)

    @staticmethod
    def _human(admission: Admission) -> Principal:
        """Writers and reviewers are people: an agent holding the grant is still refused."""
        if admission.context.principal.kind != "human":
            raise DENIED
        return admission.context.principal

    async def write(self, incident_id: str, body: Any, authorization: str | None) -> Response:
        def validate() -> tuple[int, Any]:
            version = body.get("expected_version") if isinstance(body, dict) else None
            if (
                not is_identifier(incident_id)
                or not isinstance(body, dict)
                or set(body) != {"expected_version", "content"}
                or type(version) is not int
                or version < 0
            ):
                raise INVALID
            try:
                return version, validate_content(body["content"])
            except InvalidPostmortemError as error:
                raise GovernedError(422, "invalid_postmortem", str(error)) from None

        async def write(admission: Admission, request: tuple[int, Any]) -> Released:
            version, cited = request
            principal = self._human(admission)
            try:
                async with self.units() as work:
                    await work.postmortems.get(incident_id, lock=True)
                    incident = await work.incidents.get(incident_id)
                    if incident is None:
                        raise INCIDENT_NOT_FOUND
                    reserved = incident.state.get("postmortem") or {}
                    if incident.state.get("state") != IncidentState.POSTMORTEM or not reserved.get(
                        "postmortem_id"
                    ):
                        raise NOT_OPEN
                    if cited - await work.postmortems.known_event_ids(incident_id, cited):
                        raise UNKNOWN_EVENT
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
                raise CONFLICT from None
            assert record is not None
            return Released(project(record, with_content=False), 201 if version == 0 else 200)

        return await self._gate.run(
            authorization, self._scope(WRITE_ACTION), write, validate=validate
        )

    async def review(self, incident_id: str, body: Any, authorization: str | None) -> Response:
        def validate() -> None:
            version = body.get("version") if isinstance(body, dict) else None
            comment = body.get("comment") if isinstance(body, dict) else None
            if (
                not is_identifier(incident_id)
                or not isinstance(body, dict)
                or not {"version", "outcome"} <= set(body) <= {"version", "outcome", "comment"}
                or type(version) is not int
                or version < 1
                or body["outcome"] not in REVIEW_OUTCOMES
                or (
                    comment is not None
                    and (not isinstance(comment, str) or len(comment) > MAX_COMMENT)
                )
            ):
                raise INVALID

        async def review(admission: Admission, _: None) -> Released:
            principal = self._human(admission)
            async with self.units() as work:
                record = await work.postmortems.get(incident_id, lock=True)
                incident = await work.incidents.get(incident_id)
                if incident is None:
                    raise INCIDENT_NOT_FOUND
                if incident.state.get("state") != IncidentState.POSTMORTEM:
                    raise NOT_OPEN
                if record is None:
                    raise ABSENT
                if record.version != body["version"]:
                    raise CONFLICT
                await work.postmortems.review(
                    record.postmortem_id,
                    version=body["version"],
                    outcome=body["outcome"],
                    reviewer_id=principal.principal_id,
                    comment=body.get("comment"),
                    now=self.clock(),
                )
                record = await work.postmortems.get(incident_id)
            assert record is not None
            return Released(project(record, with_content=False), 201)

        return await self._gate.run(
            authorization, self._scope(REVIEW_ACTION), review, validate=validate
        )

    async def read(self, incident_id: str, authorization: str | None) -> Response:
        def validate() -> None:
            if not is_identifier(incident_id):
                raise INVALID

        async def read(admission: Admission, _: None) -> Released:
            # Reading the progress is not reading the text: content needs its own action.
            content = await self._gate.authorize(admission.context, self._scope(CONTENT_ACTION))
            async with self.units() as work:
                if await work.incidents.get(incident_id) is None:
                    raise INCIDENT_NOT_FOUND
                record = await work.postmortems.get(incident_id)
            if record is None:
                raise ABSENT
            with_content = content.decision.decision == "allow"
            return Released(project(record, with_content=with_content))

        return await self._gate.run(
            authorization, self._scope(READ_ACTION), read, validate=validate
        )

    async def memory_changes(self, authorization: str | None) -> Response:
        """The incident memory change log (#773): what entered, when and from which incident.

        Memory content is postmortem text, so it leaves only with `run.read_context`.
        """

        async def changes(admission: Admission, _: None) -> Released:
            async with self.sessions() as session:
                changes = await PostgresIncidentMemoryRepository(session).changes()
            return Released(
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
                }
            )

        return await self._gate.run(authorization, self._scope(CONTENT_ACTION), changes)


def postmortems_router(service: PostmortemService) -> APIRouter:
    router = APIRouter()

    @router.put("/v1/incidents/{incident_id}/postmortem")
    async def write_postmortem(incident_id: str, request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.write(incident_id, body, request.headers.get("authorization"))

    @router.post("/v1/incidents/{incident_id}/postmortem/reviews")
    async def review_postmortem(incident_id: str, request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.review(incident_id, body, request.headers.get("authorization"))

    @router.get("/v1/incidents/{incident_id}/postmortem")
    async def read_postmortem(incident_id: str, request: Request) -> Response:
        return await service.read(incident_id, request.headers.get("authorization"))

    @router.get("/v1/incident-memory/changes")
    async def read_memory_changes(request: Request) -> Response:
        return await service.memory_changes(request.headers.get("authorization"))

    return router
