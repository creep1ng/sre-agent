"""Principals: who may call the platform, and whether they may still do so."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from pydantic.json_schema import WithJsonSchema

from sre_agent.control.governed import (
    IDEMPOTENCY_CONFLICT,
    INVALID,
    NOT_FOUND,
    STATUS_CONFLICT,
    ControlAudit,
    ControlGate,
    canonical_payload,
    idempotency_key,
    key_digest,
    page_limit,
    payload_sha256,
)
from sre_agent.control.operations import CONTROL
from sre_agent.control.routing import (
    LIMIT_PARAMETER,
    authorization_from,
    bearer_credentials,
    errors,
    idempotency_key_parameter,
    raw_json,
    request_body,
    unknown_query,
)
from sre_agent.gate.pipeline import Admission, Released, failing_as
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import Principal, PrincipalContext
from sre_agent.persistence.repositories import (
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
    PrincipalRepository,
    StaleWriteError,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, Identifier, is_identifier

CREATE = CONTROL[("POST", "/v1/principals")]
LIST = CONTROL[("GET", "/v1/principals")]
GET = CONTROL[("GET", "/v1/principals/{id}")]
STATUS = CONTROL[("PUT", "/v1/principals/{id}/status")]


class PrincipalCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    principal_id: Identifier
    kind: Annotated[str, Field(pattern=r"^(human|agent)$")]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]


class PrincipalListResponse(BaseModel):
    items: list[Principal]
    limit: int
    truncated: bool


class StatusReplace(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    status: Literal["active", "inactive"]
    expected_updated_at: AwareDatetime


def public_principal(principal: Principal) -> dict[str, Any]:
    return principal.model_dump(mode="json")


class Principals:
    """Create, list, read and (de)activate principals."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def create(
        self, caller: PrincipalContext, body: PrincipalCreate, key: str
    ) -> tuple[dict[str, Any] | None, int]:
        """The new principal, or the one a replay of the same key and payload created."""
        path = CREATE.path
        try:
            async with self.sessions() as session, session.begin():
                binding = await IdempotencyRepository(session).claim_or_replay(
                    scope=f"{caller.principal.principal_id}|POST|{path}",
                    key_digest=key_digest(key),
                    payload_sha256=payload_sha256(body.model_dump(mode="json")),
                    principal_id=caller.principal.principal_id,
                    method="POST",
                    canonical_path=path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=body.principal_id, replayed=False
                    ),
                )
                repository = PrincipalRepository(session)
                if binding.replayed:
                    principal = await repository.get(binding.outcome.resource_id)
                    replayed = public_principal(principal) if principal else None
                    return replayed, binding.outcome.response_status
                # Any failure to create it (an existing id) answers as a conflict.
                with failing_as(IDEMPOTENCY_CONFLICT):
                    principal = await repository.create(
                        body.principal_id, body.kind, body.display_name
                    )
        except IdempotencyConflictError:
            raise IDEMPOTENCY_CONFLICT from None
        return public_principal(principal), 201

    async def list(self, limit: int) -> dict[str, Any]:
        async with self.sessions() as session:
            items, truncated = await PrincipalRepository(session).list(limit=limit)
        return {
            "items": [public_principal(item) for item in items],
            "limit": limit,
            "truncated": truncated,
        }

    async def get(self, principal_id: str) -> dict[str, Any]:
        async with self.sessions() as session:
            principal = await PrincipalRepository(session).get(principal_id)
        if principal is None:
            raise NOT_FOUND
        return public_principal(principal)

    async def replace_status(self, principal_id: str, body: StatusReplace) -> dict[str, Any]:
        try:
            async with self.sessions() as session, session.begin():
                principal = await PrincipalRepository(session).replace_status(
                    principal_id, body.status, expected_updated_at=body.expected_updated_at
                )
        except StaleWriteError:
            raise STATUS_CONFLICT from None
        if principal is None:
            raise NOT_FOUND
        return public_principal(principal)


