# ruff: noqa: E501, I001

import hashlib
import json
import re
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Request,
    Response,
    Security,
)
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from pydantic.json_schema import WithJsonSchema

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import CredentialReference, Principal, PrincipalContext
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository, IdempotencyConflictError, IdempotencyOutcome, IdempotencyRepository, PrincipalRepository, ResourceRepository, StaleWriteError  # fmt: skip

IDEMPOTENCY_KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
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
    "status_conflict": "The principal status was changed by another request.",
    "credential_inactive": "The credential is not active.",
    "credential_issuance_failed": "Credential issuance could not be completed.",
}
CONTROL_OPERATIONS: dict[tuple[str, str], tuple[str, str, str, str]] = {
    ("POST", "/v1/principals"): (
        "principals.create",
        "admin.write",
        "administrative_control",
        "principals",
    ),
    ("GET", "/v1/principals"): (
        "principals.list",
        "admin.read",
        "administrative_control",
        "principals",
    ),
    ("GET", "/v1/principals/{id}"): (
        "principals.get",
        "admin.read",
        "administrative_control",
        "principals",
    ),
    ("PUT", "/v1/principals/{id}/status"): (
        "principals.status.replace",
        "admin.write",
        "administrative_control",
        "principals",
    ),
    ("POST", "/v1/principals/{id}/credentials"): (
        "credentials.issue",
        "admin.write",
        "administrative_control",
        "credentials",
    ),
    ("GET", "/v1/principals/{id}/credentials"): (
        "credentials.list",
        "admin.read",
        "administrative_control",
        "credentials",
    ),
    ("DELETE", "/v1/credentials/{id}"): (
        "credentials.revoke",
        "admin.write",
        "administrative_control",
        "credentials",
    ),
    ("POST", "/v1/credentials/{id}/rotation"): (
        "credentials.rotate",
        "admin.write",
        "administrative_control",
        "credentials",
    ),
}
assert set(CONTROL_OPERATIONS) == set(CONTROL_SCOPES)
assert all(CONTROL_OPERATIONS[route][1:] == scope for route, scope in CONTROL_SCOPES.items())


class PrincipalCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    principal_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")]
    kind: Annotated[str, Field(pattern=r"^(human|agent)$")]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]


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


class PrincipalListResponse(BaseModel):
    items: list[Principal]
    limit: int
    truncated: bool


