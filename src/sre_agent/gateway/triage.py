# ruff: noqa: E501, I001
"""Alert triage commands over HTTP (issue #23, chain C2b). Thin delegation."""

import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, Response

from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import Admission, Gate, Refusals, Released, Scope
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import ResourceRepository
from sre_agent.triage.service import (
    ACTIONS,
    READ_ACTION,
    WORKFLOW_ID,
    WORKFLOW_TYPE,
    InvestigationDispatcher,
    TriageError,
    TriageService,
)
from sre_agent.vocabulary import TransitionId, is_identifier

KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
RETRY_AFTER_SECONDS = "5"
MALFORMED = object()
WORKFLOW = (WORKFLOW_TYPE, WORKFLOW_ID)

# Closed command payloads mirrored from triage-command.schema.yaml (no new
# runtime dependency to load it here): unknown operations and extra keys are
# 422; required/type/value rules stay owned by the service.
ALLOWED_KEYS = {
    TransitionId.OPEN_TRIAGE: frozenset({"operation", "expected_version"}),
    TransitionId.TRIAGE_DISMISS: frozenset({"operation", "expected_version", "reason"}),
    TransitionId.TRIAGE_LINK: frozenset(
        {"operation", "expected_version", "reason", "target_incident_id"}
    ),
    TransitionId.TRIAGE_DECLARE: frozenset(
        {"operation", "expected_version", "reason", "severity", "impact", "alert_context"}
    ),
}

MESSAGES = {
    400: "Malformed command envelope.",
    401: "Missing or invalid bearer credential.",
    403: "Missing the required action grant or human operator identity.",
    404: "Unknown alert or target incident.",
    409: "Stale expected_version or duplicate declare.",
    422: "Closed payload or reason rule violated.",
    503: "Storage unavailable.",
}


def refusal(status: int, code: str) -> GovernedError:
    """A triage refusal by status, worded as the triage contract words it."""
    if status == 401:
        return GovernedError(status, code, MESSAGES[status], headers={"WWW-Authenticate": "Bearer"})
    if status == 503:
        return GovernedError(
            status, code, MESSAGES[status], retryable=True, retry_after=RETRY_AFTER_SECONDS
        )
    return GovernedError(status, code, MESSAGES[status])


REFUSALS = Refusals(
    unauthenticated=refusal(401, "authentication_failed"),
    denied=refusal(403, "not_authorized"),
    unavailable=refusal(503, "storage_unavailable"),
)


