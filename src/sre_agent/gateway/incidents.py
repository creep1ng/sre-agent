# ruff: noqa: E501, I001
"""Authoritative incident query endpoints: detail, timeline and public snapshot (HT-INC-RUNTIME-B, issue #189),
the run state and run events of the runs contract (HT-INC-COMMANDS, issue #330), and the
incident list an inbox reads first (issue #870).

Delivery lives in the gateway: bearer authentication, workflow-scoped
authorization (run.read on incident_workflow, pinned workflow as the stable
resource fact so no business joins cross into gateway tables) and the
contract error envelope. Read projections come from
sre_agent.incident.projections; reads never mutate aggregates.
"""

import re
from datetime import datetime
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request, Response

from sre_agent.gate.authentication import principal_for
from sre_agent.gate.errors import AuthenticationFailed, GovernedError
from sre_agent.gate.pipeline import (
    Admission,
    Gate,
    Refusals,
    Released,
    Scope,
    ScopeDeclaration,
    declare,
    failing_as,
)
from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationEvaluation,
    ResourceAuthorizationFact,
)
from sre_agent.governance.dto import Principal, PrincipalContext, ResourceType
from sre_agent.incident.persistence import IncidentRecord, IncidentUnitOfWork, RunRecord
from sre_agent.incident.projections import (
    RUN_ID_PATTERN,
    UnsupportedWorkflowDataError,
    decode_cursor,
    encode_cursor,
    project_detail,
    project_event,
    project_list_item,
    project_run_state,
    project_snapshot,
)
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.repositories import GrantRepository
from sre_agent.vocabulary import IDENTIFIER_PATTERN

WORKFLOW_RESOURCE_TYPE: ResourceType = "incident_workflow"
READ_ACTION = "run.read"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
RETRY_AFTER_SECONDS = "5"
LIST_STATUSES = ("open", "recent")
LIST_DEFAULT_LIMIT = 50
LIST_MAX_LIMIT = 100
# Attempts at reading a run and its last event without a transition landing between
# the two reads. A miss means writes are racing the read; the caller may retry.
STATE_READ_ATTEMPTS = 3
# The most events the event repository returns in one call.
EVENT_PAGE = 1000

UNAUTHENTICATED = AuthenticationFailed("Authentication is required.")
DENIED = GovernedError(
    403, "not_authorized", "The principal is not authorized to read this incident."
)
INVALID = GovernedError(422, "validation_error", "The request is invalid.")
INVALID_CURSOR = GovernedError(422, "invalid_cursor", "The request is invalid.")
UNAVAILABLE = GovernedError(
    503,
    "storage_unavailable",
    "Incident storage is temporarily unavailable.",
    retryable=True,
    retry_after=RETRY_AFTER_SECONDS,
)
NOT_FOUND = {
    code: GovernedError(404, code, message)
    for code, message in (
        ("incident_not_found", "The requested incident was not found."),
        ("run_absent", "The incident has no runs yet."),
        ("run_not_found", "The requested incident run was not found."),
        ("snapshot_absent", "No snapshot exists for this run yet."),
    )
}


def read_operation(method: str, path: str, action: str = READ_ACTION) -> ScopeDeclaration:
    """An incident read on the pinned workflow, registered in the gate."""
    return declare(method, path, action=action, resource_type=WORKFLOW_RESOURCE_TYPE,
                   resource_id="incident-response")  # fmt: skip


INCIDENT_PATH = "/v1/incidents/{incident_id}"
LIST = read_operation("GET", "/v1/incidents")
DETAIL = read_operation("GET", INCIDENT_PATH)
TIMELINE = read_operation("GET", INCIDENT_PATH + "/timeline")
SNAPSHOT = read_operation("GET", INCIDENT_PATH + "/snapshot")
RUN_STATE = read_operation("GET", INCIDENT_PATH + "/runs/{run_id}")
RUN_EVENTS = read_operation("GET", INCIDENT_PATH + "/runs/{run_id}/events")
REFUSALS = Refusals(unauthenticated=UNAUTHENTICATED, denied=DENIED, unavailable=UNAVAILABLE)


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


