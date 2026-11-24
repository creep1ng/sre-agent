# ruff: noqa: E501, I001

import re
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import (
    Response,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.control.governed import IDEMPOTENCY_KEY_PATTERN
from sre_agent.gate.authentication import bearer_key
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import (
    Principal,
    PrincipalContext,
)
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository, ResourceRepository  # fmt: skip

ERRORS: dict[int, tuple[str, str]] = {
    400: ("invalid_idempotency_key", "The Idempotency-Key header is missing or invalid."),
    401: ("authentication_failed", "Authentication failed."),
    403: ("resource_unavailable", "Resource unavailable."),
    404: ("resource_not_found", "The requested resource was not found."),
    409: ("idempotency_conflict", "The Idempotency-Key was already used with another payload."),
    422: ("validation_error", "The request is invalid."),
    500: ("credential_issuance_failed", "Credential issuance could not be completed."),
    503: ("audit_unavailable", "Audit unavailable."),
}
ERROR_MESSAGES = {
    "policy_unavailable": "The consumption policy is unavailable.",
    "status_conflict": "The status was changed by another request.",
    "grant_conflict": "An active grant with this principal, action and resource already exists.",
    "grant_id_conflict": "A grant with this grant_id already exists, active or revoked.",
    "credential_inactive": "The credential is not active.",
    "credential_issuance_failed": "Credential issuance could not be completed.",
}


class ListPrincipalsQuery(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    limit: int = Field(default=100, ge=1, le=100)


SAFE_ERROR_MESSAGE_PATTERN = r"^(?!.*(?:Authorization|Bearer\s|sk-[A-Za-z0-9])).*$"


class ErrorFieldDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Annotated[str, Field(min_length=1, max_length=100)]
    message: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            json_schema_extra={"pattern": SAFE_ERROR_MESSAGE_PATTERN},
        ),
    ]


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")]
    message: Annotated[
        str,
        Field(
            min_length=1,
            max_length=300,
            json_schema_extra={"pattern": SAFE_ERROR_MESSAGE_PATTERN},
        ),
    ]
    details: Annotated[list[ErrorFieldDetail], Field(max_length=16)] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ErrorDetail
    request_id: UUID
    retryable: bool


class ControlService:  # noqa: E305
    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.sessions, self.audit, self.projector = sessions, audit, projector

    def _invalid_key(self, value: str | None) -> bool:
        return value is None or re.match(IDEMPOTENCY_KEY_PATTERN, value) is None

    async def _authenticate(self, authorization: str | None) -> PrincipalContext | None:
        key = bearer_key(authorization)
        if key is None:
            return None
        async with self.sessions() as session:
            return await CredentialRepository(session).resolve_authorization_context(key)

    async def _authorize(self, session, principal: Principal, scope: tuple[str, str, str]):
        action, resource_type, resource_id = scope
        return await AuthorizationDecisionEngine(
            ResourceRepository(session), GrantRepository(session)
        ).evaluate(principal, action, resource_type, resource_id)

    async def _finish(
        self,
        request_id: UUID,
        started: float,
        status: int,
        stage: Literal["validation", "authentication", "authorization", "audit"],
        operation: str,
        action: Literal["admin.read", "admin.write"],
        *,
        payload: dict[str, Any] | None = None,
        error_code: str | None = None,
        context: PrincipalContext | None = None,
        resource_ref: tuple[str, str] | None = None,
        decision: Any = None,
        authorization_denial_cause: Any = None,
        audit_session: AsyncSession | None = None,
    ) -> JSONResponse:
        # Terminal audit events must satisfy the control AuditEvent validator:
        # stage=authorization carries identity+resource+decision (no alias);
        # any other stage carries no subject evidence. reason_code mirrors the
        # public error_code so 403 deny evidence stays consistent.
        audit_stage = stage if stage == "authorization" else "audit"
        audit_context = context if audit_stage == "authorization" else None
        audit_resource = resource_ref if audit_stage == "authorization" else None
        audit_decision = decision if audit_stage == "authorization" else None
        audit_cause = (
            authorization_denial_cause
            if audit_stage == "authorization" and status in {403, 404}
            else None
        )
        audit_reason = {
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
        }.get(error_code, error_code)
        try:
            event = self.projector.control_event(
                request_id,
                status,
                max(0, int((monotonic() - started) * 1000)),
                audit_stage,
                operation=operation,
                action=action,
                reason=audit_reason,
                retryable=status in {500, 503, 504},
                context=audit_context,
                resource_ref=audit_resource,
                decision=audit_decision,
                authorization_denial_cause=audit_cause,
            )
            if audit_session is None:
                await self.audit.append(event)
            else:
                await self.audit.append_in_transaction(event, audit_session)
        except Exception:
            error_code, status, payload = "audit_unavailable", 503, None
        if payload is not None and status != 204:
            return JSONResponse(payload, status_code=status)
        if status == 204:
            return Response(status_code=204)
        code, message = error_code or ERRORS[status][0], ERRORS[status][1]
        message = ERROR_MESSAGES.get(code, message)
        message = "Audit unavailable." if code == "audit_unavailable" else message
        return JSONResponse(
            {
                "error": {"code": code, "message": message},
                "request_id": str(request_id),
                "retryable": status in {500, 503, 504},
            },
            status,
        )
