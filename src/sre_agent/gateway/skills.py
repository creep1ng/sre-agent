"""Grant-governed access to exact-version instruction-only Skills."""

from time import monotonic
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Path, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.gateway.responses import AuditStore
from sre_agent.governance.dto import SkillVersionRecord
from sre_agent.persistence.repositories import SkillVersionRepository

_SKILL_ID_PATTERN = r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$"
_VERSION_PATTERN = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
_UNAVAILABLE = {
    "error": {"code": "resource_not_found", "message": "The requested resource was not found."}
}


class SkillResolutionResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    skill: SkillVersionRecord
    request_id: UUID
    retryable: bool


class SkillResolutionService:
    def __init__(self, sessions: Any, audit: AuditStore, projector: AuditProjector) -> None:
        self.sessions, self.audit, self.projector = sessions, audit, projector

    async def resolve(
        self, skill_id: str, version: str, authorization: str | None, request_id: UUID
    ) -> JSONResponse:
        started = monotonic()
        resource_id = f"{skill_id}@{version}"
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, "invoke", "skill", resource_id
            )
        except AuthenticationFailed:
            return await self._finish(
                request_id,
                started,
                401,
                {"error": {"code": "authentication_failed", "message": "Authentication failed."}},
                error_code="authentication_failed",
            )
        if evaluation.decision.decision != "allow":
            return await self._finish(
                request_id,
                started,
                404,
                _UNAVAILABLE,
                context=context,
                evaluation=evaluation,
                resource_ref=("skill", resource_id),
                error_code="resource_not_found",
            )

        async with self.sessions() as session:
            skill = await SkillVersionRepository(session).get(skill_id, version)
        if skill is None or skill.manifest.dependencies:
            return await self._finish(
                request_id,
                started,
                404,
                _UNAVAILABLE,
                context=context,
                evaluation=evaluation,
                resource_ref=("skill", resource_id),
                error_code="resource_not_found",
            )
        return await self._finish(
            request_id,
            started,
            200,
            SkillResolutionResponse(skill=skill, request_id=request_id, retryable=False).model_dump(
                mode="json"
            ),
            context=context,
            evaluation=evaluation,
            resource_ref=("skill", resource_id),
            error_code="grant_matched",
        )

    async def _finish(
        self,
        request_id: UUID,
        started: float,
        status: int,
        payload: dict[str, Any],
        *,
        context: Any = None,
        evaluation: Any = None,
        resource_ref: tuple[str, str] | None = None,
        error_code: str | None = None,
    ) -> JSONResponse:
        try:
            stage = (
                "authorization"
                if context is not None and evaluation is not None
                else ("authentication" if status == 401 else "audit")
            )
            event = self.projector.control_event(
                request_id,
                status,
                max(0, int((monotonic() - started) * 1000)),
                stage,
                operation="skills.resolve",
                action="invoke",
                reason=error_code,
                context=context if stage == "authorization" else None,
                resource_ref=resource_ref if stage == "authorization" else None,
                decision=evaluation.decision if stage == "authorization" else None,
                authorization_denial_cause=(
                    evaluation.denial_cause if stage == "authorization" else None
                ),
            )
            await self.audit.append(event)
        except Exception:
            return JSONResponse(
                {
                    "error": {"code": "audit_unavailable", "message": "Audit unavailable."},
                    "request_id": str(request_id),
                    "retryable": True,
                },
                status_code=503,
            )
        return JSONResponse(
            {**payload, "request_id": str(request_id), "retryable": False},
            status_code=status,
            headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
        )


def skill_resolution_router(service: SkillResolutionService) -> APIRouter:
    router = APIRouter()
    bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")

    @router.get(
        "/v1/skills/{skill_id}/{version}/resolve",
        response_model=SkillResolutionResponse,
        responses={
            401: {"description": "Authentication failed."},
            404: {"description": "Skill unavailable."},
        },
        summary="Resolve one exact Skill version",
        operation_id="resolveSkillVersion",
        description=(
            "Requires an active direct `invoke` grant for the exact version. Authorization is "
            "checked before its instructions are read; unavailable versions share one response."
        ),
        openapi_extra={
            "x-governed-scope": {
                "action": "invoke",
                "resource_type": "skill",
                "resource_id": "path.skill_id@path.version",
            }
        },
    )
    async def resolve_skill(
        request: Request,
        skill_id: Annotated[str, Path(pattern=_SKILL_ID_PATTERN)],
        version: Annotated[str, Path(pattern=_VERSION_PATTERN)],
        _bearer: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(bearer),
        ] = None,
    ) -> JSONResponse:
        try:
            request_id = UUID(request.headers.get("X-Request-ID", ""))
        except ValueError:
            request_id = uuid4()
        authorization = request.headers.get("Authorization")
        return await service.resolve(skill_id, version, authorization, request_id)

    return router
