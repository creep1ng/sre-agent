"""Protected read and versioned writes for the single-workspace consumption policy."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from sre_agent.control.governed import (
    IDEMPOTENCY_CONFLICT,
    INVALID,
    REFUSALS,
    STATUS_CONFLICT,
    ControlAudit,
    ControlGate,
    Record,
    idempotency_key,
    key_digest,
    payload_sha256,
)
from sre_agent.control.operations import CONTROL
from sre_agent.gate.errors import AuthenticationFailed, GovernedError
from sre_agent.gate.pipeline import Admission, Released
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.models import ConsumptionLimitPolicyRow
from sre_agent.persistence.repositories import (
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
)

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


POLICY_UNAVAILABLE = GovernedError(
    503,
    "policy_unavailable",
    "The consumption policy is unavailable.",
    retryable=True,
    stage="audit",
)
# The policy routes challenge an unauthenticated caller, unlike the other control routes.
CHALLENGED = replace(REFUSALS, unauthenticated=AuthenticationFailed())
PATH = "/v1/consumption-limits"


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


class ConsumptionLimits:
    """The workspace's consumption policy: one row, replaced by compare-and-set on its version."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def read(self) -> dict[str, Any]:
        async with self.sessions() as session:
            policy = await session.get(ConsumptionLimitPolicyRow, 1)
        if policy is None:
            raise POLICY_UNAVAILABLE
        return _policy_response(policy)

    async def replace(
        self,
        caller: PrincipalContext,
        body: ConsumptionLimitPolicyUpdate,
        key: str,
        record: Record,
    ) -> tuple[dict[str, Any], int]:
        """Replace the policy, or replay the answer of the same key and payload; the audit is
        written in the same transaction."""
        binding_scope = f"{caller.principal.principal_id}|PUT|{PATH}"
        try:
            async with self.sessions() as session, session.begin():
                repository = IdempotencyRepository(session)
                binding = await repository.claim_or_replay(
                    scope=binding_scope,
                    key_digest=key_digest(key),
                    payload_sha256=payload_sha256(body.model_dump(mode="json")),
                    principal_id=caller.principal.principal_id,
                    method="PUT",
                    canonical_path=PATH,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=200, resource_id="workspace", replayed=False
                    ),
                )
                if binding.replayed:
                    payload = binding.outcome.response_payload
                else:
                    payload = _policy_response(await self._compare_and_set(session, body))
                    await repository.set_response_payload(
                        scope=binding_scope, key_digest=key_digest(key), response_payload=payload
                    )
                await record(session, binding.outcome.response_status)
        except IdempotencyConflictError:
            raise IDEMPOTENCY_CONFLICT from None
        return payload, binding.outcome.response_status

    async def _compare_and_set(
        self, session: Any, body: ConsumptionLimitPolicyUpdate
    ) -> ConsumptionLimitPolicyRow:
        policy = await session.scalar(
            select(ConsumptionLimitPolicyRow)
            .where(ConsumptionLimitPolicyRow.policy_id == 1)
            .with_for_update()
        )
        if policy is None:
            raise POLICY_UNAVAILABLE
        if body.expected_version != policy.version or policy.version == MAX_SIGNED_BIGINT:
            raise STATUS_CONFLICT
        policy.version += 1
        policy.incident_token_limit = body.incident_token_limit
        policy.monthly_usd_limit = (
            Decimal(body.monthly_usd_limit) if body.monthly_usd_limit is not None else None
        )
        policy.updated_at = datetime.now(UTC)
        await session.flush()
        return policy


class ConsumptionLimitRoutes:
    """The policy routes on the gate."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.limits = ConsumptionLimits(sessions)
        control = ControlAudit(audit, projector)
        self.reading: ControlGate[None] = ControlGate(
            sessions, control, CONTROL[("GET", PATH)], refusals=CHALLENGED
        )
        self.replacing: ControlGate[tuple[ConsumptionLimitPolicyUpdate, str]] = ControlGate(
            sessions, control, CONTROL[("PUT", PATH)], refusals=CHALLENGED
        )

    async def get_policy(self, authorization: str | None) -> Response:
        async def read(_admission: Admission, _request: None) -> Released:
            return Released(await self.limits.read())

        return await self.reading.run(authorization, read)

    async def replace_policy(
        self, raw: Any, authorization: str | None, key: str | None
    ) -> Response:
        def validate() -> tuple[ConsumptionLimitPolicyUpdate, str]:
            valid_key = idempotency_key(key)
            try:
                return ConsumptionLimitPolicyUpdate.model_validate(raw), valid_key
            except (TypeError, ValidationError):
                raise INVALID from None

        async def replace(
            admission: Admission, request: tuple[ConsumptionLimitPolicyUpdate, str]
        ) -> Released:
            body, valid_key = request
            payload, status = await self.limits.replace(
                admission.context, body, valid_key, self.replacing.record(admission)
            )
            return Released(payload, status)

        return await self.replacing.run(authorization, replace, validate)


def consumption_limits_router(service: ConsumptionLimitRoutes) -> APIRouter:
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
        openapi_extra=CONTROL[("GET", "/v1/consumption-limits")].openapi_extra,
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
        openapi_extra=CONTROL[("PUT", "/v1/consumption-limits")].openapi_extra,
    )
    async def put_consumption_limits(
        raw: Annotated[Any, Body()],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
        return await service.replace_policy(raw, authorization, idempotency_key)

    return router
