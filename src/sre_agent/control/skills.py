"""Skills: published, versioned instructions an agent may load once a version is active."""

import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.json_schema import WithJsonSchema
from sqlalchemy.exc import IntegrityError

from sre_agent.control.governed import (
    IDEMPOTENCY_CONFLICT,
    INVALID,
    NOT_FOUND,
    STATUS_CONFLICT,
    ControlAudit,
    ControlGate,
    Record,
    canonical_payload,
    idempotency_key,
    key_digest,
    payload_sha256,
)
from sre_agent.control.operations import CONTROL
from sre_agent.control.routing import (
    authorization_from,
    bearer_credentials,
    errors,
    idempotency_key_parameter,
    raw_json,
    request_body,
)
from sre_agent.gate.pipeline import Admission, Released
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import PrincipalContext, SkillManifest, SkillVersionRecord
from sre_agent.persistence.repositories import (
    CatalogRepository,
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
    SkillVersionConflictError,
    SkillVersionRepository,
)
from sre_agent.vocabulary import Identifier

PUBLISH = CONTROL[("POST", "/v1/skills/versions")]
READ = CONTROL[("GET", "/v1/skills/{skill_id}/{version}")]
SKILL_ID = r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$"
SEMVER = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"


class SkillPublishRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    skill_id: Annotated[str, Field(pattern=SKILL_ID)]
    version: Annotated[str, Field(max_length=32, pattern=SEMVER)]
    owner_id: Identifier
    manifest: SkillManifest

    @model_validator(mode="after")
    def publication_fits_json_bound(self) -> "SkillPublishRequest":
        content = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        if len(content.encode("utf-8")) > 32_768:
            raise ValueError("Skill publication exceeds the encoded byte limit")
        return self


class Skills:
    """Publish skill versions and read them."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def publish(
        self, caller: PrincipalContext, body: SkillPublishRequest, key: str, record: Record
    ) -> dict[str, Any]:
        """The published version, or the one a replay of the same key and payload published;
        either answer is audited in the transaction."""
        path = PUBLISH.path
        scope = f"{caller.principal.principal_id}|POST|{path}"
        payload_hash = payload_sha256(body.model_dump(mode="json"))
        try:
            async with self.sessions() as session, session.begin():
                idempotency = IdempotencyRepository(session)
                binding = await idempotency.claim_or_replay(
                    scope=scope,
                    key_digest=key_digest(key),
                    payload_sha256=payload_hash,
                    principal_id=caller.principal.principal_id,
                    method="POST",
                    canonical_path=path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=201,
                        resource_id=f"{body.skill_id}@{body.version}",
                        replayed=False,
                    ),
                )
                if binding.replayed:
                    # The stored payload is JSON (ISO timestamps); strict python-mode validation
                    # rejected it, so a same-key retry failed instead of replaying.
                    stored = canonical_payload(binding.outcome.response_payload)
                    published = SkillVersionRecord.model_validate_json(stored)
                else:
                    published = await SkillVersionRepository(session).publish(
                        skill_id=body.skill_id,
                        version=body.version,
                        owner_id=body.owner_id,
                        manifest=body.manifest,
                        content_sha256=payload_hash,
                    )
                    await idempotency.set_response_payload(
                        scope=scope,
                        key_digest=key_digest(key),
                        response_payload=published.model_dump(mode="json"),
                    )
                await record(session, 201)
        except IdempotencyConflictError:
            raise IDEMPOTENCY_CONFLICT from None
        except (SkillVersionConflictError, IntegrityError):
            raise STATUS_CONFLICT from None
        return published.model_dump(mode="json")

    async def read(self, skill_id: str, version: str) -> dict[str, Any]:
        """A published version whose catalog entry is not inactive."""
        async with self.sessions() as session:
            published = await SkillVersionRepository(session).get(skill_id, version)
            catalog = await CatalogRepository(session).get("skill", f"{skill_id}@{version}")
        if published is None or catalog is None or catalog.status == "inactive":
            raise NOT_FOUND
        return published.model_dump(mode="json")


def _version(skill_id: str, version: str) -> None:
    if (
        re.fullmatch(SKILL_ID[1:-1], skill_id) is None
        or len(version) > 32
        or re.fullmatch(SEMVER[1:-1], version) is None
    ):
        raise INVALID


class SkillRoutes:
    """The skill routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.skills = Skills(sessions)
        control = ControlAudit(audit, projector)

        def gate(operation: Any) -> ControlGate[Any]:
            return ControlGate(sessions, control, operation, reason="grant_matched")

        self.publishing, self.reading = gate(PUBLISH), gate(READ)

    async def publish_skill_version(
        self, raw: Any, authorization: str | None, key: str | None
    ) -> Response:
        def validate() -> tuple[SkillPublishRequest, str]:
            valid_key = idempotency_key(key)
            try:
                return SkillPublishRequest.model_validate(raw), valid_key
            except ValidationError:
                raise INVALID from None

        async def publish(
            admission: Admission, request: tuple[SkillPublishRequest, str]
        ) -> Released:
            record = self.publishing.record(admission)
            return Released(await self.skills.publish(admission.context, *request, record), 201)

        return await self.publishing.run(authorization, publish, validate)

    async def get_skill_version(
        self, skill_id: str, version: str, authorization: str | None
    ) -> Response:
        async def read(_admission: Admission, _request: None) -> Released:
            return Released(await self.skills.read(skill_id, version))

        return await self.reading.run(authorization, read, lambda: _version(skill_id, version))


SkillId = Annotated[str, WithJsonSchema({"type": "string", "pattern": SKILL_ID})]
Version = Annotated[str, WithJsonSchema({"type": "string", "pattern": SEMVER, "maxLength": 32})]


def skills_router(routes: SkillRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

    @router.post(
        PUBLISH.route,
        status_code=201,
        response_model=SkillVersionRecord,
        responses=errors(400, 401, 403, 409, 422, 503),
        openapi_extra={
            "parameters": [idempotency_key_parameter()],
            **request_body(SkillPublishRequest),
            **PUBLISH.openapi_extra,
        },
    )
    async def publish_skill_version(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.publish_skill_version(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )

    @router.get(
        READ.route,
        response_model=SkillVersionRecord,
        responses=errors(401, 403, 404, 422, 503),
        openapi_extra=READ.openapi_extra,
    )
    async def get_skill_version(
        skill_id: SkillId,
        version: Version,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.get_skill_version(
            skill_id, version, authorization_from(credentials, request)
        )

    return router
