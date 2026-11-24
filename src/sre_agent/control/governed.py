"""The control plane on the common gate (`sre_agent.gate`).

A control route validates, authenticates, authorizes, runs its use case, audits and answers
through `Gate.run`, with the control wording: a 401 without a challenge, a denial as 403
`resource_unavailable`, and one control audit event per request (subject evidence only once the
principal was authorized).
"""

from collections.abc import Awaitable, Callable
from typing import Any, Generic, TypeVar

from fastapi import Response

from sre_agent.control.operations import RESOURCE_TYPE, ControlOperation
from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import Admission, Gate, Refusals, Released, Terminal
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.authorization import AuthorizationEvaluation
from sre_agent.governance.dto import AuditEvent, PrincipalContext

T = TypeVar("T")

UNAUTHENTICATED = GovernedError(
    401, "authentication_failed", "Authentication failed.", stage="authentication"
)
UNAVAILABLE = GovernedError(
    403, "resource_unavailable", "Resource unavailable.", stage="authorization"
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


class ControlAudit:
    """The control audit event of a request."""

    def __init__(self, store: TransactionalAuditStore, projector: AuditProjector) -> None:
        self.store, self.projector = store, projector

    def event(
        self,
        operation: ControlOperation,
        request_id: Any,
        status: int,
        latency_ms: int,
        stage: str,
        *,
        context: PrincipalContext | None,
        evaluation: AuthorizationEvaluation | None,
        reason: str | None,
    ) -> AuditEvent:
        # Identity, resource and decision only once the principal was authorized; validation,
        # authentication and storage failures carry no subject evidence.
        subject = stage in {"authorization", "response"} and evaluation is not None
        return self.projector.control_event(
            request_id,
            status,
            latency_ms,
            "authorization" if subject else "audit",
            operation=operation.name,
            action=operation.action,
            reason=REASONS.get(reason, reason) if reason is not None else None,
            retryable=status in {500, 503, 504},
            context=context if subject else None,
            resource_ref=(RESOURCE_TYPE, operation.resource_id) if subject else None,
            decision=evaluation.decision if subject and evaluation else None,
            authorization_denial_cause=(
                evaluation.denial_cause if subject and evaluation and status in {403, 404} else None
            ),
        )


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
        return await self.gate.run(
            self.declaration, authorization, self.operation.scope, use_case, validate=validate
        )

    async def _audit(self, terminal: Terminal) -> None:
        reason = terminal.error.code if terminal.error is not None else self.reason
        await self.audit.store.append(
            self.audit.event(
                self.operation,
                terminal.request_id,
                terminal.status,
                terminal.latency_ms,
                terminal.stage,
                context=terminal.context,
                evaluation=terminal.evaluation,
                reason=reason,
            )
        )
