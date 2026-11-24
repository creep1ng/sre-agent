"""Principals: who may call the platform, and whether they may still do so."""

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
    LIMIT_PARAMETER,
    authorization_from,
    bearer_credentials,
    errors,
    unknown_query,
)
from sre_agent.gate.pipeline import Admission, Released
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import Principal
from sre_agent.persistence.repositories import (
    PrincipalRepository,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, is_identifier

LIST = CONTROL[("GET", "/v1/principals")]
GET = CONTROL[("GET", "/v1/principals/{id}")]


class PrincipalListResponse(BaseModel):
    items: list[Principal]
    limit: int
    truncated: bool


def public_principal(principal: Principal) -> dict[str, Any]:
    return principal.model_dump(mode="json")


class Principals:
    """List and read principals."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

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


class PrincipalRoutes:
    """The principal routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.principals = Principals(sessions)
        control = ControlAudit(audit, projector)
        self.listing: ControlGate[int] = ControlGate(sessions, control, LIST)
        self.reading: ControlGate[str] = ControlGate(sessions, control, GET)

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


PrincipalId = Annotated[str, WithJsonSchema({"type": "string", "pattern": IDENTIFIER_PATTERN})]


def principals_router(routes: PrincipalRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()

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

    return router