class StateReadRaceError(Exception):
    """Every attempt saw a transition land between reading a run and its events."""


async def consistent_run_state(
    work: IncidentUnitOfWork, run_id: str, incident_id: str
) -> tuple[RunRecord, int] | None:
    """The run and the sequence of the last event it reflects, read as one consistent pair.

    A state transition bumps the run version; receipt-only appends update ``updated_at``
    in the same transaction as their events. The run is read again after its events: if
    neither marker moved, no write landed in between, so the cursor describes exactly
    the state returned and a consumer polling from it neither skips nor re-applies an
    event. Events are read from the latest snapshot on, which the runtime takes every
    few transitions.
    """

    for _ in range(STATE_READ_ATTEMPTS):
        run = await work.runs.get_for_incident(run_id, incident_id)
        if run is None:
            return None
        snapshot = await work.snapshots.latest(run_id)
        sequence = snapshot.event_sequence if snapshot is not None else -1
        while True:
            page = await work.events.list_after(run_id, sequence=sequence, limit=EVENT_PAGE)
            if page:
                sequence = page[-1].sequence
            if len(page) < EVENT_PAGE:
                break
        again = await work.runs.get_for_incident(run_id, incident_id)
        if (
            again is not None
            and again.version == run.version
            and again.updated_at == run.updated_at
        ):
            return run, sequence
    raise StateReadRaceError(run_id)


def _identifiers(incident_id: str, run_id: str | None = None) -> None:
    if re.fullmatch(IDENTIFIER_PATTERN, incident_id) is None:
        raise INVALID
    if run_id is not None and re.fullmatch(RUN_ID_PATTERN, run_id) is None:
        raise INVALID


