"""Grant-governed access to exact-version instruction-only Skills."""

import re
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Path, Request, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from sre_agent.gate.errors import ErrorEnvelope, GovernedError
from sre_agent.gate.pipeline import Admission, Gate, Refusals, Released, Scope, Terminal, declare
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import AuditStore
from sre_agent.governance.dto import SkillVersionRecord
from sre_agent.persistence.repositories import SkillVersionRepository

_SKILL_ID_PATTERN = r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$"
_VERSION_PATTERN = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
# An unavailable version, an ungranted one and a missing dependency share one answer.
UNAVAILABLE = GovernedError(404, "resource_not_found", "The requested resource was not found.")
INVALID = GovernedError(422, "contract_validation_failed", "Request validation failed.")
REFUSALS = Refusals(
    denied=UNAVAILABLE,
    unavailable=GovernedError(503, "audit_unavailable", "Audit unavailable.", retryable=True),
)


class SkillResolutionResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    skill: SkillVersionRecord
    dependencies: list[SkillVersionRecord]
    request_id: UUID
    retryable: Literal[False]


class SkillResolutionService:
    def __init__(self, sessions: Any, audit: AuditStore, projector: AuditProjector) -> None:
        self.sessions, self.audit, self.projector = sessions, audit, projector
        self.gate: Gate[str] = Gate(sessions, REFUSALS, audit=self._audit)

    async def resolve(
        self, skill_id: str, version: str, authorization: str | None, request_id: UUID
    ) -> Response:
        def validate() -> str:
            if (
                re.fullmatch(_SKILL_ID_PATTERN, skill_id) is None
                or len(version) > 32
                or re.fullmatch(_VERSION_PATTERN, version) is None
            ):
                raise INVALID
            return f"{skill_id}@{version}"

        async def resolve(admission: Admission, resource_id: str) -> Released:
            async with self.sessions() as session:
                skill = await SkillVersionRepository(session).get(skill_id, version)
            if skill is None:
                raise UNAVAILABLE
            authorized: list[tuple[str, Any]] = []
            for dependency in skill.manifest.dependencies:
                dependency_id = f"{dependency.skill_id}@{dependency.version}"
                evaluation = await self.gate.authorize(
                    admission.context, Scope("invoke", "skill", dependency_id)
                )
                if evaluation.decision.decision != "allow":
                    admission.facts.update(evaluation=evaluation, resource_id=dependency_id)
                    raise UNAVAILABLE
                authorized.append((dependency_id, evaluation))
            resolved: list[SkillVersionRecord] = []
            async with self.sessions() as session:
                repository = SkillVersionRepository(session)
                for dependency, (dependency_id, evaluation) in zip(
                    skill.manifest.dependencies, authorized, strict=True
                ):
                    found = await repository.get(dependency.skill_id, dependency.version)
                    if found is None or found.manifest.dependencies:
                        admission.facts.update(evaluation=evaluation, resource_id=dependency_id)
                        raise UNAVAILABLE
                    resolved.append(found)
            return Released(
                SkillResolutionResponse(
                    skill=skill,
                    dependencies=resolved,
                    request_id=admission.request_id,
                    retryable=False,
                ).model_dump(mode="json")
            )

        return await self.gate.run(
            authorization,
            lambda resource_id: Scope("invoke", "skill", resource_id),
            resolve,
            validate=validate,
            request_id=request_id,
        )

    async def _audit(self, terminal: Terminal) -> None:
        evaluation = terminal.facts.get("evaluation", terminal.evaluation)
        # Subject evidence only once a principal was evaluated; a storage failure has none.
        subject = terminal.context is not None and evaluation is not None
        if terminal.error is REFUSALS.unavailable:
            subject = False
        stage = (
            "authorization"
            if subject
            else {422: "validation", 401: "authentication"}.get(terminal.status, "audit")
        )
        resource_id = terminal.facts.get("resource_id", terminal.request)
        event = self.projector.control_event(
            terminal.request_id,
            terminal.status,
            terminal.latency_ms,
            stage,
            operation="skills.resolve",
            action="invoke",
            reason=terminal.error.code if terminal.error is not None else "grant_matched",
            retryable=terminal.status == 503,
            context=terminal.context if subject else None,
            resource_ref=("skill", resource_id) if subject else None,
            decision=evaluation.decision if subject else None,
            authorization_denial_cause=evaluation.denial_cause if subject else None,
        )
        await self.audit.append(event)


RESOLVE = declare(
    "GET",
    "/v1/skills/{skill_id}/{version}/resolve",
    action="invoke",
    resource_type="skill",
    resource_id="path.skill_id@path.version",
)


def skill_resolution_router(service: SkillResolutionService) -> APIRouter:
    router = APIRouter()
    bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")

    @router.get(
        RESOLVE.path,
        response_model=SkillResolutionResponse,
        responses={
            401: {
                "model": ErrorEnvelope,
                "description": "Authentication failed.",
                "headers": {
                    "WWW-Authenticate": {
                        "description": "Bearer authentication challenge.",
                        "schema": {"type": "string"},
                        "example": "Bearer",
                    }
                },
            },
            404: {"model": ErrorEnvelope, "description": "Skill unavailable."},
            422: {"model": ErrorEnvelope, "description": "Invalid skill path parameters."},
            503: {"model": ErrorEnvelope, "description": "Audit unavailable."},
        },
        summary="Resolve one exact Skill version",
        operation_id="resolveSkillVersion",
        description=(
            "Requires active direct `invoke` grants for the root and each pinned dependency. "
            "Every grant is checked before content is read; unavailable versions share one "
            "response. Nested dependencies are unsupported."
        ),
        openapi_extra=RESOLVE.openapi_extra,
    )
    async def resolve_skill(
        request: Request,
        skill_id: Annotated[str, Path(json_schema_extra={"pattern": _SKILL_ID_PATTERN})],
        version: Annotated[str, Path(json_schema_extra={"pattern": _VERSION_PATTERN})],
        _bearer: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(bearer),
        ] = None,
    ) -> Response:
        try:
            request_id = UUID(request.headers.get("X-Request-ID", ""))
        except ValueError:
            request_id = uuid4()
        authorization = request.headers.get("Authorization")
        return await service.resolve(skill_id, version, authorization, request_id)

    return router
