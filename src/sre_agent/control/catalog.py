"""The resource catalog: what the platform's resources are, who owns them, and who can find them."""

import re
from typing import Annotated, Any

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from pydantic.json_schema import WithJsonSchema

from sre_agent.control.governed import (
    INVALID,
    NOT_FOUND,
    ControlAudit,
    ControlGate,
    page_limit,
)
from sre_agent.control.operations import CONTROL
from sre_agent.control.routing import (
    FORBIDDEN_QUERY,
    LIMIT_PARAMETER,
    authorization_from,
    bearer_credentials,
    errors,
    unknown_query,
)
from sre_agent.gate.pipeline import Admission, Released
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import ResourceCatalogEntry
from sre_agent.persistence.repositories import (
    CatalogRepository,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, is_identifier

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


class CatalogListResponse(BaseModel):
    items: list[ResourceCatalogEntry]
    limit: int
    truncated: bool


class Catalog:
    """List and read catalog resources."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def list(self, filters: dict[str, Any], limit: int) -> dict[str, Any]:
        async with self.sessions() as session:
            items, truncated = await CatalogRepository(session).list(**filters, limit=limit)
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "limit": limit,
            "truncated": truncated,
        }

    async def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        """An entry a caller may find: hidden and inactive ones read as missing."""
        async with self.sessions() as session:
            entry = await CatalogRepository(session).get(resource_type, resource_id)
        hidden = entry is None or entry.discoverability.visibility == "hidden"
        if hidden or entry.status == "inactive":
            raise NOT_FOUND
        return entry.model_dump(mode="json")


class CatalogRoutes:
    """The catalog routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.catalog = Catalog(sessions)
        control = ControlAudit(audit, projector)

        def gate(operation: Any) -> ControlGate[Any]:
            return ControlGate(sessions, control, operation, reason="grant_matched")

        self.listing, self.reading = gate(LIST), gate(READ)

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
