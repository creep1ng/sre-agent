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
    CredentialReference,
    Grant,
    ModelAlias,
    Principal,
    PrincipalContext,
    Resource,
    ResourceCatalogEntry,
    SkillManifest,
    SkillVersionRecord,
)
from sre_agent.persistence.repositories import CatalogRepository, CredentialRepository, GrantRepository, IdempotencyConflictError, IdempotencyOutcome, IdempotencyRepository, ModelAliasRepository, PrincipalRepository, ResourceRepository, SkillVersionConflictError, SkillVersionRepository, StaleWriteError  # fmt: skip
from sre_agent.vocabulary import IDENTIFIER_PATTERN, Identifier, is_identifier

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


class CredentialIssue(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    expires_at: AwareDatetime | None = None


class RotationIssuanceFailure(RuntimeError):
    """A replacement key could not be issued after the old credential was locked."""


class GrantCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    grant_id: Identifier
    principal_id: Identifier
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{1,63}$")]
    resource: Resource
    effect: Literal["allow"]


# Admitted grant actions per resource contract (#423 CA3). Exact membership in
# the per-type sets below: the resource-catalog owner/state/action matrix
# (schemas/releases/*/conformance/resource-catalog-matrix.yaml) plus the
# vocabularies the runtime actually evaluates: bare "invoke" on skill
# (gateway/skills.py) alongside skill.invoke, admin.read/admin.write over
# administrative_control (CONTROL_SCOPES), and the run.*, alert.*,
# incident.declare and change.* (#770) actions over incident_workflow
# (agent/api/authorization.v1.yaml and agent/api/triage.openapi.yaml). Dotted refinements such as "invoke.delete"
# or "run.start.unpublished" are absent from those closed contracts and the
# engine matches grant.action exactly, so they are rejected without mutation.
# This is a pure lookup: it never touches a repository, so a denied caller
# still receives 403 before any target access.
# mitigation.execute over service_operation comes from the `governance` block of
# schemas/executor/1.0.0/deploy-executor.yaml (#722).
GRANT_ADMITTED_ACTIONS: dict[str, frozenset[str]] = {
    "llm_model": frozenset({"admin.read", "admin.write", "invoke"}),
    "mcp_server": frozenset({"admin.write", "mcp.discovery", "mcp.invoke"}),
    "mcp_tool": frozenset({"admin.write", "mcp.discovery", "mcp.invoke"}),
    "skill": frozenset({"admin.write", "skill.discovery", "skill.read", "skill.invoke", "invoke"}),
    "bok_collection": frozenset({"admin.write", "bok.discovery", "bok.search", "bok.read"}),
    "incident_workflow": frozenset(
        {
            "run.start",
            "run.read",
            "run.command",
            "run.approve",
            "run.read_context",
            "alert.read",
            "alert.triage",
            "alert.dismiss",
            "alert.associate",
            "incident.declare",
            "change.read",
            "change.write",
        }
    ),
    "administrative_control": frozenset({"admin.read", "admin.write"}),
    "service_operation": frozenset({"mitigation.execute"}),
}


def _grant_action_admitted(resource_type: str, action: str) -> bool:
    return action in GRANT_ADMITTED_ACTIONS.get(resource_type, frozenset())


def _grant_conflict_code(error: Exception) -> str:
    """Name the constraint a new grant violated, not a generic idempotency conflict (#759)."""
    diag = getattr(getattr(error, "orig", None), "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    return {"grants_pkey": "grant_id_conflict", "uq_grants_active_direct": "grant_conflict"}.get(
        constraint, "idempotency_conflict"
    )


class GrantListResponse(BaseModel):
    items: list[Grant]
    limit: int
    truncated: bool


class ModelAliasCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model_alias_id: Identifier
    alias: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    concrete_model: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$")]
    router: Literal["openrouter"]
    inference_provider: Annotated[str, Field(min_length=1, max_length=100)]
    # Additive ADMIN-authoritative catalog projection for llm_model. All
    # optional so pre-T6 creates keep working; when absent the projection
    # derives owner/source_ref from the alias with a private default.
    owner_id: Identifier | None = None
    source: Literal["model_alias"] | None = None
    source_ref: (
        Annotated[
            str,
            Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$"),
        ]
        | None
    ) = None
    display_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    visibility: Literal["public", "private", "hidden"] | None = None
    description: Annotated[str, Field(max_length=500)] | None = None
    tags: (
        Annotated[
            list[
                Annotated[
                    str, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9._-]*$")
                ]
            ],
            Field(max_length=16),
        ]
        | None
    ) = None


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


