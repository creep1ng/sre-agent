"""The control plane on the common gate (`sre_agent.gate`).

A control route validates, authenticates, authorizes, runs its use case, audits and answers
through `Gate.run`, with the control wording: a 401 without a challenge, a denial as 403
`resource_unavailable`, and one control audit event per request (subject evidence only once the
principal was authorized). A mutation that must not persist without its audit writes that event
inside its own transaction (`ControlAudit.within`): the write and the mutation commit or roll back
together, and the gate's auditor does not write it again.
"""

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, Generic, TypeVar

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.control.operations import RESOURCE_TYPE, ControlOperation
from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import Admission, Gate, Refusals, Released, Terminal, failing_as
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import AuditEvent

T = TypeVar("T")

IDEMPOTENCY_KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
INVALID_IDEMPOTENCY_KEY = GovernedError(
    400,
    "invalid_idempotency_key",
    "The Idempotency-Key header is missing or invalid.",
    stage="validation",
)
INVALID = GovernedError(422, "validation_error", "The request is invalid.", stage="validation")
UNAUTHENTICATED = GovernedError(
    401, "authentication_failed", "Authentication failed.", stage="authentication"
)
UNAVAILABLE = GovernedError(
    403, "resource_unavailable", "Resource unavailable.", stage="authorization"
)
NOT_FOUND = GovernedError(404, "resource_not_found", "The requested resource was not found.")
IDEMPOTENCY_CONFLICT = GovernedError(
    409, "idempotency_conflict", "The Idempotency-Key was already used with another payload."
)
STATUS_CONFLICT = GovernedError(
    409, "status_conflict", "The status was changed by another request."
)
AUDIT_UNAVAILABLE = GovernedError(
    503, "audit_unavailable", "Audit unavailable.", retryable=True, stage="audit"
)
# Storage failures while authenticating or authorizing escape as a 500, as they always did.
REFUSALS = Refusals(
    denied=UNAVAILABLE,
    unavailable=AUDIT_UNAVAILABLE,
    unavailable_on=(),
    unauthenticated=UNAUTHENTICATED,
    audit_unavailable=AUDIT_UNAVAILABLE,
)
# The audit reason of each control error code; any other code is its own reason.
REASONS = {
    "validation_error": "contract_validation_failed",
    "invalid_idempotency_key": "contract_validation_failed",
    "idempotency_conflict": "status_conflict",
    "grant_conflict": "status_conflict",
    "grant_id_conflict": "status_conflict",
    "credential_inactive": "contract_validation_failed",
    "rotation_failed": "upstream_failed",
    "credential_issuance_failed": "upstream_failed",
    "resource_unavailable": "no_matching_grant",
    "policy_unavailable": "upstream_unavailable",
}
# Facts a route's use case leaves for the auditor (`Admission.facts`).
_STARTED, _SETTLED, _REASON = "control.started", "control.settled", "control.reason"


def canonical_payload(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_payload(payload).encode()).hexdigest()


def key_digest(key: str) -> str:
    return hashlib.sha256(f"sre-idempotency-v1\0{key}".encode()).hexdigest()


def page_limit(limit: Any, extra: dict[str, Any]) -> int:
    """A list's `limit` (1 to 100, digits only); any other query parameter is invalid."""
    try:
        parsed = int(limit)
        if isinstance(limit, str) and not limit.isdigit():
            raise ValueError
    except (TypeError, ValueError):
        parsed = 0
    if extra or not 1 <= parsed <= 100:
        raise INVALID
    return parsed


def idempotency_key(value: str | None) -> str:
    """The request's Idempotency-Key, or the control refusal of a missing or malformed one."""
    if value is None or re.match(IDEMPOTENCY_KEY_PATTERN, value) is None:
        raise INVALID_IDEMPOTENCY_KEY
    return value


def unaudited(admission: Admission, status: int) -> None:
    """The use case answers `status` without an audit row (an idempotent replay)."""
    admission.facts[_SETTLED] = status