class IncidentQueryService:
    """Read-only incident queries over the authoritative unit of work."""

    action = READ_ACTION

    def __init__(
        self,
        sessions: Any,
        workflow: IncidentWorkflow,
        units: Callable[[], IncidentUnitOfWork],
        authorizer: Authorizer | None = None,
    ) -> None:
        self.sessions, self.workflow, self.units = sessions, workflow, units
        self._authorizer = authorizer or self._default_authorizer
        self.scope = Scope(self.action, WORKFLOW_RESOURCE_TYPE, workflow.workflow_id)
        self._gate: Gate[Any] = Gate(
            sessions,
            REFUSALS,
            authenticate=lambda authorization: self._authenticate(authorization),
            authorizer=lambda session, context, scope: self._authorizer(session, context.principal),
        )

    async def _default_authorizer(self, session: Any, principal: Principal) -> AuthorizationEvaluation:  # fmt: skip
        engine = AuthorizationDecisionEngine(
            IncidentWorkflowResourceReader(self.workflow), GrantRepository(session)
        )
        return await engine.evaluate(
            principal, self.action, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
        )

    async def _authenticate(self, authorization: str | None) -> PrincipalContext | None:
        return await principal_for(self.sessions, authorization)

    async def _read(
        self,
        operation: ScopeDeclaration,
        authorization: str | None,
        validate: Callable[[], Any],
        use_case: Any,
    ) -> Response:
        async def read(admission: Admission, request: Any) -> Any:
            # Reading the store or projecting what it holds fails as the reads' 503, as before.
            with failing_as(UNAVAILABLE):
                return await use_case(admission, request)

        return await self._gate.run(operation, authorization, self.scope, read, validate=validate)

    async def _incident(self, incident_id: str) -> IncidentRecord:
        with failing_as(UNAVAILABLE):
            async with self.units() as work:
                record = await work.incidents.get(incident_id)
        if record is None:
            raise NOT_FOUND["incident_not_found"]
        return record

    async def _resolve_run(self, incident_id: str, run_id: str | None) -> RunRecord:
        async with self.units() as work:
            if run_id is None:
                run_ids = await work.runs.list_ids(incident_id)
                if not run_ids:
                    raise NOT_FOUND["run_absent"]
                run_id = run_ids[-1]
            run = await work.runs.get_for_incident(run_id, incident_id)
        if run is None:
            raise NOT_FOUND["run_not_found"]
        return run

    async def get_detail(self, incident_id: str, authorization: str | None) -> Response:
        async def detail(admission: Admission, _: None) -> Released:
            record = await self._incident(incident_id)
            async with self.units() as work:
                run_ids = await work.runs.list_ids(incident_id)
                fetched = [await work.runs.get_for_incident(run, incident_id) for run in run_ids]
            runs = [run for run in fetched if run is not None]
            try:
                return Released(project_detail(record, runs, self.workflow))
            except UnsupportedWorkflowDataError:
                raise INVALID from None

        return await self._read(DETAIL, authorization, lambda: _identifiers(incident_id), detail)

    async def get_timeline(
        self,
        incident_id: str,
        run_id: str | None,
        after: str | None,
        limit: Any,
        authorization: str | None,
        operation: "ScopeDeclaration | None" = None,
    ) -> Response:
        operation = operation or TIMELINE

        def page_request() -> tuple[int, int]:
            _identifiers(incident_id, run_id)
            try:
                parsed_limit = int(limit) if limit is not None else DEFAULT_LIMIT
            except (TypeError, ValueError):
                raise INVALID from None
            if not 1 <= parsed_limit <= MAX_LIMIT:
                raise INVALID
            try:
                return parsed_limit, decode_cursor(after)
            except ValueError:
                raise INVALID_CURSOR from None

        async def timeline(admission: Admission, page_request: tuple[int, int]) -> Released:
            parsed_limit, sequence = page_request
            await self._incident(incident_id)
            run = await self._resolve_run(incident_id, run_id)
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
                    # A missing decision or unsupported data is a storage fault: the gate's 503.
                    page.append(project_event(event, document))
            watermark = max([sequence] + [item["sequence"] for item in page])
            return Released(
                {
                    "events": page,
                    "next_cursor": encode_cursor(watermark),
                    "has_more": len(stored) > parsed_limit,
                }
            )

        return await self._read(operation, authorization, page_request, timeline)

    async def get_snapshot(
        self, incident_id: str, run_id: str | None, authorization: str | None
    ) -> Response:
        async def snapshot(admission: Admission, _: None) -> Released:
            await self._incident(incident_id)
            run = await self._resolve_run(incident_id, run_id)
            async with self.units() as work:
                latest = await work.snapshots.latest(run.run_id)
            if latest is None:
                raise NOT_FOUND["snapshot_absent"]
            try:
                return Released(project_snapshot(latest, self.workflow))
            except UnsupportedWorkflowDataError:
                raise INVALID from None

        return await self._read(
            SNAPSHOT, authorization, lambda: _identifiers(incident_id, run_id), snapshot
        )

    async def get_run_state(self, incident_id: str, run_id: str, authorization: str | None) -> Response:  # fmt: skip
        """GET /v1/incidents/{incident_id}/runs/{run_id}: the run-state projection.

        The run must belong to the incident in the path; a run of another incident is
        404, exactly like one that does not exist, so the route cannot confirm it.
        """

        async def run_state(admission: Admission, _: None) -> Released:
            await self._incident(incident_id)
            async with self.units() as work:
                found = await consistent_run_state(work, run_id, incident_id)
            if found is None:
                raise NOT_FOUND["run_not_found"]
            run, sequence = found
            try:
                return Released(project_run_state(run, self.workflow, event_sequence=sequence))
            except UnsupportedWorkflowDataError:
                raise INVALID from None

        return await self._read(
            RUN_STATE, authorization, lambda: _identifiers(incident_id, run_id), run_state
        )

    async def list_incidents(
        self,
        status: str | None,
        since: str | None,
        limit: Any,
        authorization: str | None,
    ) -> Response:
        """GET /v1/incidents: incidents most recently updated first, each with its latest run
        and the decision it waits for, if any.

        ``open`` leaves out the terminal states; ``recent`` lists every state, so a closed
        incident appears while it is among the latest. ``since`` keeps incidents updated at or
        after an ISO 8601 instant with its offset.
        """

        def query() -> tuple[str, datetime | None, int]:
            try:
                parsed_limit = int(limit) if limit is not None else LIST_DEFAULT_LIMIT
                parsed_since = datetime.fromisoformat(since) if since is not None else None
            except (TypeError, ValueError):
                raise INVALID from None
            if (
                (status or "recent") not in LIST_STATUSES
                or not 1 <= parsed_limit <= LIST_MAX_LIMIT
                or (parsed_since is not None and parsed_since.tzinfo is None)
            ):
                raise INVALID
            return status or "recent", parsed_since, parsed_limit

        async def incidents(admission: Admission, query: tuple[str, datetime | None, int]) -> Released:  # fmt: skip
            listed, parsed_since, parsed_limit = query
            excluded = tuple(self.workflow.terminal_states) if listed == "open" else ()
            async with self.units() as work:
                records = await work.incidents.list_recent(
                    exclude_states=excluded, since=parsed_since, limit=parsed_limit + 1
                )
                runs = await work.runs.latest_for(
                    [record.incident_id for record in records[:parsed_limit]]
                )
            try:
                items = [
                    project_list_item(record, runs.get(record.incident_id), self.workflow)
                    for record in records[:parsed_limit]
                ]
            except UnsupportedWorkflowDataError:
                raise INVALID from None
            return Released(
                {
                    "incidents": [item for item in items if item is not None],
                    "has_more": len(records) > parsed_limit,
                },
                headers={"Cache-Control": "no-store"},
            )

        return await self._read(LIST, authorization, query, incidents)


