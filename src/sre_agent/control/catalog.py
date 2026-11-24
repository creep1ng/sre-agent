"""The resource catalog: what the platform's resources are, who owns them, and who can find them."""

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.json_schema import WithJsonSchema
from sqlalchemy.exc import IntegrityError

from sre_agent.control.governed import (
    IDEMPOTENCY_CONFLICT,
    INVALID,
    NOT_FOUND,
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
from sre_agent.governance.dto import PrincipalContext, ResourceCatalogEntry
from sre_agent.persistence.repositories import (
    CatalogRepository,
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, Identifier, is_identifier

CREATE = CONTROL[("POST", "/v1/catalog/resources")]
LIST = CONTROL[("GET", "/v1/catalog/resources")]
READ = CONTROL[("GET", "/v1/catalog/resources/{type}/{id}")]
RESOURCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$"
RESOURCE_TYPES = {
    "llm_model",
    "mcp_server",
    "mcp_tool",
    "skill",
    "bok_collection",
    "incident_workflow",
    "service_operation",
}
STATUS_ORDER = ("registered", "draft", "published", "indexing", "active", "inactive", "revoked")
STATUSES = set(STATUS_ORDER)
VISIBILITIES = {"public", "private", "hidden"}
# The source each catalog-created type must name, and the states it may start in.
EXPECTED_SOURCE = {
    "mcp_server": "mcp",
    "mcp_tool": "mcp",
    "skill": "skill",
    "bok_collection": "bok",
    "incident_workflow": "incident_workflow",
    "service_operation": "deploy_executor",
}
ALLOWED_STATUS: dict[str, set[str]] = {
    "mcp_server": {"registered", "active", "inactive", "revoked"},
    "mcp_tool": {"registered", "active", "inactive", "revoked"},
    "skill": {"draft", "published", "active", "inactive", "revoked"},
    "bok_collection": {"draft", "indexing", "active", "inactive", "revoked"},
    "incident_workflow": {"active", "inactive"},
    "service_operation": {"active", "inactive"},
}
Tag = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9._-]*$")]
ResourceId = Annotated[str, Field(min_length=1, max_length=200, pattern=RESOURCE_ID_PATTERN)]


# What a caller never finds in a list, and reads as missing.
HIDDEN, INACTIVE = ("hidden",), ("inactive",)


class CatalogDiscoverabilityCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    visibility: Literal["public", "private", "hidden"]
    description: Annotated[str, Field(max_length=500)]
    tags: Annotated[list[Tag], Field(max_length=16)]


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
    resource_id: ResourceId
    owner_id: Identifier
    source: Literal["mcp", "skill", "bok", "incident_workflow", "deploy_executor"]
    source_ref: ResourceId
    status: Literal["registered", "draft", "published", "indexing", "active", "inactive", "revoked"]
    discoverability: CatalogDiscoverabilityCreate


class CatalogListResponse(BaseModel):
    items: list[ResourceCatalogEntry]
    limit: int
    truncated: bool


class Catalog:
    """Create, list and read catalog resources."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def create(
        self, caller: PrincipalContext, body: CatalogCreate, key: str, record: Record
    ) -> tuple[dict[str, Any], int, bool]:
        """The new entry, audited in its transaction; or the answer a replay of the same key and
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
                        response_status=201,
                        resource_id=f"{body.resource_type}/{body.resource_id}",
                        replayed=False,
                    ),
                )
                status = binding.outcome.response_status
                if binding.replayed:
                    return _stored(binding.outcome.response_payload, scope), status, True
                shown = body.discoverability
                entry = await CatalogRepository(session).create(
                    body.resource_type,
                    body.resource_id,
                    body.owner_id,
                    body.source,
                    body.source_ref,
                    body.status,
                    shown.display_name,
                    shown.visibility,
                    shown.description,
                    list(shown.tags),
                )
                payload = entry.model_dump(mode="json")
                await idempotency.set_response_payload(
                    scope=scope, key_digest=key_digest(key), response_payload=payload
                )
                await record(session, status)
        except (IdempotencyConflictError, IntegrityError):
            raise IDEMPOTENCY_CONFLICT from None
        return payload, status, False

    async def list(self, filters: dict[str, Any], limit: int) -> dict[str, Any]:
        """Hidden and inactive entries are never listed; revoked and other states are."""
        if filters["visibility"] in HIDDEN:
            return {"items": [], "limit": limit, "truncated": False}
        async with self.sessions() as session:
            items, truncated = await CatalogRepository(session).list(
                **filters, excluded_visibility=HIDDEN, excluded_status=INACTIVE, limit=limit
            )
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "limit": limit,
            "truncated": truncated,
        }

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """An entry a caller may find: hidden and inactive ones read as missing."""
        async with self.sessions() as session:
            entry = await CatalogRepository(session).get(resource_type, resource_id)
        hidden = entry is None or entry.discoverability.visibility in HIDDEN
        if hidden or entry.status in INACTIVE:
            raise NOT_FOUND
        return entry.model_dump(mode="json")


def _stored(payload: Any, scope: str) -> dict[str, Any]:
    """The entry a replay answers, as it was stored; anything else is a conflict."""
    try:
        stored = ResourceCatalogEntry.model_validate_json(canonical_payload(payload))
    except ValidationError:
        raise IdempotencyConflictError(scope) from None
    return stored.model_dump(mode="json")


