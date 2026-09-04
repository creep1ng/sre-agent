# ruff: noqa: E501, I001

import hashlib
import json
from time import monotonic
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import Principal
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository, IdempotencyConflictError, IdempotencyOutcome, IdempotencyRepository, PrincipalRepository, ResourceRepository  # fmt: skip

IDEMPOTENCY_KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
ERRORS = {
    400: ("invalid_idempotency_key", "The Idempotency-Key header is missing or invalid."),
    401: ("authentication_failed", "Authentication failed."),
    403: ("resource_unavailable", "Resource unavailable."),
    404: ("resource_not_found", "The requested resource was not found."),
    409: ("idempotency_conflict", "The Idempotency-Key was already used with another payload."),
    422: ("validation_error", "The request is invalid."),
    503: ("audit_unavailable", "Audit unavailable."),
}


class PrincipalCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    principal_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")]
    kind: Annotated[str, Field(pattern=r"^(human|agent)$")]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]


class StatusReplace(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    status: Annotated[str, Field(pattern=r"^(active|inactive)$")]
    expected_updated_at: Annotated[str, Field(min_length=1, max_length=64)]


class CredentialIssueBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    expires_at: Annotated[str, Field(min_length=1, max_length=64)] | None = None


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
        import re

        return value is None or re.match(IDEMPOTENCY_KEY_PATTERN, value) is None

    async def _authenticate(self, authorization: str | None):
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
        request_id,
        started,
        status,
        stage,
        operation,
        action,
        *,
        payload=None,
        error_code=None,
        context=None,
        resource_ref=None,
        decision=None,
        authorization_denial_cause=None,
    ) -> JSONResponse:
        event = self.projector.control_event(
            request_id,
            status,
            max(0, int((monotonic() - started) * 1000)),
            stage,
            operation=operation,
            action=action,
            context=context,
            resource_ref=resource_ref,
            decision=decision,
            authorization_denial_cause=authorization_denial_cause,
        )
        try:
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
        import re

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
    router = APIRouter()

    @router.post("/v1/principals")
    async def create_principal(request: Request) -> JSONResponse:
        return await service.create_principal(
            await request.json(),
            request.headers.get("authorization"),
            request.headers.get("idempotency-key"),
        )

    @router.get("/v1/principals")
    async def list_principals(request: Request) -> JSONResponse:
        params = dict(request.query_params)
        raw_limit = params.pop("limit", "100")
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 0
        return await service.list_principals(request.headers.get("authorization"), limit, params)

    @router.get("/v1/principals/{principal_id}")
    async def get_principal(principal_id: str, request: Request) -> JSONResponse:
        return await service.get_principal(principal_id, request.headers.get("authorization"))

    return router