class CatalogListResponse(BaseModel):
    items: list[ResourceCatalogEntry]
    limit: int
    truncated: bool


class ModelAliasListResponse(BaseModel):
    items: list[ModelAlias]
    limit: int
    truncated: bool


class ModelAliasAssignment(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    concrete_model: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$")]
    router: Literal["openrouter"]
    inference_provider: Annotated[str, Field(min_length=1, max_length=100)]
    expected_updated_at: AwareDatetime


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

    async def _rotation_failure(
        self,
        request_id: UUID,
        started: float,
        context: PrincipalContext,
        decision: Any,
        old_credential: CredentialReference,
        error_code: Literal["credential_inactive", "rotation_failed"],
    ) -> Response:
        return await self._finish(
            request_id,
            started,
            409,
            "authorization",
            "credentials.rotate",
            "admin.write",
            payload={
                "result": "failure",
                "old_credential": old_credential.model_dump(mode="json"),
                "replacement_count": 0,
                "transition_count": 0,
                "replayed": False,
                "error_code": error_code,
            },
            error_code=error_code,
            context=context,
            resource_ref=("administrative_control", "credentials"),
            decision=decision,
        )

    async def rotate_credential(
        self, credential_id: str, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "credentials.rotate", "admin.write"
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
        if not is_identifier(credential_id):
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
            body = CredentialIssue.model_validate_json(_canonical_payload(raw))
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
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("POST", "/v1/credentials/{id}/rotation")],
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
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        canonical_path = f"/v1/credentials/{credential_id}/rotation"
        try:
            async with self.sessions() as session, session.begin():
                old_credential = await CredentialRepository(session).get(credential_id)
                if old_credential is None:
                    return await self._finish(
                        request_id,
                        started,
                        404,
                        "authorization",
                        operation,
                        action,
                        error_code="resource_not_found",
                        context=context,
                        resource_ref=("administrative_control", "credentials"),
                        decision=evaluation.decision,
                    )
                binding = await IdempotencyRepository(session).claim_or_replay(
                    scope=f"{context.principal.principal_id}|POST|{canonical_path}",
                    key_digest=_key_digest(idempotency_key or ""),
                    payload_sha256=_payload_sha256(body.model_dump(mode="json")),
                    principal_id=context.principal.principal_id,
                    method="POST",
                    canonical_path=canonical_path,
                    binding="principal_lifetime",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=credential_id, replayed=False
                    ),
                )
                if binding.replayed:
                    payload = {**binding.outcome.response_payload, "replayed": True}
                elif old_credential.status != "active":
                    await session.rollback()
                    return await self._rotation_failure(
                        request_id,
                        started,
                        context,
                        evaluation.decision,
                        old_credential,
                        "credential_inactive",
                    )
                else:
                    try:
                        issued = await CredentialRepository(session).rotate(
                            credential_id, expires_at=body.expires_at
                        )
                    except Exception:
                        await session.rollback()
                        return await self._rotation_failure(
                            request_id,
                            started,
                            context,
                            evaluation.decision,
                            old_credential,
                            "rotation_failed",
                        )
                    if issued is None:
                        await session.rollback()
                        return await self._rotation_failure(
                            request_id,
                            started,
                            context,
                            evaluation.decision,
                            old_credential,
                            "credential_inactive",
                        )
                    metadata = {
                        "result": "success",
                        "old_credential": old_credential.model_dump(mode="json"),
                        "issuance": {
                            "credential": issued.credential.model_dump(mode="json"),
                            "replaced_credential_id": old_credential.credential_id,
                            "secret_revealed": False,
                        },
                        "replacement_count": 1,
                        "transition_count": 1,
                        "replayed": False,
                    }
                    await IdempotencyRepository(session).set_response_payload(
                        scope=f"{context.principal.principal_id}|POST|{canonical_path}",
                        key_digest=_key_digest(idempotency_key or ""),
                        response_payload=metadata,
                    )
                    payload = {
                        **metadata,
                        "issuance": {
                            **metadata["issuance"],
                            "key": issued.key,
                            "secret_revealed": True,
                        },
                    }
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
                resource_ref=("administrative_control", "credentials"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            201,
            "authorization",
            operation,
            action,
            payload=payload,
            context=context,
            resource_ref=("administrative_control", "credentials"),
            decision=evaluation.decision,
        )

    async def create_grant(
        self, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "grants.create", "admin.write"
        scope = ("POST", "/v1/grants")
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
            body = GrantCreate.model_validate(raw)
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
                resource_ref=("administrative_control", "grants"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )

        canonical_path = "/v1/grants"
        binding_scope = f"{context.principal.principal_id}|POST|{canonical_path}"
        payload_hash = _payload_sha256(body.model_dump(mode="json"))
        try:
            async with self.sessions() as session, session.begin():
                prior = await IdempotencyRepository(session).peek(
                    scope=binding_scope,
                    key_digest=_key_digest(idempotency_key or ""),
                    payload_sha256=payload_hash,
                )
                if prior is not None:
                    try:
                        payload = Grant.model_validate_json(
                            _canonical_payload(prior.outcome.response_payload)
                        ).model_dump(mode="json")
                    except ValidationError:
                        raise IdempotencyConflictError(binding_scope) from None
                    return Response(
                        content=_canonical_payload(payload),
                        status_code=prior.outcome.response_status,
                        media_type="application/json",
                    )
                principal = await PrincipalRepository(session).get(body.principal_id)
                if principal is None or principal.status != "active":
                    return await self._finish(
                        request_id,
                        started,
                        404,
                        "authorization",
                        operation,
                        action,
                        error_code="resource_not_found",
                        context=context,
                        resource_ref=("administrative_control", "grants"),
                        decision=evaluation.decision,
                    )
                fact = await ResourceRepository(session).authorization_view(
                    body.resource.resource_type, body.resource.resource_id
                )
                if fact is None or fact.status != "active":
                    return await self._finish(
                        request_id,
                        started,
                        404,
                        "authorization",
                        operation,
                        action,
                        error_code="resource_not_found",
                        context=context,
                        resource_ref=("administrative_control", "grants"),
                        decision=evaluation.decision,
                    )
                if not _grant_action_admitted(body.resource.resource_type, body.action):
                    return await self._finish(
                        request_id,
                        started,
                        422,
                        "validation",
                        operation,
                        action,
                        error_code="validation_error",
                    )
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
                        resource_id=body.grant_id,
                        replayed=False,
                    ),
                )
                repository = GrantRepository(session)
                if binding.replayed:
                    try:
                        payload = Grant.model_validate_json(
                            _canonical_payload(binding.outcome.response_payload)
                        ).model_dump(mode="json")
                    except ValidationError:
                        raise IdempotencyConflictError(binding_scope) from None
                    return Response(
                        content=_canonical_payload(payload),
                        status_code=binding.outcome.response_status,
                        media_type="application/json",
                    )
                grant = await repository.create(
                    body.grant_id,
                    body.principal_id,
                    body.action,
                    body.resource.resource_type,
                    body.resource.resource_id,
                )
                payload = grant.model_dump(mode="json")
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
                    resource_ref=("administrative_control", "grants"),
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
        except (IdempotencyConflictError, IntegrityError) as conflict:
            return await self._finish(
                request_id,
                started,
                409,
                "authorization",
                operation,
                action,
                error_code=_grant_conflict_code(conflict),
                context=context,
                resource_ref=("administrative_control", "grants"),
                decision=evaluation.decision,
            )

    async def list_grants(
        self,
        authorization: str | None,
        principal_id: str | None,
        resource_id: str | None,
        limit: Any,
        extra_params: dict[str, Any],
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "grants.list", "admin.read"
        try:
            parsed_limit = int(limit)
            if isinstance(limit, str) and not limit.isdigit():
                raise ValueError
            ListPrincipalsQuery.model_validate({"limit": parsed_limit})
        except (TypeError, ValueError, ValidationError):
            parsed_limit = 0
        exactly_one_filter = (principal_id is None) != (resource_id is None)
        filter_value = principal_id if principal_id is not None else resource_id
        if (
            extra_params
            or not exactly_one_filter
            or filter_value is None
            or not is_identifier(filter_value)
            or not 1 <= parsed_limit <= 100
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
            context, evaluation = await authorize_governed_access(
                self.sessions,
                authorization,
                *CONTROL_SCOPES[("GET", "/v1/grants")],
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
                resource_ref=("administrative_control", "grants"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            items, truncated = await GrantRepository(session).list_filtered(
                principal_id=principal_id,
                resource_id=resource_id,
                limit=parsed_limit,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload={
                "items": [item.model_dump(mode="json") for item in items],
                "limit": parsed_limit,
                "truncated": truncated,
            },
            error_code="grant_matched",
            context=context,
            resource_ref=("administrative_control", "grants"),
            decision=evaluation.decision,
        )

    async def revoke_grant(self, grant_id: str, authorization: str | None) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "grants.revoke", "admin.write"
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
        if not is_identifier(grant_id):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session, context.principal, CONTROL_SCOPES[("DELETE", "/v1/grants/{id}")]
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
                resource_ref=("administrative_control", "grants"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session, session.begin():
            grant = await GrantRepository(session).revoke(grant_id)
            if grant is None:
                result = await self._finish(
                    request_id,
                    started,
                    404,
                    "authorization",
                    operation,
                    action,
                    error_code="resource_not_found",
                    context=context,
                    resource_ref=("administrative_control", "grants"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
            else:
                result = await self._finish(
                    request_id,
                    started,
                    204,
                    "authorization",
                    operation,
                    action,
                    error_code="grant_matched",
                    context=context,
                    resource_ref=("administrative_control", "grants"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
            if result.status_code == 503:
                await session.rollback()
            return result

    async def create_alias(
        self, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "aliases.create", "admin.write"
        scope = ("POST", "/v1/model-aliases")
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
            body = ModelAliasCreate.model_validate(raw)
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
        if body.tags is not None and len(set(body.tags)) != len(body.tags):
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
                resource_ref=("administrative_control", "model_aliases"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )

        canonical_path = "/v1/model-aliases"
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
                        resource_id=body.model_alias_id,
                        replayed=False,
                    ),
                )
                if binding.replayed:
                    try:
                        payload = ModelAlias.model_validate_json(
                            _canonical_payload(binding.outcome.response_payload)
                        ).model_dump(mode="json")
                    except ValidationError:
                        raise IdempotencyConflictError(binding_scope) from None
                    return Response(
                        content=_canonical_payload(payload),
                        status_code=binding.outcome.response_status,
                        media_type="application/json",
                    )
                alias = await ModelAliasRepository(session).create(
                    body.model_alias_id,
                    body.alias,
                    body.concrete_model,
                    body.router,
                    body.inference_provider,
                    owner_id=body.owner_id,
                    source_ref=body.source_ref,
                    display_name=body.display_name,
                    visibility=body.visibility,
                    description=body.description,
                    tags=body.tags,
                )
                payload = alias.model_dump(mode="json")
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
                    resource_ref=("administrative_control", "model_aliases"),
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
                resource_ref=("administrative_control", "model_aliases"),
                decision=evaluation.decision,
            )

    async def list_aliases(
        self,
        authorization: str | None,
        limit: Any,
        extra_params: dict[str, Any],
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "aliases.list", "admin.read"
        try:
            parsed_limit = int(limit)
            if isinstance(limit, str) and not limit.isdigit():
                raise ValueError
            ListPrincipalsQuery.model_validate({"limit": parsed_limit})
        except (TypeError, ValueError, ValidationError):
            parsed_limit = 0
        if extra_params or not 1 <= parsed_limit <= 100:
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
                self.sessions,
                authorization,
                *CONTROL_SCOPES[("GET", "/v1/model-aliases")],
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
                resource_ref=("administrative_control", "model_aliases"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            items, truncated = await ModelAliasRepository(session).list(limit=parsed_limit)
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload={
                "items": [item.model_dump(mode="json") for item in items],
                "limit": parsed_limit,
                "truncated": truncated,
            },
            error_code="grant_matched",
            context=context,
            resource_ref=("administrative_control", "model_aliases"),
            decision=evaluation.decision,
        )

    async def get_alias(self, model_alias_id: str, authorization: str | None) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "aliases.get", "admin.read"
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
        if not is_identifier(model_alias_id):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("GET", "/v1/model-aliases/{id}")],
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
                resource_ref=("administrative_control", "model_aliases"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session:
            alias = await ModelAliasRepository(session).get(model_alias_id)
        if alias is None:
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                operation,
                action,
                error_code="resource_not_found",
                context=context,
                resource_ref=("administrative_control", "model_aliases"),
                decision=evaluation.decision,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload=alias.model_dump(mode="json"),
            error_code="grant_matched",
            context=context,
            resource_ref=("administrative_control", "model_aliases"),
            decision=evaluation.decision,
        )

    async def replace_alias_assignment(
        self, model_alias_id: str, raw: Any, authorization: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "aliases.assignment.replace", "admin.write"
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
        if not is_identifier(model_alias_id):
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
            body = ModelAliasAssignment.model_validate_json(_canonical_payload(raw))
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
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("PUT", "/v1/model-aliases/{id}/assignment")],
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
                resource_ref=("administrative_control", "model_aliases"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session, session.begin():
            try:
                alias = await ModelAliasRepository(session).replace_assignment(
                    model_alias_id,
                    concrete_model=body.concrete_model,
                    router=body.router,
                    inference_provider=body.inference_provider,
                    expected_updated_at=body.expected_updated_at,
                )
            except StaleWriteError:
                await session.rollback()
                return await self._finish(
                    request_id,
                    started,
                    409,
                    "authorization",
                    operation,
                    action,
                    error_code="status_conflict",
                    context=context,
                    resource_ref=("administrative_control", "model_aliases"),
                    decision=evaluation.decision,
                )
            if alias is None:
                result = await self._finish(
                    request_id,
                    started,
                    404,
                    "authorization",
                    operation,
                    action,
                    error_code="resource_not_found",
                    context=context,
                    resource_ref=("administrative_control", "model_aliases"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
            else:
                result = await self._finish(
                    request_id,
                    started,
                    200,
                    "authorization",
                    operation,
                    action,
                    payload=alias.model_dump(mode="json"),
                    error_code="grant_matched",
                    context=context,
                    resource_ref=("administrative_control", "model_aliases"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
            if result.status_code == 503:
                await session.rollback()
            return result

    async def replace_alias_status(
        self, model_alias_id: str, raw: Any, authorization: str | None
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "aliases.status.replace", "admin.write"
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
        if not is_identifier(model_alias_id):
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
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("PUT", "/v1/model-aliases/{id}/status")],
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
                resource_ref=("administrative_control", "model_aliases"),
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
            )
        async with self.sessions() as session, session.begin():
            try:
                alias = await ModelAliasRepository(session).replace_status(
                    model_alias_id,
                    body.status,
                    expected_updated_at=body.expected_updated_at,
                )
            except StaleWriteError:
                await session.rollback()
                return await self._finish(
                    request_id,
                    started,
                    409,
                    "authorization",
                    operation,
                    action,
                    error_code="status_conflict",
                    context=context,
                    resource_ref=("administrative_control", "model_aliases"),
                    decision=evaluation.decision,
                )
            if alias is None:
                result = await self._finish(
                    request_id,
                    started,
                    404,
                    "authorization",
                    operation,
                    action,
                    error_code="resource_not_found",
                    context=context,
                    resource_ref=("administrative_control", "model_aliases"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
            else:
                result = await self._finish(
                    request_id,
                    started,
                    200,
                    "authorization",
                    operation,
                    action,
                    payload=alias.model_dump(mode="json"),
                    error_code="grant_matched",
                    context=context,
                    resource_ref=("administrative_control", "model_aliases"),
                    decision=evaluation.decision,
                    audit_session=session,
                )
            if result.status_code == 503:
                await session.rollback()
            return result

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

    async def list_catalog_resources(
        self,
        authorization: str | None,
        resource_type: Any,
        owner_id: Any,
        status: Any,
        visibility: Any,
        limit: Any,
        extra_params: dict[str, Any],
    ) -> Response:
        request_id, started = uuid4(), monotonic()
        operation, action = "catalog.list", "admin.read"
        valid_types = {
            "llm_model",
            "mcp_server",
            "mcp_tool",
            "skill",
            "bok_collection",
            "incident_workflow",
            "service_operation",
        }
        valid_status = {
            "registered",
            "draft",
            "published",
            "indexing",
            "active",
            "inactive",
            "revoked",
        }
        valid_visibility = {"public", "private", "hidden"}
        try:
            parsed_limit = int(limit)
            if isinstance(limit, str) and not limit.isdigit():
                raise ValueError
            ListPrincipalsQuery.model_validate({"limit": parsed_limit})
            if not 1 <= parsed_limit <= 100:
                raise ValueError
            if extra_params:
                raise ValueError
            if resource_type is not None and resource_type not in valid_types:
                raise ValueError
            if owner_id is not None and not is_identifier(owner_id):
                raise ValueError
            if status is not None and status not in valid_status:
                raise ValueError
            if visibility is not None and visibility not in valid_visibility:
                raise ValueError
        except (TypeError, ValueError, ValidationError):
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
                self.sessions, authorization, *CONTROL_SCOPES[("GET", "/v1/catalog/resources")]
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
        async with self.sessions() as session:
            items, truncated = await CatalogRepository(session).list(
                resource_type=resource_type,
                owner_id=owner_id,
                status=status,
                visibility=visibility,
                limit=parsed_limit,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            operation,
            action,
            payload={
                "items": [item.model_dump(mode="json") for item in items],
                "limit": parsed_limit,
                "truncated": truncated,
            },
            error_code="grant_matched",
            context=context,
            resource_ref=("administrative_control", "catalog"),
            decision=evaluation.decision,
        )

    async def get_catalog_resource(
        self, resource_type: str, resource_id: str, authorization: str | None
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
        if resource_type not in {
            "llm_model",
            "mcp_server",
            "mcp_tool",
            "skill",
            "bok_collection",
            "incident_workflow",
            "service_operation",
        } or (re.match(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$", resource_id) is None):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                operation,
                action,
                error_code="validation_error",
            )
        async with self.sessions() as session:
            evaluation = await self._authorize(
                session,
                context.principal,
                CONTROL_SCOPES[("GET", "/v1/catalog/resources/{type}/{id}")],
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
        async with self.sessions() as session:
            entry = await CatalogRepository(session).get(resource_type, resource_id)
        if (
            entry is None
            or entry.discoverability.visibility == "hidden"
            or entry.status == "inactive"
        ):
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
            payload=entry.model_dump(mode="json"),
            error_code="grant_matched",
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
        "/v1/grants",
        status_code=201,
        response_model=Grant,
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
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
                "content": {"application/json": {"schema": GrantCreate.model_json_schema()}},
            },
            **CONTROL[("POST", "/v1/grants")].openapi_extra,
        },
    )
    async def create_grant(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.create_grant(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/grants",
        response_model=GrantListResponse,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "principal_id",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string", "pattern": IDENTIFIER_PATTERN},
                },
                {
                    "name": "resource_id",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string", "pattern": IDENTIFIER_PATTERN},
                },
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
                },
            ],
            "x-required-query-any-of": ["principal_id", "resource_id"],
            "x-forbidden-query-parameters": [
                "cursor",
                "page",
                "offset",
                "continuation_token",
                "next",
            ],
            **CONTROL[("GET", "/v1/grants")].openapi_extra,
        },
    )
    async def list_grants(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        known = {"principal_id", "resource_id", "limit"}
        result = await service.list_grants(
            authorization_from(credentials, request),
            request.query_params.get("principal_id"),
            request.query_params.get("resource_id"),
            request.query_params.get("limit", "100"),
            {key: value for key, value in request.query_params.items() if key not in known},
        )
        response.status_code = result.status_code
        return result

    @router.delete(
        "/v1/grants/{grant_id}",
        status_code=204,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
    )
    async def revoke_grant(
        grant_id: str,
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.revoke_grant(grant_id, authorization_from(credentials, request))
        response.status_code = result.status_code
        return result

    @router.post(
        "/v1/model-aliases",
        status_code=201,
        response_model=ModelAlias,
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
                "content": {"application/json": {"schema": ModelAliasCreate.model_json_schema()}},
            },
            **CONTROL[("POST", "/v1/model-aliases")].openapi_extra,
        },
    )
    async def create_alias(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.create_alias(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/model-aliases",
        response_model=ModelAliasListResponse,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
                },
            ],
            "x-forbidden-query-parameters": [
                "cursor",
                "page",
                "offset",
                "continuation_token",
                "next",
            ],
            **CONTROL[("GET", "/v1/model-aliases")].openapi_extra,
        },
    )
    async def list_aliases(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        known = {"limit"}
        result = await service.list_aliases(
            authorization_from(credentials, request),
            request.query_params.get("limit", "100"),
            {key: value for key, value in request.query_params.items() if key not in known},
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/model-aliases/{alias_id}",
        response_model=ModelAlias,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra=CONTROL[("GET", "/v1/model-aliases/{id}")].openapi_extra,
    )
    async def get_alias(
        alias_id: Annotated[
            str,
            WithJsonSchema({"type": "string", "pattern": IDENTIFIER_PATTERN}),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.get_alias(alias_id, authorization_from(credentials, request))
        response.status_code = result.status_code
        return result

    @router.put(
        "/v1/model-aliases/{alias_id}/assignment",
        response_model=ModelAlias,
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
                    "application/json": {"schema": ModelAliasAssignment.model_json_schema()}
                },
            },
            **CONTROL[("PUT", "/v1/model-aliases/{id}/assignment")].openapi_extra,
        },
    )
    async def replace_alias_assignment(
        alias_id: Annotated[
            str,
            WithJsonSchema({"type": "string", "pattern": IDENTIFIER_PATTERN}),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.replace_alias_assignment(
            alias_id, await raw_json(request), authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

    @router.put(
        "/v1/model-aliases/{alias_id}/status",
        response_model=ModelAlias,
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
            **CONTROL[("PUT", "/v1/model-aliases/{id}/status")].openapi_extra,
        },
    )
    async def replace_alias_status(
        alias_id: Annotated[
            str,
            WithJsonSchema({"type": "string", "pattern": IDENTIFIER_PATTERN}),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.replace_alias_status(
            alias_id, await raw_json(request), authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

    @router.post(
        "/v1/catalog/resources",
        status_code=201,
        response_model=ResourceCatalogEntry,
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
                "content": {"application/json": {"schema": CatalogCreate.model_json_schema()}},
            },
            **CONTROL[("POST", "/v1/catalog/resources")].openapi_extra,
        },
    )
    async def create_catalog_resource(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.create_catalog_resource(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/catalog/resources",
        response_model=CatalogListResponse,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "resource_type",
                    "in": "query",
                    "required": False,
                    "schema": {
                        "enum": ["llm_model", "mcp_server", "mcp_tool", "skill", "bok_collection"]
                    },
                },
                {
                    "name": "owner_id",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string", "pattern": IDENTIFIER_PATTERN},
                },
                {
                    "name": "status",
                    "in": "query",
                    "required": False,
                    "schema": {
                        "enum": [
                            "registered",
                            "draft",
                            "published",
                            "indexing",
                            "active",
                            "inactive",
                            "revoked",
                        ]
                    },
                },
                {
                    "name": "visibility",
                    "in": "query",
                    "required": False,
                    "schema": {"enum": ["public", "private", "hidden"]},
                },
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 100, "minimum": 1, "maximum": 100},
                },
            ],
            "x-forbidden-query-parameters": [
                "cursor",
                "page",
                "offset",
                "continuation_token",
                "next",
            ],
            **CONTROL[("GET", "/v1/catalog/resources")].openapi_extra,
        },
    )
    async def list_catalog_resources(
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        known = {"resource_type", "owner_id", "status", "visibility", "limit"}
        result = await service.list_catalog_resources(
            authorization_from(credentials, request),
            request.query_params.get("resource_type"),
            request.query_params.get("owner_id"),
            request.query_params.get("status"),
            request.query_params.get("visibility"),
            request.query_params.get("limit", "100"),
            {key: value for key, value in request.query_params.items() if key not in known},
        )
        response.status_code = result.status_code
        return result

    @router.get(
        "/v1/catalog/resources/{resource_type}/{id}",
        response_model=ResourceCatalogEntry,
        responses={
            401: {"model": ErrorEnvelope},
            403: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        openapi_extra=CONTROL[("GET", "/v1/catalog/resources/{type}/{id}")].openapi_extra,
    )
    async def get_catalog_resource(
        resource_type: Annotated[
            str,
            WithJsonSchema(
                {"enum": ["llm_model", "mcp_server", "mcp_tool", "skill", "bok_collection"]}
            ),
        ],
        id: Annotated[
            str,
            WithJsonSchema(
                {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 200,
                    "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$",
                }
            ),
        ],
        request: Request,
        response: Response,
        credentials: HTTPAuthorizationCredentials | None = bearer_credentials,
    ) -> Response:
        result = await service.get_catalog_resource(
            resource_type, id, authorization_from(credentials, request)
        )
        response.status_code = result.status_code
        return result

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