class PrincipalRoutes:
    """The principal routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.principals = Principals(sessions)
        control = ControlAudit(audit, projector)
        self.creating: ControlGate[tuple[PrincipalCreate, str]] = ControlGate(
            sessions, control, CREATE
        )
        self.listing: ControlGate[int] = ControlGate(sessions, control, LIST)
        self.reading: ControlGate[str] = ControlGate(sessions, control, GET)
        self.replacing: ControlGate[StatusReplace] = ControlGate(sessions, control, STATUS)

    async def create_principal(
        self, raw: Any, authorization: str | None, key: str | None
    ) -> Response:
        def validate() -> tuple[PrincipalCreate, str]:
            valid_key = idempotency_key(key)
            try:
                return PrincipalCreate.model_validate(raw), valid_key
            except ValidationError:
                raise INVALID from None

        async def create(admission: Admission, request: tuple[PrincipalCreate, str]) -> Released:
            payload, status = await self.principals.create(admission.context, *request)
            return Released(payload, status)

        return await self.creating.run(authorization, create, validate)

    async def list_principals(
        self, authorization: str | None, limit: Any, extra: dict[str, Any]
    ) -> Response:
        async def list_(_admission: Admission, valid_limit: int) -> Released:
            return Released(await self.principals.list(valid_limit))

        return await self.listing.run(authorization, list_, lambda: page_limit(limit, extra))

    async def get_principal(self, principal_id: str, authorization: str | None) -> Response:
        def validate() -> str:
            if not is_identifier(principal_id):
                raise INVALID
            return principal_id

        async def get(_admission: Admission, valid_id: str) -> Released:
            return Released(await self.principals.get(valid_id))

        return await self.reading.run(authorization, get, validate)

    async def replace_principal_status(
        self, principal_id: str, raw: Any, authorization: str | None
    ) -> Response:
        def validate() -> StatusReplace:
            if not is_identifier(principal_id):
                raise INVALID
            try:
                return StatusReplace.model_validate_json(canonical_payload(raw))
            except (TypeError, ValidationError):
                raise INVALID from None

        async def replace(_admission: Admission, body: StatusReplace) -> Released:
            return Released(await self.principals.replace_status(principal_id, body))

        return await self.replacing.run(authorization, replace, validate)


IDEMPOTENCY_KEY_DESCRIPTION = (
    "Client-owned request key, not configuration or a secret. Generate a fresh key per logical "
    "mutation; reuse it only to retry the identical payload. A different payload returns 409 "
    "idempotency_conflict."
)
PrincipalId = Annotated[str, WithJsonSchema({"type": "string", "pattern": IDENTIFIER_PATTERN})]


def principals_router(routes: PrincipalRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

    @router.post(
        CREATE.route,
        status_code=201,
        response_model=Principal,
        responses=errors(400, 401, 403, 409, 422, 503, described=True),
        openapi_extra={
            "parameters": [idempotency_key_parameter(IDEMPOTENCY_KEY_DESCRIPTION)],
            **request_body(PrincipalCreate),
            **CREATE.openapi_extra,
        },
    )
    async def create_principal(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.create_principal(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )

    @router.get(
        LIST.route,
        response_model=PrincipalListResponse,
        responses=errors(401, 403, 422, 503, described=True),
        openapi_extra={"parameters": [LIMIT_PARAMETER], **LIST.openapi_extra},
    )
    async def list_principals(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.list_principals(
            authorization_from(credentials, request),
            request.query_params.get("limit", "100"),
            unknown_query(request, "limit"),
        )

    @router.get(
        GET.route,
        response_model=Principal,
        responses=errors(401, 403, 404, 422, 503, described=True),
        openapi_extra=GET.openapi_extra,
    )
    async def get_principal(
        principal_id: PrincipalId,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.get_principal(principal_id, authorization_from(credentials, request))

    @router.put(
        STATUS.route,
        response_model=Principal,
        responses=errors(401, 403, 404, 409, 422, 503),
        openapi_extra=STATUS.openapi_extra,
    )
    async def replace_principal_status(
        principal_id: str,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.replace_principal_status(
            principal_id, await raw_json(request), authorization_from(credentials, request)
        )

    return router
