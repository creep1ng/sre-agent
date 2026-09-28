"""Protected read-only access to the single-workspace consumption policy."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Response, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.persistence.models import ConsumptionLimitPolicyRow


class ConsumptionLimitPolicyResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int
    incident_token_limit: int | None
    monthly_usd_limit: str | None
    updated_at: datetime


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
        action, resource_type, resource_id = CONTROL_SCOPES[
            ("GET", "/v1/consumption-limits")
        ]
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

        monthly_limit = None
        if policy.monthly_usd_limit is not None:
            monthly_limit = format(policy.monthly_usd_limit, "f")
            if "." in monthly_limit:
                monthly_limit = monthly_limit.rstrip("0").rstrip(".")
        return JSONResponse(
            {
                "version": policy.version,
                "incident_token_limit": policy.incident_token_limit,
                "monthly_usd_limit": monthly_limit,
                "updated_at": policy.updated_at.isoformat(),
            }
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
        authorization = (
            f"{credentials.scheme} {credentials.credentials}" if credentials else None
        )
        return await service.get_policy(authorization)

    return router
