"""Protected read and versioned writes for the single-workspace consumption policy."""

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Body, Header, Response, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.persistence.models import ConsumptionLimitPolicyRow
from sre_agent.persistence.repositories import (
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
)

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[\x20-\x7E]{16,128}$")
MONTHLY_USD_PATTERN = r"^(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,12})?$"
MAX_SIGNED_BIGINT = 9_223_372_036_854_775_807


class ConsumptionLimitPolicyResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int
    incident_token_limit: int | None
    monthly_usd_limit: str | None
    updated_at: datetime


class ConsumptionLimitPolicyUpdate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    expected_version: Annotated[int, Field(ge=0, le=MAX_SIGNED_BIGINT)]
    incident_token_limit: Annotated[int, Field(ge=0, le=MAX_SIGNED_BIGINT)] | None
    monthly_usd_limit: Annotated[str, Field(pattern=MONTHLY_USD_PATTERN)] | None


class StalePolicyVersion(RuntimeError):
    """The compare-and-set version was not current when the policy row was locked."""


class PolicyUnavailable(RuntimeError):
    """The singleton policy row is missing or cannot be updated."""


def _canonical_payload(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_payload(payload).encode()).hexdigest()


def _key_digest(key: str) -> str:
    return hashlib.sha256(f"sre-idempotency-v1\0{key}".encode()).hexdigest()


def _policy_response(policy: ConsumptionLimitPolicyRow) -> dict[str, Any]:
    monthly_limit = None
    if policy.monthly_usd_limit is not None:
        monthly_limit = format(policy.monthly_usd_limit, "f")
        if "." in monthly_limit:
            monthly_limit = monthly_limit.rstrip("0").rstrip(".")
    return {
        "version": policy.version,
        "incident_token_limit": policy.incident_token_limit,
        "monthly_usd_limit": monthly_limit,
        "updated_at": policy.updated_at.isoformat(),
    }


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message},
            "request_id": str(uuid4()),
            "retryable": False,
        },
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


class ConsumptionLimitPolicyService:
    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def get_policy(self, authorization: str | None) -> Response:
        action, resource_type, resource_id = CONTROL_SCOPES[("GET", "/v1/consumption-limits")]
        try:
            _, evaluation = await authorize_governed_access(
                self.sessions, authorization, action, resource_type, resource_id
            )
        except AuthenticationFailed:
            return _error(401, "authentication_failed", "Authentication failed.")
        if evaluation.decision.decision == "deny":
            return _error(403, "resource_unavailable", "Resource unavailable.")

        async with self.sessions() as session:
            policy = await session.get(ConsumptionLimitPolicyRow, 1)
        if policy is None:
            return _error(503, "policy_unavailable", "The consumption policy is unavailable.")

        return JSONResponse(_policy_response(policy))

    async def replace_policy(
        self,
        raw: Any,
        authorization: str | None,
        idempotency_key: str | None,
    ) -> Response:
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions,
                authorization,
                *CONTROL_SCOPES[("PUT", "/v1/consumption-limits")],
            )
        except AuthenticationFailed:
            return _error(401, "authentication_failed", "Authentication failed.")
        if evaluation.decision.decision == "deny":
            return _error(403, "resource_unavailable", "Resource unavailable.")
        if idempotency_key is None or IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key) is None:
            return _error(
                400,
                "invalid_idempotency_key",
                "The Idempotency-Key header is missing or invalid.",
            )
        try:
            body = ConsumptionLimitPolicyUpdate.model_validate(raw)
        except (TypeError, ValidationError):
            return _error(422, "validation_error", "The request is invalid.")

        path = "/v1/consumption-limits"
        binding_scope = f"{context.principal.principal_id}|PUT|{path}"
        key_digest = _key_digest(idempotency_key)
        payload_sha256 = _payload_sha256(body.model_dump(mode="json"))
        try:
            async with self.sessions() as session, session.begin():
                repository = IdempotencyRepository(session)
                binding = await repository.claim_or_replay(
                    scope=binding_scope,
                    key_digest=key_digest,
                    payload_sha256=payload_sha256,
                    principal_id=context.principal.principal_id,
                    method="PUT",
                    canonical_path=path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=200,
                        resource_id="workspace",
                        replayed=False,
                    ),
                )
                if binding.replayed:
                    return JSONResponse(
                        binding.outcome.response_payload,
                        status_code=binding.outcome.response_status,
                    )

                policy = await session.scalar(
                    select(ConsumptionLimitPolicyRow)
                    .where(ConsumptionLimitPolicyRow.policy_id == 1)
                    .with_for_update()
                )
                if policy is None:
                    raise PolicyUnavailable
                if body.expected_version != policy.version or policy.version == MAX_SIGNED_BIGINT:
                    raise StalePolicyVersion

                policy.version += 1
                policy.incident_token_limit = body.incident_token_limit
                policy.monthly_usd_limit = (
                    Decimal(body.monthly_usd_limit) if body.monthly_usd_limit is not None else None
                )
                policy.updated_at = datetime.now(UTC)
                await session.flush()
                response_payload = _policy_response(policy)
                await repository.set_response_payload(
                    scope=binding_scope,
                    key_digest=key_digest,
                    response_payload=response_payload,
                )
                return JSONResponse(response_payload, status_code=200)
        except IdempotencyConflictError:
            return _error(
                409,
                "idempotency_conflict",
                "The Idempotency-Key was already used with another payload.",
            )
        except StalePolicyVersion:
            return _error(409, "status_conflict", "The policy version is stale.")
        except PolicyUnavailable:
            return _error(503, "policy_unavailable", "The consumption policy is unavailable.")


def consumption_limits_router(service: ConsumptionLimitPolicyService) -> APIRouter:
    router = APIRouter()
    bearer = HTTPBearer(auto_error=False, description="Administrative bearer credential")
    bearer_credentials: Any = Security(bearer)

    @router.get(
        "/v1/consumption-limits",
        response_model=ConsumptionLimitPolicyResponse,
        responses={
            401: {"description": "Authentication failed"},
            403: {"description": "Resource unavailable"},
            503: {"description": "Policy unavailable"},
        },
        openapi_extra={
            "x-governed-scope": {
                "action": "admin.read",
                "resource_type": "administrative_control",
                "resource_id": "consumption_limits",
            }
        },
    )
    async def get_consumption_limits(
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        return await service.get_policy(authorization)

    @router.put(
        "/v1/consumption-limits",
        response_model=ConsumptionLimitPolicyResponse,
        responses={
            400: {"description": "Invalid idempotency key"},
            401: {"description": "Authentication failed"},
            403: {"description": "Resource unavailable"},
            409: {"description": "Idempotency or version conflict"},
            422: {"description": "Invalid policy"},
            503: {"description": "Policy unavailable"},
        },
        openapi_extra={
            "x-governed-scope": {
                "action": "admin.write",
                "resource_type": "administrative_control",
                "resource_id": "consumption_limits",
            }
        },
    )
    async def put_consumption_limits(
        raw: Annotated[Any, Body()],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        return await service.replace_policy(raw, authorization, idempotency_key)

    return router
