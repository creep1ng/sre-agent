"""Start and resume incident runs over HTTP (HT-INC-COMMANDS, issue #330).

Delivery lives in the gateway: bearer authentication, `run.start` on the pinned
workflow resource, idempotency taken from the request header, and the contract
error envelope. Every state rule, transition and unit of work stays in the
runtime (#26) and its authoritative store (#146): this module decides no state
change and owns no second state machine.

The actor comes from the authenticated credential. A body cannot name a
different actor, so a browser can never assert authority it was not granted.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, Response

from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import Admission, Gate, Refusals, Released, Scope
from sre_agent.gateway.execution import ExecutionRefused, OperationExecutor
from sre_agent.gateway.incidents import (
    INVALID,
    NOT_FOUND,
    RETRY_AFTER_SECONDS,
    UNAUTHENTICATED,
    UNAVAILABLE,
    WORKFLOW_RESOURCE_TYPE,
    IncidentWorkflowResourceReader,
    consistent_run_state,
)
from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationEvaluation,
)
from sre_agent.governance.dto import Principal, PrincipalContext
from sre_agent.incident.commands import HumanCommand, resolve
from sre_agent.incident.persistence import (
    IncidentIdempotencyConflictError,
    IncidentStaleWriteError,
    IncidentUnitOfWork,
)
from sre_agent.incident.projections import (
    RUN_ID_PATTERN,
    UnsupportedWorkflowDataError,
    project_run_state,
)
from sre_agent.incident.runtime import (
    ActorReference,
    ApprovalRequiredError,
    IncidentNotFoundError,
    IncidentRuntime,
    InvalidTransitionError,
    MissingIncidentVersionError,
    PreconditionFailedError,
    RunNotFoundError,
    RunStart,
)
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.repositories import GrantRepository, PrincipalRepository
from sre_agent.vocabulary import (
    RUN_OBJECTIVE_TRANSITIONS,
    RunCommand,
    RunObjective,
    is_identifier,
)

logger = logging.getLogger(__name__)
START_ACTION = "run.start"
# The range the contract admits. The store follows it: migration 20260928_14
# widens transition_commits.command_id to varchar(200), so the boundary no
# longer refuses a key the contract allows, nor accepts one the store cannot
# hold.
IDEMPOTENCY_KEY_PATTERN = r"^\S{8,200}$"
START_REQUEST_FIELDS = frozenset({"workflow_version", "objective", "resume_from_run_id"})

START_DENIED = GovernedError(
    403, "not_authorized", "The principal is not authorized to start runs on this workflow."
)
RUN_CONFLICT = GovernedError(
    409, "run_conflict", "The request conflicts with the current state of the run."
)
CONFLICTS = (
    ApprovalRequiredError,
    IncidentIdempotencyConflictError,
    IncidentStaleWriteError,
    InvalidTransitionError,
)

Authorizer = Callable[[Any, Principal], Awaitable[AuthorizationEvaluation]]


def status_error(status: int, code: str, message: str) -> GovernedError:
    """A refusal another component reports by status (the deploy-executor), as the run routes
    word theirs: retryable with `Retry-After` when unavailable, a challenge when unauthenticated."""
    if status == 401:
        return GovernedError(status, code, message, headers={"WWW-Authenticate": "Bearer"})
    if status == 503:
        return GovernedError(status, code, message, retryable=True, retry_after=RETRY_AFTER_SECONDS)
    return GovernedError(status, code, message)


class RunStartService:
    """Open a run for an objective, or return the run a caller asks to resume."""

    def __init__(
        self,
        sessions: Any,
        workflow: IncidentWorkflow,
        runtime: IncidentRuntime,
        units: Callable[[], IncidentUnitOfWork],
        authorizer: Authorizer | None = None,
        investigator: Any = None,
    ) -> None:
        self.sessions, self.workflow, self.runtime, self.units = sessions, workflow, runtime, units
        self._authorizer = authorizer or self._default_authorizer
        self.investigator = investigator
        self.scope = Scope(START_ACTION, WORKFLOW_RESOURCE_TYPE, workflow.workflow_id)
        self._gate: Gate[None] = Gate(
            sessions,
            Refusals(unauthenticated=UNAUTHENTICATED, denied=START_DENIED, unavailable=UNAVAILABLE),
            authorizer=lambda session, context, scope: self._authorizer(session, context.principal),
        )

    async def _default_authorizer(
        self, session: Any, principal: Principal
    ) -> AuthorizationEvaluation:
        engine = AuthorizationDecisionEngine(
            IncidentWorkflowResourceReader(self.workflow), GrantRepository(session)
        )
        return await engine.evaluate(
            principal, START_ACTION, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
        )

    def _invalid_request(self, incident_id: str, idempotency_key: str | None, body: Any) -> bool:
        if not is_identifier(incident_id):
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
        if not isinstance(objective, str) or objective not in RUN_OBJECTIVE_TRANSITIONS:
            return True
        resume = body.get("resume_from_run_id")
        return resume is not None and re.fullmatch(RUN_ID_PATTERN, str(resume)) is None

    async def start(
        self,
        incident_id: str,
        body: Any,
        authorization: str | None,
        idempotency_key: str | None,
    ) -> Response:
        def validate() -> None:
            if self._invalid_request(incident_id, idempotency_key, body):
                raise INVALID

        async def start(admission: Admission, _: None) -> Released:
            assert idempotency_key is not None
            resume = body.get("resume_from_run_id")
            if resume is not None:
                return await self._resume(incident_id, str(resume))
            principal = admission.context.principal
            return await self._open(incident_id, body, principal, idempotency_key)

        return await self._gate.run(authorization, self.scope, start, validate=validate)

    async def _open(
        self, incident_id: str, body: dict[str, Any], principal: Principal, idempotency_key: str
    ) -> Released:
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
            raise NOT_FOUND["incident_not_found"] from None
        except RunNotFoundError:
            raise NOT_FOUND["run_not_found"] from None
        except (*CONFLICTS, PreconditionFailedError):
            raise RUN_CONFLICT from None
        sequence = max((event.sequence for event in result.events), default=-1)
        run = result.run
        if body["objective"] == RunObjective.INVESTIGATE and self.investigator is not None:
            await self.investigator.after_start(result)
            async with self.units() as work:
                found = await consistent_run_state(work, result.run.run_id, incident_id)
            if found is None:
                raise NOT_FOUND["run_not_found"]
            run, sequence = found
        return self._state(run, sequence, 200 if result.replayed else 201)

    def _state(self, run: Any, sequence: int, status: int) -> Released:
        try:
            return Released(project_run_state(run, self.workflow, event_sequence=sequence), status)
        except UnsupportedWorkflowDataError:
            raise INVALID from None

    async def _resume(self, incident_id: str, run_id: str) -> Released:
        """Return the run the caller asks to resume, from the authoritative store.

        Resuming reads: the run keeps its identity and its correlation, and the
        caller drives it further with commands. Nothing is transitioned here.
        """

        async with self.units() as work:
            if await work.incidents.get(incident_id) is None:
                raise NOT_FOUND["incident_not_found"]
            # The state and its cursor come from one read point, as in the
            # run reads: a transition that lands between reading the run and
            # its events is read again, never returned as an old state with
            # a newer cursor. A read that keeps racing is a retryable 503.
            found = await consistent_run_state(work, run_id, incident_id)
        if found is None:
            raise NOT_FOUND["run_not_found"]
        run, sequence = found
        return self._state(run, sequence, 200)


def runs_router(service: RunStartService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/incidents/{incident_id}/runs")
    async def start_run(incident_id: str, request: Request) -> Response:
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


# Which action authorizes each command, copied from the command_action_map of
# agent/api/authorization.v1.yaml. The route resolves the action itself and asks
# the engine for it; it never infers authority from the body or from a name.
COMMAND_ACTIONS = {
    RunCommand.APPROVE_MITIGATION: "run.approve",
    RunCommand.REJECT_MITIGATION: "run.approve",
    RunCommand.REQUEST_CHANGES: "run.command",
    RunCommand.PROPOSE_DISPOSITION: "run.command",
    RunCommand.ESCALATE: "run.command",
    RunCommand.CANCEL_RUN: "run.command",
    RunCommand.VERIFICATION_PASSED: "run.command",
    RunCommand.VERIFICATION_FAILED: "run.command",
    RunCommand.CLOSE_INCIDENT: "run.approve",
}
COMMAND_FIELDS = frozenset(
    {
        "command",
        "actor",
        "actor_reference",
        "turn_id",
        "disposition",
        "comment",
        "authorization",
        "expected_incident_version",
    }
)
VERSIONED_REVIEW_COMMANDS = frozenset(
    {RunCommand.APPROVE_MITIGATION, RunCommand.REJECT_MITIGATION, RunCommand.REQUEST_CHANGES}
)
# run-command:2.1.0 commands have no pre-version clients to replay, so the
# reviewed version is always required, and closing must assert run.approve in
# the body: the explicit human approval the workflow requires to close.
VERSION_REQUIRED_COMMANDS = frozenset(
    {RunCommand.VERIFICATION_PASSED, RunCommand.VERIFICATION_FAILED, RunCommand.CLOSE_INCIDENT}
)
EXPLICIT_APPROVAL_COMMANDS = frozenset({RunCommand.CLOSE_INCIDENT})
DISPOSITIONS = frozenset({"dismiss", "link", "declare"})
TURN_ID_PATTERN = r"^turn_[a-z0-9]{8,32}$"
MAX_COMMENT = 2000
COMMAND_REFUSALS = Refusals(
    unauthenticated=UNAUTHENTICATED,
    denied=GovernedError(
        403, "not_authorized", "The principal is not authorized to send this command."
    ),
    unavailable=UNAVAILABLE,
)
ATTRIBUTION_MISMATCH = GovernedError(
    403, "actor_attribution_mismatch", "Actor attribution must match the authenticated principal."
)
PRECONDITION_FAILED = GovernedError(
    409, "precondition_failed", "The incident does not meet the command's workflow precondition."
)
COMMAND_CONFLICT = GovernedError(
    409, "run_conflict", "The command is not permitted from the run's current state."
)


class RunCommandService:
    """Deliver one human command to a run, with the workflow deciding the rest.

    The command names the action, the action is asked of the engine, and the
    engine answers against an active grant. The body never expands that: it may
    assert the authorization tuple, but the assertion is checked against what
    the route resolved and rejected when it disagrees, and the actor it names
    must be the authenticated principal or the request is refused as spoofed
    attribution.
    """

    def __init__(
        self,
        sessions: Any,
        workflow: IncidentWorkflow,
        runtime: IncidentRuntime,
        authorizer: Callable[[Any, Principal, str], Awaitable[AuthorizationEvaluation]]
        | None = None,
        executor: OperationExecutor | None = None,
        verifier: Any = None,
    ) -> None:
        self.sessions, self.workflow, self.runtime = sessions, workflow, runtime
        self._authorizer = authorizer or self._default_authorizer
        self.executor, self.verifier = executor, verifier
        self._gate: Gate[str] = Gate(
            sessions,
            COMMAND_REFUSALS,
            authorizer=lambda session, context, scope: self._authorizer(
                session, context.principal, scope.action
            ),
        )

    async def _default_authorizer(
        self, session: Any, principal: Principal, action: str
    ) -> AuthorizationEvaluation:
        engine = AuthorizationDecisionEngine(
            IncidentWorkflowResourceReader(self.workflow), GrantRepository(session)
        )
        return await engine.evaluate(
            principal, action, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
        )

    async def _linked(self, principal_id: str, channel: str) -> PrincipalContext | None:
        """The active principal a chat link names; the link stands in for the credential."""
        async with self.sessions() as session:
            principal = await PrincipalRepository(session).get(principal_id)
        if principal is None or principal.status != "active":
            return None
        return PrincipalContext(
            principal=principal,
            credential_id=f"chat_link_{channel}",
            authenticated_at=datetime.now(UTC),
        )

    def _invalid_reference(self, reference: Any) -> bool:
        if not isinstance(reference, dict) or set(reference) - {
            "reference_version",
            "principal_id",
            "display_name",
        }:
            return True
        name = reference.get("display_name")
        return (
            reference.get("reference_version") != "1.0.0"
            or not isinstance(reference.get("principal_id"), str)
            or not is_identifier(reference["principal_id"])
            or (name is not None and (not isinstance(name, str) or len(name) > 200))
        )

    def _invalid_request(
        self, incident_id: str, run_id: str, idempotency_key: str | None, body: Any
    ) -> bool:
        if not is_identifier(incident_id):
            return True
        if re.fullmatch(RUN_ID_PATTERN, run_id) is None:
            return True
        if (
            idempotency_key is None
            or re.fullmatch(IDEMPOTENCY_KEY_PATTERN, idempotency_key) is None
        ):
            return True
        if not isinstance(body, dict) or not set(body) <= COMMAND_FIELDS:
            return True
        # A command or disposition of any other JSON type must be refused here, as
        # invalid: an array or an object is not hashable, and looking it up in the
        # maps below would raise outside the error handling and answer 500.
        command = body.get("command")
        if not isinstance(command, str) or command not in COMMAND_ACTIONS:
            return True
        if command in VERSIONED_REVIEW_COMMANDS:
            version = body.get("expected_incident_version")
            # Omission is admitted only to let the runtime replay an exact legacy
            # idempotency key whose stored hash predates this field. A fresh
            # versionless review still fails the runtime's version precondition.
            if "expected_incident_version" in body and (type(version) is not int or version < 0):
                return True
        elif command in VERSION_REQUIRED_COMMANDS:
            version = body.get("expected_incident_version")
            if type(version) is not int or version < 0:
                return True
        elif "expected_incident_version" in body:
            return True
        if body.get("actor") != "human":
            return True
        if self._invalid_reference(body.get("actor_reference")):
            return True
        disposition = body.get("disposition")
        if command == RunCommand.PROPOSE_DISPOSITION:
            if not isinstance(disposition, str) or disposition not in DISPOSITIONS:
                return True
        elif disposition is not None:
            return True
        comment = body.get("comment")
        if comment is not None and (not isinstance(comment, str) or len(comment) > MAX_COMMENT):
            return True
        turn_id = body.get("turn_id")
        if turn_id is not None and (
            not isinstance(turn_id, str) or re.fullmatch(TURN_ID_PATTERN, turn_id) is None
        ):
            return True
        return self._contradicts_resolved_authority(command, body.get("authorization"))

    def _contradicts_resolved_authority(self, command: str, claim: Any) -> bool:
        """The body may assert its authorization; it may never disagree with it."""

        if claim is None:
            return command in EXPLICIT_APPROVAL_COMMANDS
        if not isinstance(claim, dict) or set(claim) - {"action", "resource"}:
            return True
        resource = claim.get("resource")
        if not isinstance(resource, dict) or set(resource) - {"type", "id"}:
            return True
        return (
            claim.get("action") != COMMAND_ACTIONS[command]
            or resource.get("type") != WORKFLOW_RESOURCE_TYPE
            or resource.get("id") != self.workflow.workflow_id
        )

    async def send_from_chat(
        self,
        principal_id: str,
        channel: str,
        incident_id: str,
        run_id: str,
        body: Any,
        idempotency_key: str,
    ) -> Response:
        """Deliver a command from a linked chat, as the human principal the link names (#767).

        The chat gateway has no bearer key to forward: the link record stands in for the
        authentication, and everything after it (grant, attribution, runtime) is `send`'s.
        """
        return await self.send(
            incident_id, run_id, body, None, idempotency_key, linked=(principal_id, channel)
        )

    async def send(
        self,
        incident_id: str,
        run_id: str,
        body: Any,
        authorization: str | None,
        idempotency_key: str | None,
        *,
        linked: tuple[str, str] | None = None,
    ) -> Response:
        def validate() -> str:
            if self._invalid_request(incident_id, run_id, idempotency_key, body):
                raise INVALID
            return str(body["command"])

        async def command(admission: Admission, command: str) -> Released:
            assert idempotency_key is not None
            return await self._command(
                admission, incident_id, run_id, body, idempotency_key, linked
            )

        return await self._gate.run(
            authorization,
            lambda command: Scope(
                COMMAND_ACTIONS[command], WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
            ),
            command,
            validate=validate,
            authenticate=(lambda _: self._linked(*linked)) if linked else None,
        )

    async def _command(
        self,
        admission: Admission,
        incident_id: str,
        run_id: str,
        body: dict[str, Any],
        idempotency_key: str,
        linked: tuple[str, str] | None,
    ) -> Released:
        principal, request_id = admission.context.principal, admission.request_id
        command = str(body["command"])
        # Commands are human-only (run-command:2.0.0 and 2.1.0). The actor type and the
        # reference the body asserts must both describe the authenticated
        # principal: an agent credential holding the action, by grant or by
        # mistake, still cannot sign a human command.
        if (
            principal.kind != "human"
            or body["actor_reference"]["principal_id"] != principal.principal_id
        ):
            raise ATTRIBUTION_MISMATCH
        request = HumanCommand(
            command_id=idempotency_key,
            incident_id=incident_id,
            run_id=run_id,
            command=command,
            actor_reference=ActorReference(
                principal_id=principal.principal_id,
                display_name=body["actor_reference"].get("display_name"),
            ),
            disposition=body.get("disposition"),
            comment=body.get("comment"),
            expected_incident_version=body.get("expected_incident_version"),
            turn_id=body.get("turn_id"),
            inputs={"channel": linked[1]} if linked else None,
        )
        try:
            transition = resolve(request)
            if command == RunCommand.APPROVE_MITIGATION and self.executor is not None:
                # Checked, then run, before anything moves: verifying means it ran (#722).
                execution = await self.executor.run(
                    incident_id, run_id, request.expected_incident_version, request_id
                )
                transition = replace(transition, execution=execution)
            result = await self.runtime.execute(transition)
        except ExecutionRefused as refused:
            # Nothing moved; the run's timeline still says why (#722), and the answer stands.
            try:
                await self.runtime.record_refusal(
                    incident_id,
                    run_id,
                    request.actor_reference,
                    reason_code=refused.code,
                    request_id=str(request_id),
                    denial=refused.status == 403,
                )
            except Exception as error:
                # Only the type is logged, never the content; the refusal still answers.
                logger.error("approval_refusal_record_failed error=%s", type(error).__name__)
            raise status_error(refused.status, refused.code, refused.message) from None
        except IncidentNotFoundError:
            raise NOT_FOUND["incident_not_found"] from None
        except RunNotFoundError:
            raise NOT_FOUND["run_not_found"] from None
        except MissingIncidentVersionError:
            raise INVALID from None
        except PreconditionFailedError:
            # A guard of the runtime refused it, before anything was written.
            raise PRECONDITION_FAILED from None
        except CONFLICTS:
            raise COMMAND_CONFLICT from None
        if transition.execution is not None and self.verifier is not None:
            # It ran: the agent measures the service once the delay passes (#723).
            self.verifier.after_approval(incident_id, run_id)
        if command == RunCommand.VERIFICATION_PASSED and self.verifier is not None:
            # Resolved: the agent opens the postmortem with its draft (#711).
            self.verifier.after_resolved(incident_id)
        if command == RunCommand.VERIFICATION_FAILED and self.verifier is not None:
            # Still failing: the agent investigates again on its own (#710).
            self.verifier.after_verification_failed(incident_id)
        sequence = max((event.sequence for event in result.events), default=-1)
        try:
            payload = project_run_state(result.run, self.workflow, event_sequence=sequence)
        except UnsupportedWorkflowDataError:
            raise INVALID from None
        return Released(payload, 202)


def commands_router(service: RunCommandService) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/incidents/{incident_id}/runs/{run_id}/commands")
    async def send_command(incident_id: str, run_id: str, request: Request) -> Response:
        try:
            body = await request.json()
        except ValueError:
            body = None
        return await service.send(
            incident_id,
            run_id,
            body,
            request.headers.get("authorization"),
            request.headers.get("idempotency-key"),
        )

    return router