class StatusReplace(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    status: Literal["active", "inactive"]
    expected_updated_at: AwareDatetime


class CredentialIssue(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    expires_at: AwareDatetime | None = None


class CredentialIssueResponse(BaseModel):
    credential: CredentialReference
    replaced_credential_id: str | None
    key: str
    secret_revealed: Literal[True]


class CredentialMetadataResponse(BaseModel):
    credential: CredentialReference
    replaced_credential_id: str | None
    secret_revealed: Literal[False]


class CredentialRotationResponse(BaseModel):
    result: Literal["success"]
    old_credential: CredentialReference
    issuance: CredentialIssueResponse | CredentialMetadataResponse
    replacement_count: Literal[1]
    transition_count: Literal[1]
    replayed: bool


class RotationIssuanceFailure(RuntimeError):
    """A replacement key could not be issued after the old credential was locked."""


class CredentialRotationFailureResponse(BaseModel):
    result: Literal["failure"]
    old_credential: CredentialReference
    replacement_count: Literal[0]
    transition_count: Literal[0]
    replayed: Literal[False]
    error_code: Literal["credential_inactive", "rotation_failed"]


class CredentialListResponse(BaseModel):
    items: list[CredentialReference]
    limit: int
    truncated: bool


def _canonical_payload(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_payload(payload).encode()).hexdigest()


def _key_digest(key: str) -> str:
    return hashlib.sha256(f"sre-idempotency-v1\0{key}".encode()).hexdigest()


def _public_principal(principal: Principal) -> dict[str, Any]:
    return principal.model_dump(mode="json")


class ControlService:  # noqa: E305
    def __init__(self, sessions: Any, audit: Any, projector: AuditProjector) -> None:
        self.sessions, self.audit, self.projector = sessions, audit, projector

    def _invalid_key(self, value: str | None) -> bool:
        return value is None or re.match(IDEMPOTENCY_KEY_PATTERN, value) is None

    async def _authenticate(self, authorization: str | None) -> PrincipalContext | None:
        scheme, separator, key = authorization.partition(" ") if authorization else ("", "", "")
        if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
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
            "idempotency_conflict": "contract_validation_failed",
            "credential_inactive": "contract_validation_failed",
            "rotation_failed": "upstream_failed",
            "credential_issuance_failed": "upstream_failed",
            "resource_unavailable": "no_matching_grant",
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
            await self.audit.append(event)
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

    async def _rotation_failure(
        self,
        request_id: UUID,
        started: float,
        context: PrincipalContext,
        decision: Any,
        old_credential: CredentialReference,
        error_code: Literal["credential_inactive", "rotation_failed"],
    ) -> Response:
        return await self._finish(
            request_id,
            started,
            409,
            "authorization",
            "credentials.rotate",
            "admin.write",
            payload={
                "result": "failure",
                "old_credential": old_credential.model_dump(mode="json"),
                "replacement_count": 0,
                "transition_count": 0,
                "replayed": False,
                "error_code": error_code,
            },
            error_code=error_code,
            context=context,
            resource_ref=("administrative_control", "credentials"),
            decision=decision,
        )

    async def create_principal(
        self, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        operation, action = "principals.create", "admin.write"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        if self._invalid_key(idempotency_key):
            return await self._finish(
                request_id,
                started,
                400,
                "validation",
                operation,
                action,
                error_code="invalid_idempotency_key",
            )
        try:
            body = PrincipalCreate.model_validate(raw)
        except ValidationError:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        scope = ("POST", "/v1/principals")
        payload_hash = _payload_sha256(body.model_dump(mode="json"))
        canonical_path = "/v1/principals"
        async with self.sessions() as session:
            evaluation = await self._authorize(session, context.principal, CONTROL_SCOPES[scope])
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                403,
                "authorization",
                operation,
                action,
                error_code="resource_unavailable",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        binding_scope = f"{context.principal.principal_id}|POST|{canonical_path}"
        try:
            async with self.sessions() as session, session.begin():
                binding = await IdempotencyRepository(session).claim_or_replay(
                    scope=binding_scope,
                    key_digest=_key_digest(idempotency_key or ""),
                    payload_sha256=payload_hash,
                    principal_id=context.principal.principal_id,
                    method="POST",
                    canonical_path=canonical_path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=body.principal_id, replayed=False
                    ),
                )
                if binding.replayed:
                    principal = await PrincipalRepository(session).get(binding.outcome.resource_id)
                    payload = _public_principal(principal) if principal else None
                    status = binding.outcome.response_status
                else:
                    try:
                        principal = await PrincipalRepository(session).create(
                            body.principal_id, body.kind, body.display_name
                        )
                    except Exception:
                        await session.rollback()
                        return await self._finish(
                            request_id,
                            started,
                            409,
                            "authorization",
                            operation,
                            action,
                            error_code="idempotency_conflict",
                            context=context,
                            resource_ref=("administrative_control", "principals"),
                            decision=evaluation.decision,
                        )
                    payload, status = _public_principal(principal), 201
        except IdempotencyConflictError:
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code="idempotency_conflict",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            status,
            "authorization",
            operation,
            action,
            payload=payload,
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=evaluation.decision,
        )

    async def list_principals(
        self, authorization: str | None, limit: Any, extra_params: dict[str, Any]
    ) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        operation, action = "principals.list", "admin.read"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        try:
            parsed_limit = int(limit)
            if isinstance(limit, str) and not limit.isdigit():
                raise ValueError
            ListPrincipalsQuery.model_validate({"limit": parsed_limit})
        except (TypeError, ValueError, ValidationError):
            parsed_limit = 0
        if extra_params or not 1 <= parsed_limit <= 100:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session, context.principal, CONTROL_SCOPES[("GET", "/v1/principals")]
            )
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            items, truncated = await PrincipalRepository(session).list(limit=parsed_limit)
        payload: dict[str, Any] = {
            "items": [_public_principal(item) for item in items],
            "limit": parsed_limit,
            "truncated": truncated,
        }
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload=payload,
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=evaluation.decision,
        )

    async def get_principal(self, principal_id: str, authorization: str | None) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        operation, action = "principals.get", "admin.read"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        if re.match(r"^[a-z][a-z0-9_-]{2,63}$", principal_id) is None:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session, context.principal, CONTROL_SCOPES[("GET", "/v1/principals/{id}")]
            )
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            principal = await PrincipalRepository(session).get(principal_id)
        if principal is None:
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload=_public_principal(principal),
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=evaluation.decision,
        )

    async def replace_principal_status(
        self, principal_id: str, raw: Any, authorization: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "principals.status.replace", "admin.write"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        if re.match(r"^[a-z][a-z0-9_-]{2,63}$", principal_id) is None:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        try:
            body = StatusReplace.model_validate_json(_canonical_payload(raw))
        except (TypeError, ValidationError):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session, context.principal, CONTROL_SCOPES[("PUT", "/v1/principals/{id}/status")]
            )
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                403,
                "authorization",
                operation,
                action,
                error_code="resource_unavailable",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        try:
            async with self.sessions() as session, session.begin():
                principal = await PrincipalRepository(session).replace_status(
                    principal_id, body.status, expected_updated_at=body.expected_updated_at
                )
        except StaleWriteError:
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code="status_conflict",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
            )
        if principal is None:
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "principals"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload=_public_principal(principal),
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=evaluation.decision,
        )

    async def issue_credential(
        self, principal_id: str, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "credentials.issue", "admin.write"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        if self._invalid_key(idempotency_key):
            return await self._finish(
                request_id,
                started,
                400,
                "validation",
                operation,
                action,
                error_code="invalid_idempotency_key",
            )
        if re.match(r"^[a-z][a-z0-9_-]{2,63}$", principal_id) is None:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        try:
            body = CredentialIssue.model_validate_json(_canonical_payload(raw))
        except (TypeError, ValidationError):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("POST", "/v1/principals/{id}/credentials")],
            )
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                403,
                "authorization",
                operation,
                action,
                error_code="resource_unavailable",
                context=context,
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        canonical_path = f"/v1/principals/{principal_id}/credentials"
        payload_hash = _payload_sha256(body.model_dump(mode="json"))
        try:
            async with self.sessions() as session, session.begin():
                if await PrincipalRepository(session).get(principal_id) is None:
                    return await self._finish(
                        request_id,
                        started,
                        404,
                        "authorization",
                        operation,
                        action,
                        error_code="resource_not_found",
                        context=context,
                        resource_ref=("administrative_control", "credentials"),
                        decision=evaluation.decision,
                    )
                binding = await IdempotencyRepository(session).claim_or_replay(
                    scope=f"{context.principal.principal_id}|POST|{canonical_path}",
                    key_digest=_key_digest(idempotency_key or ""),
                    payload_sha256=payload_hash,
                    principal_id=context.principal.principal_id,
                    method="POST",
                    canonical_path=canonical_path,
                    binding="principal_lifetime",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=principal_id, replayed=False
                    ),
                )
                if binding.replayed:
                    payload = binding.outcome.response_payload
                else:
                    try:
                        issued = await CredentialRepository(session).issue(
                            principal_id, expires_at=body.expires_at
                        )
                    except Exception:
                        await session.rollback()
                        return await self._finish(
                            request_id,
                            started,
                            500,
                            "authorization",
                            operation,
                            action,
                            error_code="credential_issuance_failed",
                            context=context,
                            resource_ref=("administrative_control", "credentials"),
                            decision=evaluation.decision,
                        )
                    metadata = {
                        "credential": issued.credential.model_dump(mode="json"),
                        "replaced_credential_id": None,
                        "secret_revealed": False,
                    }
                    await IdempotencyRepository(session).set_response_payload(
                        scope=f"{context.principal.principal_id}|POST|{canonical_path}",
                        key_digest=_key_digest(idempotency_key or ""),
                        response_payload=metadata,
                    )
                    payload = {**metadata, "key": issued.key, "secret_revealed": True}
        except IdempotencyConflictError:
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code="idempotency_conflict",
                context=context,
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            201,
            "authorization",
            operation,
            action,
            payload=payload,
            context=context,
            resource_ref=("administrative_control", "credentials"),
            decision=evaluation.decision,
        )

    async def list_credentials(
        self, principal_id: str, authorization: str | None, limit: Any, extra_params: dict[str, Any]
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "credentials.list", "admin.read"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        try:
            parsed_limit = int(limit)
            if isinstance(limit, str) and not limit.isdigit():
                raise ValueError
            ListPrincipalsQuery.model_validate({"limit": parsed_limit})
        except (TypeError, ValueError, ValidationError):
            parsed_limit = 0
        if (
            re.match(r"^[a-z][a-z0-9_-]{2,63}$", principal_id) is None
            or extra_params
            or not 1 <= parsed_limit <= 100
        ):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("GET", "/v1/principals/{id}/credentials")],
            )
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            if await PrincipalRepository(session).get(principal_id) is None:
                return await self._finish(
                    request_id,
                    started,
                    404,
                    "authorization",
                    operation,
                    action,
                    error_code="resource_not_found",
                    context=context,
                    resource_ref=("administrative_control", "credentials"),
                    decision=evaluation.decision,
                )
            items, truncated = await CredentialRepository(session).list_for_principal(
                principal_id, limit=parsed_limit
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload={
                "items": [item.model_dump(mode="json") for item in items],
                "limit": parsed_limit,
                "truncated": truncated,
            },
            context=context,
            resource_ref=("administrative_control", "credentials"),
            decision=evaluation.decision,
        )

    async def revoke_credential(self, credential_id: str, authorization: str | None) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "credentials.revoke", "admin.write"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        if re.match(r"^[a-z][a-z0-9_-]{2,63}$", credential_id) is None:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session, context.principal, CONTROL_SCOPES[("DELETE", "/v1/credentials/{id}")]
            )
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                403,
                "authorization",
                operation,
                action,
                error_code="resource_unavailable",
                context=context,
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session, session.begin():
            if await CredentialRepository(session).get(credential_id) is None:
                return await self._finish(
                    request_id,
                    started,
                    404,
                    "authorization",
                    operation,
                    action,
                    error_code="resource_not_found",
                    context=context,
                    resource_ref=("administrative_control", "credentials"),
                    decision=evaluation.decision,
                )
            await CredentialRepository(session).revoke(credential_id)
        return await self._finish(
            request_id,
            started,
            204,
            "authorization",
            operation,
            action,
            context=context,
            resource_ref=("administrative_control", "credentials"),
            decision=evaluation.decision,
        )

    async def rotate_credential(
        self, credential_id: str, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "credentials.rotate", "admin.write"
        context = await self._authenticate(authorization)
        if context is None:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
            )
        if self._invalid_key(idempotency_key):
            return await self._finish(
                request_id,
                started,
                400,
                "validation",
                operation,
                action,
                error_code="invalid_idempotency_key",
            )
        if re.match(r"^[a-z][a-z0-9_-]{2,63}$", credential_id) is None:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        try:
            body = CredentialIssue.model_validate_json(_canonical_payload(raw))
        except (TypeError, ValidationError):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("POST", "/v1/credentials/{id}/rotation")],
            )
        if evaluation.decision.decision == "deny":
            return await self._finish(
                request_id,
                started,
                403,
                "authorization",
                operation,
                action,
                error_code="resource_unavailable",
                context=context,
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        canonical_path = f"/v1/credentials/{credential_id}/rotation"
        try:
            async with self.sessions() as session, session.begin():
                old_credential = await CredentialRepository(session).get(credential_id)
                if old_credential is None:
                    return await self._finish(
                        request_id,
                        started,
                        404,
                        "authorization",
                        operation,
                        action,
                        error_code="resource_not_found",
                        context=context,
                        resource_ref=("administrative_control", "credentials"),
                        decision=evaluation.decision,
                    )
                binding = await IdempotencyRepository(session).claim_or_replay(
                    scope=f"{context.principal.principal_id}|POST|{canonical_path}",
                    key_digest=_key_digest(idempotency_key or ""),
                    payload_sha256=_payload_sha256(body.model_dump(mode="json")),
                    principal_id=context.principal.principal_id,
                    method="POST",
                    canonical_path=canonical_path,
                    binding="principal_lifetime",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=credential_id, replayed=False
                    ),
                )
                if binding.replayed:
                    payload = {**binding.outcome.response_payload, "replayed": True}
                elif old_credential.status != "active":
                    await session.rollback()
                    return await self._rotation_failure(
                        request_id,
                        started,
                        context,
                        evaluation.decision,
                        old_credential,
                        "credential_inactive",
                    )
                else:
                    try:
                        issued = await CredentialRepository(session).rotate(
                            credential_id, expires_at=body.expires_at
                        )
                    except Exception:
                        await session.rollback()
                        return await self._rotation_failure(
                            request_id,
                            started,
                            context,
                            evaluation.decision,
                            old_credential,
                            "rotation_failed",
                        )
                    if issued is None:
                        await session.rollback()
                        return await self._rotation_failure(
                            request_id,
                            started,
                            context,
                            evaluation.decision,
                            old_credential,
                            "credential_inactive",
                        )
                    metadata = {
                        "result": "success",
                        "old_credential": old_credential.model_dump(mode="json"),
                        "issuance": {
                            "credential": issued.credential.model_dump(mode="json"),
                            "replaced_credential_id": old_credential.credential_id,
                            "secret_revealed": False,
                        },
                        "replacement_count": 1,
                        "transition_count": 1,
                        "replayed": False,
                    }
                    await IdempotencyRepository(session).set_response_payload(
                        scope=f"{context.principal.principal_id}|POST|{canonical_path}",
                        key_digest=_key_digest(idempotency_key or ""),
                        response_payload=metadata,
                    )
                    payload = {
                        **metadata,
                        "issuance": {
                            **metadata["issuance"],
                            "key": issued.key,
                            "secret_revealed": True,
                        },
                    }
        except IdempotencyConflictError:
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code="idempotency_conflict",
                context=context,
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            201,
            "authorization",
            operation,
            action,
            payload=payload,
            context=context,
            resource_ref=("administrative_control", "credentials"),
            decision=evaluation.decision,
        )


