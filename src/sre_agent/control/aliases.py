"""Model aliases: the stable names agents call, each assigned to one concrete model and router."""

from typing import Annotated, Any

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
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
from sre_agent.governance.dto import ModelAlias
from sre_agent.persistence.repositories import (
    ModelAliasRepository,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, is_identifier

LIST = CONTROL[("GET", "/v1/model-aliases")]
GET = CONTROL[("GET", "/v1/model-aliases/{id}")]
CONCRETE_MODEL = r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$"
Tag = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9._-]*$")]


class ModelAliasListResponse(BaseModel):
    items: list[ModelAlias]
    limit: int
    truncated: bool


class Aliases:
    """List and read model aliases."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

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


def _identifier(value: str) -> str:
    if not is_identifier(value):
        raise INVALID
    return value


class AliasRoutes:
    """The alias routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.aliases = Aliases(sessions)
        control = ControlAudit(audit, projector)

        def gate(operation: Any) -> ControlGate[Any]:
            return ControlGate(sessions, control, operation, reason="grant_matched")

        self.listing, self.reading = gate(LIST), gate(GET)

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


AliasId = Annotated[str, WithJsonSchema({"type": "string", "pattern": IDENTIFIER_PATTERN})]


def aliases_router(routes: AliasRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

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

    return router