def audited_as(admission: Admission, reason: str) -> None:
    """The audit reason of a refusal the route answers with its own body (a rotation failure)."""
    admission.facts[_REASON] = reason


class ControlAudit:
    """The control audit event of a request, written after it ends or inside its transaction."""

    def __init__(self, store: TransactionalAuditStore, projector: AuditProjector) -> None:
        self.store, self.projector = store, projector

    def event(
        self, operation: ControlOperation, terminal: Terminal, reason: str | None
    ) -> AuditEvent:
        # Identity, resource and decision only once the principal was authorized; validation,
        # authentication and storage failures carry no subject evidence.
        evaluation, status = terminal.evaluation, terminal.status
        subject = terminal.stage in {"authorization", "response"} and evaluation is not None
        return self.projector.control_event(
            terminal.request_id,
            status,
            terminal.latency_ms,
            "authorization" if subject else "audit",
            operation=operation.name,
            action=operation.action,
            reason=REASONS.get(reason, reason) if reason is not None else None,
            retryable=status in {500, 503, 504},
            context=terminal.context if subject else None,
            resource_ref=(RESOURCE_TYPE, operation.resource_id) if subject else None,
            decision=evaluation.decision if subject and evaluation else None,
            authorization_denial_cause=(
                evaluation.denial_cause if subject and evaluation and status in {403, 404} else None
            ),
        )

    async def within(
        self,
        operation: ControlOperation,
        admission: Admission,
        session: AsyncSession,
        status: int,
        reason: str | None,
    ) -> None:
        """Write the request's audit in the mutation's transaction; a failed write answers
        `audit_unavailable`, and raising it inside the transaction rolls the mutation back."""
        # A failed write is answered as `audit_unavailable` and not audited again.
        admission.facts[_SETTLED] = AUDIT_UNAVAILABLE.status
        with failing_as(AUDIT_UNAVAILABLE):
            # The answer this transaction commits with, as the gate records a released one.
            terminal = Terminal(
                admission.request_id,
                _latency(admission.facts),
                status,
                "authorization",
                admission.context,
                admission.evaluation,
                None,
                admission.facts,
            )
            event = self.event(operation, terminal, reason)
            await self.store.append_in_transaction(event, session)
        admission.facts[_SETTLED] = status


def _latency(facts: dict[str, Any]) -> int:
    return max(0, int((monotonic() - facts[_STARTED]) * 1000))


# Writes the request's audit, answering the given status (and reason, if not the route's own),
# inside the given transaction; the use case calls it before its transaction commits.
Record = Callable[..., Awaitable[None]]


class ControlGate(Generic[T]):
    """One control operation on the common gate, audited as a control event. `reason` is the
    audit reason of its successes (`grant_matched` on the routes that record it)."""

    def __init__(
        self,
        sessions: Any,
        audit: ControlAudit,
        operation: ControlOperation,
        *,
        reason: str | None = None,
        refusals: Refusals = REFUSALS,
    ) -> None:
        self.audit, self.operation, self.reason = audit, operation, reason
        self.declaration = operation.declare()
        self.gate: Gate[T] = Gate(sessions, refusals, audit=self._audit)

    async def run(
        self,
        authorization: str | None,
        use_case: Callable[[Admission, T], Awaitable[Released | Response]],
        validate: Callable[[], T] | None = None,
    ) -> Response:
        started = monotonic()

        async def timed(admission: Admission, request: T) -> Released | Response:
            admission.facts[_STARTED] = started
            return await use_case(admission, request)

        return await self.gate.run(
            self.declaration, authorization, self.operation.scope, timed, validate=validate
        )

    def record(self, admission: Admission) -> Record:
        """The in-transaction audit of this request."""
        return lambda session, status, reason=None: self.audit.within(
            self.operation, admission, session, status, reason or self.reason
        )

    async def _audit(self, terminal: Terminal) -> None:
        if terminal.facts.get(_SETTLED) == terminal.status:
            return
        error = terminal.error
        reason = error.code if error is not None else terminal.facts.get(_REASON, self.reason)
        await self.audit.store.append(self.audit.event(self.operation, terminal, reason))
