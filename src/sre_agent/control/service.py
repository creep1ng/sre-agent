# ruff: noqa: E501, I001

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
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.json_schema import WithJsonSchema
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.bok.owner import BoKVersionCollision
from sre_agent.bok.publication import BOK_SLUG_PATTERN, SEMVER_PATTERN, BoKAuthorRefused, BoKPublishRequest, BoKVersionRecord, BoKVersionSummary, publish_bok_version, read_bok_version  # fmt: skip
from sre_agent.control.governed import IDEMPOTENCY_KEY_PATTERN
from sre_agent.control.governed import canonical_payload as _canonical_payload
from sre_agent.control.governed import key_digest as _key_digest
from sre_agent.control.governed import payload_sha256 as _payload_sha256
from sre_agent.control.operations import CONTROL, CONTROL_SCOPES
from sre_agent.gate.authentication import bearer_key
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import (
    Principal,
    PrincipalContext,
    ResourceCatalogEntry,
    SkillManifest,
    SkillVersionRecord,
)
from sre_agent.persistence.repositories import CatalogRepository, CredentialRepository, GrantRepository, IdempotencyConflictError, IdempotencyOutcome, IdempotencyRepository, ResourceRepository, SkillVersionConflictError, SkillVersionRepository, StaleWriteError  # fmt: skip
from sre_agent.vocabulary import Identifier

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
    "policy_unavailable": "The consumption policy is unavailable.",
    "status_conflict": "The status was changed by another request.",
    "grant_conflict": "An active grant with this principal, action and resource already exists.",
    "grant_id_conflict": "A grant with this grant_id already exists, active or revoked.",
    "credential_inactive": "The credential is not active.",
    "credential_issuance_failed": "Credential issuance could not be completed.",
}


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


class CatalogDiscoverabilityCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    visibility: Literal["public", "private", "hidden"]
    description: Annotated[str, Field(max_length=500)]
    tags: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9._-]*$")]],
        Field(max_length=16),
    ]


class CatalogCreate(BaseModel):
    """Closed ADMIN-authoritative create for non-llm catalog resources.

    llm_model stays owned by ModelAliasCreate; this body rejects it so
    routing authority never duplicates. Source must match the type and
    status must be permitted for the type; secrets and routing fields are
    rejected by the closed body.
    """

    model_config = ConfigDict(strict=True, extra="forbid")
    resource_type: Literal[
        "mcp_server",
        "mcp_tool",
        "skill",
        "bok_collection",
        "incident_workflow",
        "service_operation",
    ]
    resource_id: Annotated[
        str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")
    ]
    owner_id: Identifier
    source: Literal["mcp", "skill", "bok", "incident_workflow", "deploy_executor"]
    source_ref: Annotated[
        str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")
    ]
    status: Literal["registered", "draft", "published", "indexing", "active", "inactive", "revoked"]
    discoverability: CatalogDiscoverabilityCreate


class SkillPublishRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    skill_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$")]
    version: Annotated[
        str,
        Field(max_length=32, pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"),
    ]
    owner_id: Identifier
    manifest: SkillManifest

    @model_validator(mode="after")
    def publication_fits_json_bound(self) -> "SkillPublishRequest":
        content = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        if len(content.encode("utf-8")) > 32_768:
            raise ValueError("Skill publication exceeds the encoded byte limit")
        return self


class SkillStatusRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    status: Literal["active", "inactive"]


class SkillStatusResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    resource_type: Literal["skill"]
    resource_id: str
    status: Literal["active", "inactive"]
    updated_at: AwareDatetime


class ActiveInactiveStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    status: Literal["active", "inactive"]
    expected_updated_at: AwareDatetime


class ControlService:  # noqa: E305
    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.sessions, self.audit, self.projector = sessions, audit, projector

    def _invalid_key(self, value: str | None) -> bool:
        return value is None or re.match(IDEMPOTENCY_KEY_PATTERN, value) is None

    async def _authenticate(self, authorization: str | None) -> PrincipalContext | None:
        key = bearer_key(authorization)
        if key is None:
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
        audit_session: AsyncSession | None = None,
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
            "idempotency_conflict": "status_conflict",
            "grant_conflict": "status_conflict",
            "grant_id_conflict": "status_conflict",
            "credential_inactive": "contract_validation_failed",
            "rotation_failed": "upstream_failed",
            "credential_issuance_failed": "upstream_failed",
            "resource_unavailable": "no_matching_grant",
            "policy_unavailable": "upstream_unavailable",
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
            if audit_session is None:
                await self.audit.append(event)
            else:
                await self.audit.append_in_transaction(event, audit_session)
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

    async def create_catalog_resource(
        self, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.create", "admin.write"
        scope = ("POST", "/v1/catalog/resources")
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
            body = CatalogCreate.model_validate(raw)
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
        if len(set(body.discoverability.tags)) != len(body.discoverability.tags):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        expected_source = {
            "mcp_server": "mcp",
            "mcp_tool": "mcp",
            "skill": "skill",
            "bok_collection": "bok",
            "incident_workflow": "incident_workflow",
            "service_operation": "deploy_executor",
        }[body.resource_type]
        if body.source != expected_source:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        allowed_status: dict[str, set[str]] = {
            "mcp_server": {"registered", "active", "inactive", "revoked"},
            "mcp_tool": {"registered", "active", "inactive", "revoked"},
            "skill": {"draft", "published", "active", "inactive", "revoked"},
            "bok_collection": {"draft", "indexing", "active", "inactive", "revoked"},
            "incident_workflow": {"active", "inactive"},
            "service_operation": {"active", "inactive"},
        }
        if body.status not in allowed_status[body.resource_type]:
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
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, *CONTROL_SCOPES[scope]
            )
        except AuthenticationFailed:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
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
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        canonical_path = "/v1/catalog/resources"
        binding_scope = f"{context.principal.principal_id}|POST|{canonical_path}"
        payload_hash = _payload_sha256(body.model_dump(mode="json"))
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
                        response_status=201,
                        resource_id=f"{body.resource_type}/{body.resource_id}",
                        replayed=False,
                    ),
                )
                if binding.replayed:
                    try:
                        payload = ResourceCatalogEntry.model_validate_json(
                            _canonical_payload(binding.outcome.response_payload)
                        ).model_dump(mode="json")
                    except ValidationError:
                        raise IdempotencyConflictError(binding_scope) from None
                    return Response(
                        content=_canonical_payload(payload),
                        status_code=binding.outcome.response_status,
                        media_type="application/json",
                    )
                entry = await CatalogRepository(session).create(
                    body.resource_type,
                    body.resource_id,
                    body.owner_id,
                    body.source,
                    body.source_ref,
                    body.status,
                    body.discoverability.display_name,
                    body.discoverability.visibility,
                    body.discoverability.description,
                    list(body.discoverability.tags),
                )
                payload = entry.model_dump(mode="json")
                await IdempotencyRepository(session).set_response_payload(
                    scope=binding_scope,
                    key_digest=_key_digest(idempotency_key or ""),
                    response_payload=payload,
                )
                result = await self._finish(
                    request_id,
                    started,
                    binding.outcome.response_status,
                    "authorization",
                    operation,
                    action,
                    payload=payload,
                    error_code="grant_matched",
                    context=context,
                    resource_ref=("administrative_control", "catalog"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
                if result.status_code == 503:
                    await session.rollback()
                    return result
                return Response(
                    content=_canonical_payload(payload),
                    status_code=binding.outcome.response_status,
                    media_type="application/json",
                )
        except (IdempotencyConflictError, IntegrityError):
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code="idempotency_conflict",
                context=context,
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )

    async def publish_skill_version(
        self, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.create", "admin.write"
        scope = ("POST", "/v1/skills/versions")
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
            body = SkillPublishRequest.model_validate(raw)
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
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, *CONTROL_SCOPES[scope]
            )
        except AuthenticationFailed:
            return await self._finish(
                request_id,
                started,
                401,
                "authentication",
                operation,
                action,
                error_code="authentication_failed",
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
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )

        canonical_path = "/v1/skills/versions"
        binding_scope = f"{context.principal.principal_id}|POST|{canonical_path}"
        request_payload = body.model_dump(mode="json")
        payload_hash = _payload_sha256(request_payload)
        resource_id = f"{body.skill_id}@{body.version}"
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
                        response_status=201,
                        resource_id=resource_id,
                        replayed=False,
                    ),
                )
                if binding.replayed:
                    # The stored payload is JSON (ISO timestamps); strict python-mode validation
                    # rejected it, so a same-key retry failed instead of replaying.
                    record = SkillVersionRecord.model_validate_json(
                        _canonical_payload(binding.outcome.response_payload)
                    )
                else:
                    record = await SkillVersionRepository(session).publish(
                        skill_id=body.skill_id,
                        version=body.version,
                        owner_id=body.owner_id,
                        manifest=body.manifest,
                        content_sha256=payload_hash,
                    )
                    await IdempotencyRepository(session).set_response_payload(
                        scope=binding_scope,
                        key_digest=_key_digest(idempotency_key or ""),
                        response_payload=record.model_dump(mode="json"),
                    )
                payload = record.model_dump(mode="json")
                result = await self._finish(
                    request_id,
                    started,
                    201,
                    "authorization",
                    operation,
                    action,
                    payload=payload,
                    error_code="grant_matched",
                    context=context,
                    resource_ref=("administrative_control", "catalog"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
                if result.status_code == 503:
                    await session.rollback()
                    return result
                return result
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
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )
        except SkillVersionConflictError:
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code="status_conflict",
                context=context,
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )
        except IntegrityError:
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code="status_conflict",
                context=context,
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )

    async def get_skill_version(
        self, skill_id: str, version: str, authorization: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.read", "admin.read"
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
        if (
            re.fullmatch(r"[a-z][a-z0-9-]{2,62}[a-z0-9]", skill_id) is None
            or re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version) is None
            or len(version) > 32
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
        scope = CONTROL_SCOPES[("GET", "/v1/skills/{skill_id}/{version}")]
        async with self.sessions() as session:
            evaluation = await self._authorize(session, context.principal, scope)
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
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            record = await SkillVersionRepository(session).get(skill_id, version)
            catalog = await CatalogRepository(session).get("skill", f"{skill_id}@{version}")
        if record is None or catalog is None or catalog.status == "inactive":
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload=record.model_dump(mode="json"),
            error_code="grant_matched",
            context=context,
            resource_ref=("administrative_control", "catalog"),
            decision=evaluation.decision,
        )

    async def publish_bok_version(
        self, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.create", "admin.write"
        canonical_path = "/v1/bok/collections/versions"

        def finish(status: int, stage: Any = "authorization", **evidence: Any) -> Any:
            return self._finish(request_id, started, status, stage, operation, action, **evidence)

        if self._invalid_key(idempotency_key):
            return await finish(400, "validation", error_code="invalid_idempotency_key")
        try:
            body = BoKPublishRequest.model_validate(raw)
        except ValidationError:
            return await finish(422, "validation", error_code="validation_error")
        try:
            context, evaluation = await authorize_governed_access(
                self.sessions, authorization, *CONTROL_SCOPES[("POST", canonical_path)]
            )
        except AuthenticationFailed:
            return await finish(401, "authentication", error_code="authentication_failed")
        granted = {
            "context": context,
            "resource_ref": ("administrative_control", "catalog"),
            "decision": evaluation.decision,
        }
        if evaluation.decision.decision == "deny":
            return await finish(
                403,
                error_code="resource_unavailable",
                authorization_denial_cause=evaluation.denial_cause,
                **granted,
            )

        binding_scope = f"{context.principal.principal_id}|POST|{canonical_path}"
        resource_id = f"{body.collection_id}@{body.version}"
        try:
            async with self.sessions() as session, session.begin():
                binding = await IdempotencyRepository(session).claim_or_replay(
                    scope=binding_scope,
                    key_digest=_key_digest(idempotency_key or ""),
                    payload_sha256=_payload_sha256(body.model_dump(mode="json")),
                    principal_id=context.principal.principal_id,
                    method="POST",
                    canonical_path=canonical_path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=resource_id, replayed=False
                    ),
                )
                if binding.replayed:
                    status, payload = 200, binding.outcome.response_payload
                else:
                    summary, created = await publish_bok_version(
                        session, body, author=context.principal, origin="console"
                    )
                    status, payload = (201 if created else 200), summary.model_dump(mode="json")
                    await IdempotencyRepository(session).set_response_payload(
                        scope=binding_scope,
                        key_digest=_key_digest(idempotency_key or ""),
                        response_payload=payload,
                    )
                result = await finish(
                    status,
                    payload=payload,
                    error_code="grant_matched",
                    audit_session=session,
                    **granted,
                )
                if result.status_code == 503:
                    await session.rollback()
                return result
        except IdempotencyConflictError:
            return await finish(409, error_code="idempotency_conflict", **granted)
        except BoKAuthorRefused:
            return await finish(403, error_code="resource_unavailable", **granted)
        except (BoKVersionCollision, IntegrityError):
            return await finish(409, error_code="status_conflict", **granted)

    async def get_bok_version(
        self, collection_id: str, version: str, authorization: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.read", "admin.read"

        def finish(status: int, stage: Any = "authorization", **evidence: Any) -> Any:
            return self._finish(request_id, started, status, stage, operation, action, **evidence)

        context = await self._authenticate(authorization)
        if context is None:
            return await finish(401, "authentication", error_code="authentication_failed")
        if (
            re.fullmatch(BOK_SLUG_PATTERN, collection_id) is None
            or re.fullmatch(SEMVER_PATTERN, version) is None
            or len(version) > 32
        ):
            return await finish(422, "validation", error_code="validation_error")
        scope = CONTROL_SCOPES[("GET", "/v1/bok/collections/{collection_id}/versions/{version}")]
        async with self.sessions() as session:
            evaluation = await self._authorize(session, context.principal, scope)
        granted = {
            "context": context,
            "resource_ref": ("administrative_control", "catalog"),
            "decision": evaluation.decision,
        }
        if evaluation.decision.decision == "deny":
            return await finish(
                403,
                error_code="resource_unavailable",
                authorization_denial_cause=evaluation.denial_cause,
                **granted,
            )
        async with self.sessions() as session:
            record = await read_bok_version(session, collection_id, version)
        if record is None:
            return await finish(404, error_code="resource_not_found", **granted)
        return await finish(
            200, payload=record.model_dump(mode="json"), error_code="grant_matched", **granted
        )

    async def get_skill_status(
        self, skill_id: str, version: str, authorization: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.read", "admin.write"
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
        if (
            re.fullmatch(r"[a-z][a-z0-9-]{2,62}[a-z0-9]", skill_id) is None
            or len(version) > 32
            or re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version) is None
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
        scope = CONTROL_SCOPES[("GET", "/v1/skills/{skill_id}/{version}/status")]
        async with self.sessions() as session:
            evaluation = await self._authorize(session, context.principal, scope)
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
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            located = await SkillVersionRepository(session).get_status(skill_id, version)
        if located is None:
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )
        _entry, updated_at = located
        if _entry.status not in ("active", "inactive"):
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload=SkillStatusResponse(
                resource_type="skill",
                resource_id=f"{skill_id}@{version}",
                status=_entry.status,  # type: ignore[arg-type]
                updated_at=updated_at,
            ).model_dump(mode="json"),
            error_code="grant_matched",
            context=context,
            resource_ref=("administrative_control", "catalog"),
            decision=evaluation.decision,
        )

    async def replace_skill_status(
        self, skill_id: str, version: str, raw: Any, authorization: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.status.replace", "admin.write"
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
        if (
            re.fullmatch(r"[a-z][a-z0-9-]{2,62}[a-z0-9]", skill_id) is None
            or len(version) > 32
            or re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version) is None
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
        try:
            body = ActiveInactiveStatus.model_validate_json(_canonical_payload(raw))
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
        scope = CONTROL_SCOPES[("PUT", "/v1/skills/{skill_id}/{version}/status")]
        async with self.sessions() as session:
            evaluation = await self._authorize(session, context.principal, scope)
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
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        try:
            async with self.sessions() as session, session.begin():
                changed = await SkillVersionRepository(session).replace_status(
                    skill_id,
                    version,
                    body.status,
                    expected_updated_at=body.expected_updated_at,
                )
                payload = None
                if changed is not None:
                    entry, updated_at = changed
                    payload = SkillStatusResponse(
                        resource_type="skill",
                        resource_id=entry.resource_id,
                        status=entry.status,
                        updated_at=updated_at,
                    ).model_dump(mode="json")
                result = await self._finish(
                    request_id,
                    started,
                    404 if changed is None else 200,
                    "authorization",
                    operation,
                    action,
                    payload=payload,
                    error_code="resource_not_found" if changed is None else "grant_matched",
                    context=context,
                    resource_ref=("administrative_control", "catalog"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
                if result.status_code == 503:
                    await session.rollback()
                return result
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
                resource_ref=("administrative_control", "catalog"),
                decision=evaluation.decision,
            )


def control_router(service: ControlService) -> APIRouter:
    """Typed administrative control-plane router with Issue #184 catalog reads/writes."""
    router = APIRouter()
    bearer_scheme = HTTPBearer(auto_error=False, description="Administrative bearer credential")
    bearer_credentials: Any = Security(bearer_scheme)

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

    @router.post(
        "/v1/skills/versions",
        status_code=201,
        response_model=SkillVersionRecord,
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
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
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": SkillPublishRequest.model_json_schema()}
                },
            },
            **CONTROL[("POST", "/v1/skills/versions")].openapi_extra,
        },
    )
    async def publish_skill_version(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.publish_skill_version(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/skills/{skill_id}/{version}",
        response_model=SkillVersionRecord,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra=CONTROL[("GET", "/v1/skills/{skill_id}/{version}")].openapi_extra,
    )
    async def get_skill_version(
        skill_id: Annotated[
            str,
            WithJsonSchema({"type": "string", "pattern": r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$"}),
        ],
        version: Annotated[
            str,
            WithJsonSchema(
                {
                    "type": "string",
                    "pattern": r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
                    "maxLength": 32,
                }
            ),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.get_skill_version(
            skill_id, version, authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/skills/{skill_id}/{version}/status",
        response_model=SkillStatusResponse,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra=CONTROL[("GET", "/v1/skills/{skill_id}/{version}/status")].openapi_extra,
    )
    async def get_skill_status(
        skill_id: Annotated[
            str,
            WithJsonSchema({"type": "string", "pattern": r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$"}),
        ],
        version: Annotated[
            str,
            WithJsonSchema(
                {
                    "type": "string",
                    "maxLength": 32,
                    "pattern": r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
                }
            ),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.get_skill_status(
            skill_id, version, authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

    @router.put(
        "/v1/skills/{skill_id}/{version}/status",
        response_model=SkillStatusResponse,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": ActiveInactiveStatus.model_json_schema()}
                },
            },
            **CONTROL[("PUT", "/v1/skills/{skill_id}/{version}/status")].openapi_extra,
        },
    )
    async def replace_skill_status(
        skill_id: Annotated[
            str,
            WithJsonSchema({"type": "string", "pattern": r"^[a-z][a-z0-9-]{2,62}[a-z0-9]$"}),
        ],
        version: Annotated[
            str,
            WithJsonSchema(
                {
                    "type": "string",
                    "maxLength": 32,
                    "pattern": r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
                }
            ),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.replace_skill_status(
            skill_id,
            version,
            await raw_json(request),
            authorization_from(credentials, request),
        )
        response.status_code = result.status_code
        return result

    @router.post(
        "/v1/bok/collections/versions",
        status_code=201,
        response_model=BoKVersionSummary,
        responses={
            200: {"model": BoKVersionSummary},
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
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
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": BoKPublishRequest.model_json_schema()}},
            },
            **CONTROL[("POST", "/v1/bok/collections/versions")].openapi_extra,
        },
    )
    async def publish_bok_version(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.publish_bok_version(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/bok/collections/{collection_id}/versions/{version}",
        response_model=BoKVersionRecord,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra=CONTROL[
            ("GET", "/v1/bok/collections/{collection_id}/versions/{version}")
        ].openapi_extra,
    )
    async def get_bok_version(
        collection_id: Annotated[
            str, WithJsonSchema({"type": "string", "pattern": BOK_SLUG_PATTERN})
        ],
        version: Annotated[
            str,
            WithJsonSchema({"type": "string", "maxLength": 32, "pattern": SEMVER_PATTERN}),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.get_bok_version(
            collection_id, version, authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

    return router
