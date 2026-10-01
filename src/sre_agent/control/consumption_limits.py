"""Protected read-only access to the single-workspace consumption policy."""

from datetime import datetime
from functools import partial
from time import monotonic
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.control.service import ControlService
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.persistence.models import ConsumptionLimitPolicyRow


class ConsumptionLimitPolicyResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int
    incident_token_limit: int | None
    monthly_usd_limit: str | None
    updated_at: datetime


class ConsumptionLimitPolicyService(ControlService):
    async def get_policy(self, authorization: str | None) -> Response:
        action, resource_type, resource_id = CONTROL_SCOPES[("GET", "/v1/consumption-limits")]
        finish = partial(
            self._finish, uuid4(), monotonic(), operation="consumption_limits.get", action=action
        )
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, action, resource_type, resource_id
            )
        except AuthenticationFailed:
            response = await finish(401, "authentication", error_code="authentication_failed")
            if response.status_code == 401:
                response.headers["WWW-Authenticate"] = "Bearer"
            return response
        finish = partial(
            finish,
            context=context,
            resource_ref=(resource_type, resource_id),
            decision=evaluation.decision,
            authorization_denial_cause=evaluation.denial_cause,
        )
        if evaluation.decision.decision == "deny":
            return await finish(403, "authorization", error_code="resource_unavailable")

        async with self.sessions() as session:
            policy = await session.get(ConsumptionLimitPolicyRow, 1)
        if policy is None:
            return await finish(503, "audit", error_code="policy_unavailable")

        monthly_limit = None
        if policy.monthly_usd_limit is not None:
            monthly_limit = format(policy.monthly_usd_limit, "f")
            if "." in monthly_limit:
                monthly_limit = monthly_limit.rstrip("0").rstrip(".")
        return await finish(
            200,
            "authorization",
            payload={
                "version": policy.version,
                "incident_token_limit": policy.incident_token_limit,
                "monthly_usd_limit": monthly_limit,
                "updated_at": policy.updated_at.isoformat(),
            },
        )


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

    return router