def incident_router(service: IncidentQueryService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/incidents")
    async def incidents(request: Request) -> Response:
        params = request.query_params
        return await service.list_incidents(
            params.get("status"),
            params.get("since"),
            params.get("limit"),
            request.headers.get("authorization"),
        )

    @router.get("/v1/incidents/{incident_id}")
    async def detail(incident_id: str, request: Request) -> Response:
        return await service.get_detail(incident_id, request.headers.get("authorization"))

    @router.get("/v1/incidents/{incident_id}/timeline")
    async def timeline(incident_id: str, request: Request) -> Response:
        params = request.query_params
        return await service.get_timeline(
            incident_id,
            params.get("run_id"),
            params.get("after"),
            params.get("limit"),
            request.headers.get("authorization"),
        )

    @router.get("/v1/incidents/{incident_id}/snapshot")
    async def snapshot(incident_id: str, request: Request) -> Response:
        return await service.get_snapshot(
            incident_id,
            request.query_params.get("run_id"),
            request.headers.get("authorization"),
        )

    @router.get("/v1/incidents/{incident_id}/runs/{run_id}")
    async def run_state(incident_id: str, run_id: str, request: Request) -> Response:
        return await service.get_run_state(
            incident_id, run_id, request.headers.get("authorization")
        )

    @router.get("/v1/incidents/{incident_id}/runs/{run_id}/events")
    async def run_events(incident_id: str, run_id: str, request: Request) -> Response:
        # The timeline of one run: the same page, cursor and projection, with the
        # run fixed by the path instead of chosen by a query parameter.
        params = request.query_params
        return await service.get_timeline(
            incident_id,
            run_id,
            params.get("after"),
            params.get("limit"),
            request.headers.get("authorization"),
            RUN_EVENTS,
        )

    return router