def control_router(service: ControlService) -> APIRouter:
    """Typed administrative control-plane router with all eight Issue #147 routes."""
    router = APIRouter()
    bearer_scheme = HTTPBearer(auto_error=False, description="Administrative bearer credential")
    bearer_credentials: Any = Security(bearer_scheme)

    @router.post(
        "/v1/principals",
        status_code=201,
        response_model=Principal,
        responses={
            400: {"model": ErrorEnvelope, "description": "Invalid idempotency key"},
            401: {"model": ErrorEnvelope, "description": "Authentication failed"},
            403: {"model": ErrorEnvelope, "description": "Resource unavailable"},
            409: {"model": ErrorEnvelope, "description": "Idempotency conflict"},
            422: {"model": ErrorEnvelope, "description": "Validation error"},
            503: {"model": ErrorEnvelope, "description": "Audit unavailable"},
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "description": "Scoped idempotency key (mutating POST only)",
                    "schema": {
                        "type": "string",
                        "minLength": 16,
                        "maxLength": 128,
                        "pattern": IDEMPOTENCY_KEY_PATTERN,
                    },
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": PrincipalCreate.model_json_schema()}},
            },
        },
    )
    async def create_principal(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        try:
            body = await request.json()
        except Exception:
            body = None
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        result = await service.create_principal(
            body,
            authorization or request.headers.get("authorization"),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/principals",
        response_model=PrincipalListResponse,
        responses={
            401: {"model": ErrorEnvelope, "description": "Authentication failed"},
            404: {"model": ErrorEnvelope, "description": "Resource unavailable"},
            422: {"model": ErrorEnvelope, "description": "Validation error"},
            503: {"model": ErrorEnvelope, "description": "Audit unavailable"},
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
                }
            ]
        },
    )
    async def list_principals(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        limit = request.query_params.get("limit", "100")
        params = {k: v for k, v in request.query_params.items() if k != "limit"}
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        result = await service.list_principals(
            authorization or request.headers.get("authorization"), limit, params
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/principals/{principal_id}",
        response_model=Principal,
        responses={
            401: {"model": ErrorEnvelope, "description": "Authentication failed"},
            404: {"model": ErrorEnvelope, "description": "Resource unavailable"},
            422: {"model": ErrorEnvelope, "description": "Validation error"},
            503: {"model": ErrorEnvelope, "description": "Audit unavailable"},
        },
    )
    async def get_principal(
        principal_id: Annotated[
            str,
            WithJsonSchema({"type": "string", "pattern": r"^[a-z][a-z0-9_-]{2,63}$"}),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        result = await service.get_principal(
            principal_id, authorization or request.headers.get("authorization")
        )
        response.status_code = result.status_code
        return result

    async def raw_json(request: Request) -> Any:
        try:
            return await request.json()
        except Exception:
            return None

    def authorization_from(
        credentials: HTTPAuthorizationCredentials | None, request: Request
    ) -> str | None:
        if credentials is not None:
            return f"{credentials.scheme} {credentials.credentials}"
        return request.headers.get("authorization")

    @router.put(
        "/v1/principals/{principal_id}/status",
        response_model=Principal,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
    )
    async def replace_principal_status(
        principal_id: str,
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.replace_principal_status(
            principal_id, await raw_json(request), authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

    @router.post(
        "/v1/principals/{principal_id}/credentials",
        status_code=201,
        response_model=CredentialIssueResponse | CredentialMetadataResponse,
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            500: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {
                        "type": "string",
                        "minLength": 16,
                        "maxLength": 128,
                        "pattern": IDEMPOTENCY_KEY_PATTERN,
                    },
                }
            ]
        },
    )
    async def issue_credential(
        principal_id: str,
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.issue_credential(
            principal_id,
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/principals/{principal_id}/credentials",
        response_model=CredentialListResponse,
        responses={
            401: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
    )
    async def list_credentials(
        principal_id: str,
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.list_credentials(
            principal_id,
            authorization_from(credentials, request),
            request.query_params.get("limit", "100"),
            {key: value for key, value in request.query_params.items() if key != "limit"},
        )
        response.status_code = result.status_code
        return result

    @router.delete(
        "/v1/credentials/{credential_id}",
        status_code=204,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
    )
    async def revoke_credential(
        credential_id: str,
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.revoke_credential(
            credential_id, authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

    @router.post(
        "/v1/credentials/{credential_id}/rotation",
        status_code=201,
        response_model=CredentialRotationResponse | CredentialRotationFailureResponse,
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            409: {"model": CredentialRotationFailureResponse | ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {
                        "type": "string",
                        "minLength": 16,
                        "maxLength": 128,
                        "pattern": IDEMPOTENCY_KEY_PATTERN,
                    },
                }
            ]
        },
    )
    async def rotate_credential(
        credential_id: str,
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.rotate_credential(
            credential_id,
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    return router