def _created(raw: Any) -> CatalogCreate:
    """A closed create body whose tags are distinct, whose source fits its type and whose status
    the type may start in."""
    try:
        body = CatalogCreate.model_validate(raw)
    except ValidationError:
        raise INVALID from None
    tags = body.discoverability.tags
    if len(set(tags)) != len(tags) or body.source != EXPECTED_SOURCE[body.resource_type]:
        raise INVALID
    if body.status not in ALLOWED_STATUS[body.resource_type]:
        raise INVALID
    return body


class CatalogRoutes:
    """The catalog routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.catalog = Catalog(sessions)
        control = ControlAudit(audit, projector)

        def gate(operation: Any) -> ControlGate[Any]:
            return ControlGate(sessions, control, operation, reason="grant_matched")

        self.creating, self.listing, self.reading = gate(CREATE), gate(LIST), gate(READ)

    async def create_catalog_resource(
        self, raw: Any, authorization: str | None, key: str | None
    ) -> Response:
        def validate() -> tuple[CatalogCreate, str]:
            valid_key = idempotency_key(key)
            return _created(raw), valid_key

        async def create(admission: Admission, request: tuple[CatalogCreate, str]) -> Response:
            payload, status, replayed = await self.catalog.create(
                admission.context, *request, self.creating.record(admission)
            )
            if replayed:
                unaudited(admission, status)
            content = canonical_payload(payload)
            return Response(content, status_code=status, media_type="application/json")

        return await self.creating.run(authorization, create, validate)

    async def list_catalog_resources(
        self,
        authorization: str | None,
        resource_type: Any,
        owner_id: Any,
        status: Any,
        visibility: Any,
        limit: Any,
        extra: dict[str, Any],
    ) -> Response:
        filters = {
            "resource_type": resource_type,
            "owner_id": owner_id,
            "status": status,
            "visibility": visibility,
        }

        def validate() -> int:
            valid_limit = page_limit(limit, extra)
            if (
                (resource_type is not None and resource_type not in RESOURCE_TYPES)
                or (owner_id is not None and not is_identifier(owner_id))
                or (status is not None and status not in STATUSES)
                or (visibility is not None and visibility not in VISIBILITIES)
            ):
                raise INVALID
            return valid_limit

        async def list_(_admission: Admission, valid_limit: int) -> Released:
            return Released(await self.catalog.list(filters, valid_limit))

        return await self.listing.run(authorization, list_, validate)

    async def get_catalog_resource(
        self, resource_type: str, resource_id: str, authorization: str | None
    ) -> Response:
        def validate() -> None:
            if resource_type not in RESOURCE_TYPES or not re.match(
                RESOURCE_ID_PATTERN, resource_id
            ):
                raise INVALID

        async def read(_admission: Admission, _request: None) -> Released:
            return Released(await self.catalog.read(resource_type, resource_id))

        return await self.reading.run(authorization, read, validate)


# The documented filter and path enums name the five types an operator browses.
DOCUMENTED_TYPES = ["llm_model", "mcp_server", "mcp_tool", "skill", "bok_collection"]


def _query(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "in": "query", "required": False, "schema": schema}


def catalog_router(routes: CatalogRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

    @router.post(
        CREATE.route,
        status_code=201,
        response_model=ResourceCatalogEntry,
        responses=errors(400, 401, 403, 409, 422, 503),
        openapi_extra={
            "parameters": [idempotency_key_parameter()],
            **request_body(CatalogCreate),
            **CREATE.openapi_extra,
        },
    )
    async def create_catalog_resource(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.create_catalog_resource(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )

    @router.get(
        LIST.route,
        response_model=CatalogListResponse,
        responses=errors(401, 403, 422, 503),
        openapi_extra={
            "parameters": [
                _query("resource_type", {"enum": DOCUMENTED_TYPES}),
                _query("owner_id", {"type": "string", "pattern": IDENTIFIER_PATTERN}),
                _query("status", {"enum": list(STATUS_ORDER)}),
                _query("visibility", {"enum": ["public", "private", "hidden"]}),
                LIMIT_PARAMETER,
            ],
            **FORBIDDEN_QUERY,
            **LIST.openapi_extra,
        },
    )
    async def list_catalog_resources(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        params = request.query_params
        return await routes.list_catalog_resources(
            authorization_from(credentials, request),
            params.get("resource_type"),
            params.get("owner_id"),
            params.get("status"),
            params.get("visibility"),
            params.get("limit", "100"),
            unknown_query(request, "resource_type", "owner_id", "status", "visibility", "limit"),
        )

    @router.get(
        READ.route,
        response_model=ResourceCatalogEntry,
        responses=errors(401, 403, 404, 422, 503),
        openapi_extra=READ.openapi_extra,
    )
    async def get_catalog_resource(
        resource_type: Annotated[str, WithJsonSchema({"enum": DOCUMENTED_TYPES})],
        id: Annotated[
            str,
            WithJsonSchema(
                {"type": "string", "minLength": 1, "maxLength": 200, "pattern": RESOURCE_ID_PATTERN}
            ),
        ],
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.get_catalog_resource(
            resource_type, id, authorization_from(credentials, request)
        )

    return router
