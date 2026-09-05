# ruff: noqa: E501, I001

import hashlib
import json
import re
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Header,
    Path,
    Query,
    Request,
    Response,
    Security,
)
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import Principal, PrincipalContext
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository, IdempotencyConflictError, IdempotencyOutcome, IdempotencyRepository, PrincipalRepository, ResourceRepository  # fmt: skip

IDEMPOTENCY_KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
ERRORS: dict[int, tuple[str, str]] = {
    400: ("invalid_idempotency_key", "The Idempotency-Key header is missing or invalid."),
    401: ("authentication_failed", "Authentication failed."),
    403: ("resource_unavailable", "Resource unavailable."),
    404: ("resource_not_found", "The requested resource was not found."),
    409: ("idempotency_conflict", "The Idempotency-Key was already used with another payload."),
    422: ("validation_error", "The request is invalid."),
    503: ("audit_unavailable", "Audit unavailable."),
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
            authorization_denial_cause if audit_stage == "authorization" and status == 403 else None
        )
        try:
            event = self.projector.control_event(
                request_id,
                status,
                max(0, int((monotonic() - started) * 1000)),
                audit_stage,
                operation=operation,
                action=action,
                reason=error_code,
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
            return JSONResponse(None, status_code=204)
        code, message = error_code or ERRORS[status][0], ERRORS[status][1]
        message = "Audit unavailable." if code == "audit_unavailable" else message
        return JSONResponse(
            {
                "error": {"code": code, "message": message},
                "request_id": str(request_id),
                "retryable": status in {503, 504},
            },
            status,
        )

    async def create_principal(
        self, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        operation, action = "principals.create", "admin.write"
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
            "audit",
            operation,
            action,
            payload=payload,
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=evaluation.decision,
        )

    async def list_principals(
        self, authorization: str | None, limit: int, extra_params: dict[str, Any]
    ) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        operation, action = "principals.list", "admin.read"
        if extra_params or not 1 <= limit <= 100:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
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
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session, context.principal, CONTROL_SCOPES[("GET", "/v1/principals")]
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
        async with self.sessions() as session:
            items, truncated = await PrincipalRepository(session).list(limit=limit)
        payload: dict[str, Any] = {
            "items": [_public_principal(item) for item in items],
            "limit": limit,
            "truncated": truncated,
        }
        return await self._finish(
            request_id,
            started,
            200,
            "audit",
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
            "audit",
            operation,
            action,
            payload=_public_principal(principal),
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=evaluation.decision,
        )


def control_router(service: ControlService) -> APIRouter:
    """Typed control-plane router: 3 of 8 routes (principals create/list/get).

    Remaining routes (status replace + credentials issue/list/revoke/rotate)
    ship in follow-up slices with #147 open; see openspec apply-progress.
    """
    router = APIRouter()
    bearer_scheme = HTTPBearer(auto_error=False, description="Administrative bearer credential")
    bearer_credentials: Any = Security(bearer_scheme)
    idempotency_header = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[\x20-\x7E]{16,128}$",
        description="Scoped idempotency key (mutating POST only)",
    )

    @router.post(
        "/v1/principals",
        status_code=201,
        responses={
            201: {"description": "Principal created", "content": {"application/json": {}}},
            401: {"description": "Authentication failed"},
            403: {"description": "Resource unavailable"},
            409: {"description": "Idempotency conflict"},
            422: {"description": "Validation error"},
        },
    )
    async def create_principal(
        body: PrincipalCreate,
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
        idempotency_key: str | None = idempotency_header,
    ) -> Response:
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        result = await service.create_principal(
            body.model_dump(mode="json"),
            authorization or request.headers.get("authorization"),
            idempotency_key or request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get("/v1/principals")
    async def list_principals(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
        limit: int = Query(default=100, ge=1, le=100),
    ) -> Response:
        try:
            ListPrincipalsQuery.model_validate({"limit": limit, **dict(request.query_params)})
        except ValidationError:
            pass
        params = {k: v for k, v in request.query_params.items() if k != "limit"}
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        result = await service.list_principals(
            authorization or request.headers.get("authorization"), limit, params
        )
        response.status_code = result.status_code
        return result

    @router.get("/v1/principals/{principal_id}")
    async def get_principal(
        principal_id: Annotated[str, Path(pattern=r"^[a-z][a-z0-9_-]{2,63}$")],
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

    return router
