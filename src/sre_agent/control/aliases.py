"""Model aliases: the stable names agents call, each assigned to one concrete model and router."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
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
    page_limit,
    payload_sha256,
    unaudited,
)
from sre_agent.control.operations import CONTROL
from sre_agent.control.routing import (
    FORBIDDEN_QUERY,
    LIMIT_PARAMETER,
    authorization_from,
    bearer_credentials,
    errors,
    idempotency_key_parameter,
    raw_json,
    request_body,
    unknown_query,
)
from sre_agent.gate.pipeline import Admission, Released
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import CatalogVisibility, ModelAlias, PrincipalContext
from sre_agent.persistence.repositories import (
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
    ModelAliasRepository,
    StaleWriteError,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, Identifier, is_identifier

CREATE = CONTROL[("POST", "/v1/model-aliases")]
LIST = CONTROL[("GET", "/v1/model-aliases")]
GET = CONTROL[("GET", "/v1/model-aliases/{id}")]
ASSIGNMENT = CONTROL[("PUT", "/v1/model-aliases/{id}/assignment")]
STATUS = CONTROL[("PUT", "/v1/model-aliases/{id}/status")]
CONCRETE_MODEL = r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$"
Tag = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9._-]*$")]


class ModelAliasCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model_alias_id: Identifier
    alias: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    concrete_model: Annotated[str, Field(pattern=CONCRETE_MODEL)]
    router: Literal["openrouter"]
    inference_provider: Annotated[str, Field(min_length=1, max_length=100)]
    # Additive ADMIN-authoritative catalog projection for llm_model. All
    # optional so pre-T6 creates keep working; `_catalog_projection` decides
    # what an absent one is.
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
    visibility: CatalogVisibility | None = None
    description: Annotated[str, Field(max_length=500)] | None = None
    tags: Annotated[list[Tag], Field(max_length=16)] | None = None


class ModelAliasListResponse(BaseModel):
    items: list[ModelAlias]
    limit: int
    truncated: bool


class ModelAliasAssignment(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    concrete_model: Annotated[str, Field(pattern=CONCRETE_MODEL)]
    router: Literal["openrouter"]
    inference_provider: Annotated[str, Field(min_length=1, max_length=100)]
    expected_updated_at: AwareDatetime


class ActiveInactiveStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    status: Literal["active", "inactive"]
    expected_updated_at: AwareDatetime


def _catalog_projection(body: ModelAliasCreate) -> dict[str, Any]:
    """The new alias's catalog fields: those the caller sent, and for the others the alias's
    own defaults: owned by and sourced from itself, named by its alias, private, with no
    description and no tags."""
    return {
        "owner_id": body.owner_id if body.owner_id is not None else body.model_alias_id,
        "source_ref": body.source_ref if body.source_ref is not None else body.model_alias_id,
        "display_name": body.display_name if body.display_name is not None else body.alias,
        "visibility": body.visibility if body.visibility is not None else "private",
        "description": body.description if body.description is not None else "",
        "tags": body.tags if body.tags is not None else [],
    }


class Aliases:
    """Create, list, read, reassign and (de)activate model aliases."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def create(
        self, caller: PrincipalContext, body: ModelAliasCreate, key: str, record: Record
    ) -> tuple[dict[str, Any], int, bool]:
        """The new alias, audited in its transaction; or the answer a replay of the same key and
        payload already got, unaudited (the last item says which)."""
        path = CREATE.path
        scope = f"{caller.principal.principal_id}|POST|{path}"
        try:
            async with self.sessions() as session, session.begin():
                idempotency = IdempotencyRepository(session)
                binding = await idempotency.claim_or_replay(
                    scope=scope,
                    key_digest=key_digest(key),
                    payload_sha256=payload_sha256(body.model_dump(mode="json")),
                    principal_id=caller.principal.principal_id,
                    method="POST",
                    canonical_path=path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=body.model_alias_id, replayed=False
                    ),
                )
                status = binding.outcome.response_status
                if binding.replayed:
                    return _stored(binding.outcome.response_payload, scope), status, True
                alias = await ModelAliasRepository(session).create(
                    body.model_alias_id,
                    body.alias,
                    body.concrete_model,
                    body.router,
                    body.inference_provider,
                    **_catalog_projection(body),
                )
                payload = alias.model_dump(mode="json")
                await idempotency.set_response_payload(
                    scope=scope, key_digest=key_digest(key), response_payload=payload
                )
                await record(session, status)
        except (IdempotencyConflictError, IntegrityError):
            raise IDEMPOTENCY_CONFLICT from None
        return payload, status, False

    async def list(self, limit: int) -> dict[str, Any]:
        async with self.sessions() as session:
            items, truncated = await ModelAliasRepository(session).list(limit=limit)
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "limit": limit,
            "truncated": truncated,
        }

    async def get(self, model_alias_id: str) -> dict[str, Any]:
        async with self.sessions() as session:
            alias = await ModelAliasRepository(session).get(model_alias_id)
        if alias is None:
            raise NOT_FOUND
        return alias.model_dump(mode="json")

    async def reassign(
        self, model_alias_id: str, body: ModelAliasAssignment, record: Record
    ) -> dict[str, Any]:
        """Assign another model; the answer, found or not, is audited in the same transaction."""
        return await self._replace(
            model_alias_id,
            record,
            lambda repository: repository.replace_assignment(
                model_alias_id,
                concrete_model=body.concrete_model,
                router=body.router,
                inference_provider=body.inference_provider,
                expected_updated_at=body.expected_updated_at,
            ),
        )

    async def replace_status(
        self, model_alias_id: str, body: ActiveInactiveStatus, record: Record
    ) -> dict[str, Any]:
        """(De)activate; the answer, found or not, is audited in the same transaction."""
        return await self._replace(
            model_alias_id,
            record,
            lambda repository: repository.replace_status(
                model_alias_id, body.status, expected_updated_at=body.expected_updated_at
            ),
        )

    async def _replace(self, model_alias_id: str, record: Record, change: Any) -> dict[str, Any]:
        async with self.sessions() as session, session.begin():
            try:
                alias = await change(ModelAliasRepository(session))
            except StaleWriteError:
                raise STATUS_CONFLICT from None
            if alias is None:
                await record(session, NOT_FOUND.status, NOT_FOUND.code)
            else:
                await record(session, 200)
        if alias is None:
            raise NOT_FOUND
        return alias.model_dump(mode="json")