class TriageHttpService:
    """HTTP boundary for triage commands; the service decides everything else."""

    def __init__(
        self,
        database: Database,
        workflow: IncidentWorkflow,
        investigator: InvestigationDispatcher | None = None,
    ) -> None:
        self._database = database
        self._sessions = database.sessions
        self._investigator = investigator
        self._service = TriageService(database, workflow)
        # The workflow's own resource row, as the triage service reads it. The service checks
        # the grant again inside its transaction, with the human identity linking needs.
        self._gate: Gate[Any] = Gate(self._sessions, REFUSALS, facts=ResourceRepository)

    async def _domain(self, call: Any) -> Any:
        try:
            return await call
        except TriageError as error:
            raise refusal(error.http_status, error.code) from None

    async def post_command(
        self,
        alert_id: str,
        raw: Any,
        authorization: str | None,
        idempotency_key: str | None,
        background: BackgroundTasks | None = None,
    ) -> Response:
        def validate() -> str:
            if idempotency_key is None or re.fullmatch(KEY_PATTERN, idempotency_key) is None:
                raise refusal(400, "invalid_idempotency_key")
            if raw is MALFORMED:
                raise refusal(400, "invalid_command")
            operation = raw.get("operation") if isinstance(raw, dict) else None
            allowed_keys = ALLOWED_KEYS.get(operation) if isinstance(operation, str) else None
            if allowed_keys is None or set(raw) - allowed_keys:
                raise refusal(422, "validation_error")
            expected_version = raw.get("expected_version")
            if isinstance(expected_version, bool) or not isinstance(expected_version, int):
                raise refusal(400, "invalid_command")
            for field in ("reason", "severity", "impact", "target_incident_id"):
                value = raw.get(field)
                if value is not None and not isinstance(value, str):
                    raise refusal(400, "invalid_command")
            try:
                self._service.check(
                    raw["operation"],
                    alert_id,
                    expected_version,
                    raw.get("reason"),
                    raw.get("severity"),
                    raw.get("impact"),
                    raw.get("target_incident_id"),
                    raw.get("alert_context"),
                    idempotency_key,
                )
            except TriageError as error:
                raise refusal(error.http_status, error.code) from None
            return raw["operation"]

        async def command(admission: Admission, operation: str) -> Released:
            result = await self._domain(
                self._service.execute(
                    admission.context.principal,
                    alert_id=alert_id,
                    operation=operation,
                    expected_version=raw["expected_version"],
                    reason=raw.get("reason"),
                    severity=raw.get("severity"),
                    impact=raw.get("impact"),
                    alert_context=raw.get("alert_context"),
                    target_incident_id=raw.get("target_incident_id"),
                    idempotency_key=idempotency_key,
                )
            )
            if (
                result.investigation_run_id is not None
                and result.incident_id is not None
                and self._investigator is not None
                and background is not None
            ):
                background.add_task(
                    self._investigator.dispatch,
                    result.incident_id,
                    result.investigation_run_id,
                )
            return Released(
                {
                    "alert_id": alert_id,
                    "status": result.status,
                    "incident_id": result.incident_id,
                    "expected_version": result.expected_version,
                    "reason": raw.get("reason"),
                    "actor": result.actor,
                    "decided_at": result.decided_at,
                    "decision_origin": result.decision_origin,
                    "responsible_system": result.responsible_system,
                },
                result.http_status,
            )

        return await self._gate.run(
            authorization,
            lambda operation: Scope(ACTIONS[operation], *WORKFLOW),
            command,
            validate=validate,
        )

    async def _read(self, alert_id: str, authorization: str | None, read: Any) -> Response:
        def validate() -> None:
            if not isinstance(alert_id, str) or not is_identifier(alert_id):
                raise refusal(400, "invalid_command")

        async def use_case(admission: Admission, _: None) -> Released:
            return Released(await self._domain(read(admission.context.principal)))

        return await self._gate.run(
            authorization, Scope(READ_ACTION, *WORKFLOW), use_case, validate=validate
        )

    async def get_state(self, alert_id: str, authorization: str | None) -> Response:
        """Contract getAlertTriage: current triage state, no mutation."""
        return await self._read(
            alert_id,
            authorization,
            lambda principal: self._service.read_state(principal, alert_id=alert_id),
        )

    async def get_context(self, alert_id: str, authorization: str | None) -> Response:
        """Return advisory state and domain-authorized next actions."""
        return await self._read(
            alert_id,
            authorization,
            lambda principal: self._service.read_context(principal, alert_id=alert_id),
        )

    async def get_eligible_incidents(self, alert_id: str, authorization: str | None) -> Response:
        """List eligible link destinations without checking alert inventory or triage state."""
        return await self._read(
            alert_id,
            authorization,
            lambda principal: self._service.list_eligible_incidents(principal),
        )


def triage_router(service: TriageHttpService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/alerts/{alert_id}/triage")
    async def get_state(alert_id: str, request: Request) -> Response:
        return await service.get_state(alert_id, request.headers.get("authorization"))

    @router.get("/v1/alerts/{alert_id}/triage/context")
    async def get_context(alert_id: str, request: Request) -> Response:
        return await service.get_context(alert_id, request.headers.get("authorization"))

    @router.get("/v1/alerts/{alert_id}/triage/eligible-incidents")
    async def get_eligible_incidents(alert_id: str, request: Request) -> Response:
        return await service.get_eligible_incidents(alert_id, request.headers.get("authorization"))

    @router.post("/v1/alerts/{alert_id}/triage/commands")
    async def post_command(
        alert_id: str, request: Request, background: BackgroundTasks
    ) -> Response:
        try:
            raw = await request.json()
        except ValueError:
            raw = MALFORMED
        return await service.post_command(
            alert_id,
            raw,
            request.headers.get("authorization"),
            request.headers.get("idempotency-key"),
            background,
        )

    return router
