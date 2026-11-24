"""Grants: which principal may take which action on which resource."""

from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from sre_agent.control.governed import (
    INVALID,
    NOT_FOUND,
    ControlAudit,
    ControlGate,
    Record,
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
from sre_agent.governance.dto import Grant
from sre_agent.persistence.repositories import (
    GrantRepository,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, is_identifier

LIST = CONTROL[("GET", "/v1/grants")]
REVOKE = CONTROL[("DELETE", "/v1/grants/{id}")]


class GrantListResponse(BaseModel):
    items: list[Grant]
    limit: int
    truncated: bool


class Grants:
    """List and revoke grants."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def list(
        self, principal_id: str | None, resource_id: str | None, limit: int
    ) -> dict[str, Any]:
        async with self.sessions() as session:
            items, truncated = await GrantRepository(session).list_filtered(
                principal_id=principal_id, resource_id=resource_id, limit=limit
            )
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "limit": limit,
            "truncated": truncated,
        }

    async def revoke(self, grant_id: str, record: Record) -> None:
        """Revoke a grant; the answer, found or not, is audited in the same transaction."""
        async with self.sessions() as session, session.begin():
            grant = await GrantRepository(session).revoke(grant_id)
            if grant is None:
                await record(session, NOT_FOUND.status, NOT_FOUND.code)
            else:
                await record(session, 204)
        if grant is None:
            raise NOT_FOUND


class GrantRoutes:
    """The grant routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.grants = Grants(sessions)
        control = ControlAudit(audit, projector)
        matched = {"reason": "grant_matched"}
        self.listing: ControlGate[int] = ControlGate(sessions, control, LIST, **matched)
        self.revoking: ControlGate[str] = ControlGate(sessions, control, REVOKE, **matched)

    async def list_grants(
        self,
        authorization: str | None,
        principal_id: str | None,
        resource_id: str | None,
        limit: Any,
        extra: dict[str, Any],
    ) -> Response:
        def validate() -> int:
            valid_limit = page_limit(limit, extra)
            only = principal_id if principal_id is not None else resource_id
            if (principal_id is None) == (resource_id is None) or not is_identifier(only or ""):
                raise INVALID
            return valid_limit

        async def list_(_admission: Admission, valid_limit: int) -> Released:
            return Released(await self.grants.list(principal_id, resource_id, valid_limit))

        return await self.listing.run(authorization, list_, validate)

    async def revoke_grant(self, grant_id: str, authorization: str | None) -> Response:
        def validate() -> str:
            if not is_identifier(grant_id):
                raise INVALID
            return grant_id

        async def revoke(admission: Admission, valid_id: str) -> Response:
            await self.grants.revoke(valid_id, self.revoking.record(admission))
            return Response(status_code=204)

        return await self.revoking.run(authorization, revoke, validate)


def grants_router(routes: GrantRoutes) -> APIRouter:
    router = APIRouter()
    credentials_of: Any = bearer_credentials()
    filter_parameter = {"in": "query", "required": False}
    identifier = {"schema": {"type": "string", "pattern": IDENTIFIER_PATTERN}}

    @router.get(
        LIST.route,
        response_model=GrantListResponse,
        responses=errors(401, 403, 422, 503),
        openapi_extra={
            "parameters": [
                {"name": "principal_id", **filter_parameter, **identifier},
                {"name": "resource_id", **filter_parameter, **identifier},
                LIMIT_PARAMETER,
            ],
            "x-required-query-any-of": ["principal_id", "resource_id"],
            **FORBIDDEN_QUERY,
            **LIST.openapi_extra,
        },
    )
    async def list_grants(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        params = request.query_params
        return await routes.list_grants(
            authorization_from(credentials, request),
            params.get("principal_id"),
            params.get("resource_id"),
            params.get("limit", "100"),
            unknown_query(request, "principal_id", "resource_id", "limit"),
        )

    @router.delete(REVOKE.route, status_code=204, responses=errors(401, 403, 404, 422, 503))
    async def revoke_grant(
        grant_id: str,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.revoke_grant(grant_id, authorization_from(credentials, request))

    return router