def _stored(payload: Any, scope: str) -> dict[str, Any]:
    """The alias a replay answers, as it was stored; anything else is a conflict."""
    try:
        return ModelAlias.model_validate_json(canonical_payload(payload)).model_dump(mode="json")
    except ValidationError:
        raise IdempotencyConflictError(scope) from None


def _identifier(value: str) -> str:
    if not is_identifier(value):
        raise INVALID
    return value


def _body(model: type[BaseModel], raw: Any) -> Any:
    try:
        return model.model_validate_json(canonical_payload(raw))
    except (TypeError, ValidationError):
        raise INVALID from None


class AliasRoutes:
    """The alias routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.aliases = Aliases(sessions)
        control = ControlAudit(audit, projector)

        def gate(operation: Any) -> ControlGate[Any]:
            return ControlGate(sessions, control, operation, reason="grant_matched")

        self.creating, self.listing, self.reading = gate(CREATE), gate(LIST), gate(GET)
        self.reassigning, self.replacing = gate(ASSIGNMENT), gate(STATUS)

    async def create_alias(self, raw: Any, authorization: str | None, key: str | None) -> Response:
        def validate() -> tuple[ModelAliasCreate, str]:
            valid_key = idempotency_key(key)
            try:
                body = ModelAliasCreate.model_validate(raw)
            except ValidationError:
                raise INVALID from None
            if body.tags is not None and len(set(body.tags)) != len(body.tags):
                raise INVALID
            return body, valid_key

        async def create(admission: Admission, request: tuple[ModelAliasCreate, str]) -> Response:
            payload, status, replayed = await self.aliases.create(
                admission.context, *request, self.creating.record(admission)
            )
            if replayed:
                unaudited(admission, status)
            content = canonical_payload(payload)
            return Response(content, status_code=status, media_type="application/json")

        return await self.creating.run(authorization, create, validate)

    async def list_aliases(
        self, authorization: str | None, limit: Any, extra: dict[str, Any]
    ) -> Response:
        async def list_(_admission: Admission, valid_limit: int) -> Released:
            return Released(await self.aliases.list(valid_limit))

        return await self.listing.run(authorization, list_, lambda: page_limit(limit, extra))

    async def get_alias(self, model_alias_id: str, authorization: str | None) -> Response:
        async def get(_admission: Admission, valid_id: str) -> Released:
            return Released(await self.aliases.get(valid_id))

        return await self.reading.run(authorization, get, lambda: _identifier(model_alias_id))

    async def replace_alias_assignment(
        self, model_alias_id: str, raw: Any, authorization: str | None
    ) -> Response:
        def validate() -> ModelAliasAssignment:
            _identifier(model_alias_id)
            return _body(ModelAliasAssignment, raw)

        async def reassign(admission: Admission, body: ModelAliasAssignment) -> Released:
            record = self.reassigning.record(admission)
            return Released(await self.aliases.reassign(model_alias_id, body, record))

        return await self.reassigning.run(authorization, reassign, validate)

    async def replace_alias_status(
        self, model_alias_id: str, raw: Any, authorization: str | None
    ) -> Response:
        def validate() -> ActiveInactiveStatus:
            _identifier(model_alias_id)
            return _body(ActiveInactiveStatus, raw)

        async def replace(admission: Admission, body: ActiveInactiveStatus) -> Released:
            record = self.replacing.record(admission)
            return Released(await self.aliases.replace_status(model_alias_id, body, record))

        return await self.replacing.run(authorization, replace, validate)


AliasId = Annotated[str, WithJsonSchema({"type": "string", "pattern": IDENTIFIER_PATTERN})]


def aliases_router(routes: AliasRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

    @router.post(
        CREATE.route,
        status_code=201,
        response_model=ModelAlias,
        responses=errors(400, 401, 403, 409, 422, 503),
        openapi_extra={
            "parameters": [idempotency_key_parameter()],
            **request_body(ModelAliasCreate),
            **CREATE.openapi_extra,
        },
    )
    async def create_alias(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.create_alias(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )

    @router.get(
        LIST.route,
        response_model=ModelAliasListResponse,
        responses=errors(401, 403, 422, 503),
        openapi_extra={"parameters": [LIMIT_PARAMETER], **FORBIDDEN_QUERY, **LIST.openapi_extra},
    )
    async def list_aliases(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.list_aliases(
            authorization_from(credentials, request),
            request.query_params.get("limit", "100"),
            unknown_query(request, "limit"),
        )

    @router.get(
        GET.route,
        response_model=ModelAlias,
        responses=errors(401, 403, 404, 422, 503),
        openapi_extra=GET.openapi_extra,
    )
    async def get_alias(
        alias_id: AliasId,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.get_alias(alias_id, authorization_from(credentials, request))

    @router.put(
        ASSIGNMENT.route,
        response_model=ModelAlias,
        responses=errors(401, 403, 404, 409, 422, 503),
        openapi_extra={**request_body(ModelAliasAssignment), **ASSIGNMENT.openapi_extra},
    )
    async def replace_alias_assignment(
        alias_id: AliasId,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.replace_alias_assignment(
            alias_id, await raw_json(request), authorization_from(credentials, request)
        )

    @router.put(
        STATUS.route,
        response_model=ModelAlias,
        responses=errors(401, 403, 404, 409, 422, 503),
        openapi_extra={**request_body(ActiveInactiveStatus), **STATUS.openapi_extra},
    )
    async def replace_alias_status(
        alias_id: AliasId,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.replace_alias_status(
            alias_id, await raw_json(request), authorization_from(credentials, request)
        )

    return router
