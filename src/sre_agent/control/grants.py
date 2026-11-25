"""Grants: which principal may take which action on which resource."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, ValidationError
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
from sre_agent.gate.errors import GovernedError
from sre_agent.gate.pipeline import Admission, Released
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import TransactionalAuditStore
from sre_agent.governance.dto import Grant, PrincipalContext, Resource
from sre_agent.governance.resources import GRANT_ADMITTED_ACTIONS
from sre_agent.persistence.repositories import (
    GrantConflictError,
    GrantRepository,
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
    PrincipalRepository,
    ResourceRepository,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, Identifier, is_identifier

CREATE = CONTROL[("POST", "/v1/grants")]
LIST = CONTROL[("GET", "/v1/grants")]
REVOKE = CONTROL[("DELETE", "/v1/grants/{id}")]
# A new grant that repeats an existing one is named for what it repeats (#759).
CONFLICTS = {
    "grant_id": GovernedError(
        409, "grant_id_conflict", "A grant with this grant_id already exists, active or revoked."
    ),
    "active_grant": GovernedError(
        409,
        "grant_conflict",
        "An active grant with this principal, action and resource already exists.",
    ),
}


class GrantCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    grant_id: Identifier
    principal_id: Identifier
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{1,63}$")]
    resource: Resource
    effect: Literal["allow"]


class GrantListResponse(BaseModel):
    items: list[Grant]
    limit: int
    truncated: bool


class Grants:
    """Create, list and revoke grants."""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions

    async def create(
        self, caller: PrincipalContext, body: GrantCreate, key: str, record: Record
    ) -> tuple[dict[str, Any], int, bool]:
        """The new grant, audited in its transaction; or the answer a replay of the same key and
        payload already got, unaudited (the last item says which)."""
        path = CREATE.path
        scope = f"{caller.principal.principal_id}|POST|{path}"
        payload_hash = payload_sha256(body.model_dump(mode="json"))
        try:
            async with self.sessions() as session, session.begin():
                idempotency = IdempotencyRepository(session)
                prior = await idempotency.peek(
                    scope=scope, key_digest=key_digest(key), payload_sha256=payload_hash
                )
                if prior is not None:
                    stored = _stored(prior.outcome.response_payload, scope)
                    return stored, prior.outcome.response_status, True
                await self._admit(session, body)
                binding = await idempotency.claim_or_replay(
                    scope=scope,
                    key_digest=key_digest(key),
                    payload_sha256=payload_hash,
                    principal_id=caller.principal.principal_id,
                    method="POST",
                    canonical_path=path,
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=201, resource_id=body.grant_id, replayed=False
                    ),
                )
                status = binding.outcome.response_status
                if binding.replayed:
                    return _stored(binding.outcome.response_payload, scope), status, True
                grant = await GrantRepository(session).create(
                    body.grant_id,
                    body.principal_id,
                    body.action,
                    body.resource.resource_type,
                    body.resource.resource_id,
                )
                payload = grant.model_dump(mode="json")
                await idempotency.set_response_payload(
                    scope=scope, key_digest=key_digest(key), response_payload=payload
                )
                await record(session, status)
        except GrantConflictError as conflict:
            raise CONFLICTS.get(conflict.repeats or "", IDEMPOTENCY_CONFLICT) from None
        except (IdempotencyConflictError, IntegrityError):
            raise IDEMPOTENCY_CONFLICT from None
        return payload, status, False

    async def _admit(self, session: Any, body: GrantCreate) -> None:
        """An active principal, an active resource and an action its contract admits."""
        principal = await PrincipalRepository(session).get(body.principal_id)
        if principal is None or principal.status != "active":
            raise NOT_FOUND
        resource = body.resource
        fact = await ResourceRepository(session).authorization_view(
            resource.resource_type, resource.resource_id
        )
        if fact is None or fact.status != "active":
            raise NOT_FOUND
        if body.action not in GRANT_ADMITTED_ACTIONS.get(resource.resource_type, frozenset()):
            raise INVALID

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


def _stored(payload: Any, scope: str) -> dict[str, Any]:
    """The grant a replay answers, as it was stored; anything else is a conflict."""
    try:
        return Grant.model_validate_json(canonical_payload(payload)).model_dump(mode="json")
    except ValidationError:
        raise IdempotencyConflictError(scope) from None


def _json(payload: Any, status: int) -> Response:
    return Response(canonical_payload(payload), status_code=status, media_type="application/json")


class GrantRoutes:
    """The grant routes on the gate: validate, then run the use case once authorized."""

    def __init__(
        self, sessions: Any, audit: TransactionalAuditStore, projector: AuditProjector
    ) -> None:
        self.grants = Grants(sessions)
        control = ControlAudit(audit, projector)
        matched = {"reason": "grant_matched"}
        self.creating: ControlGate[tuple[GrantCreate, str]] = ControlGate(
            sessions, control, CREATE, **matched
        )
        self.listing: ControlGate[int] = ControlGate(sessions, control, LIST, **matched)
        self.revoking: ControlGate[str] = ControlGate(sessions, control, REVOKE, **matched)

    async def create_grant(self, raw: Any, authorization: str | None, key: str | None) -> Response:
        def validate() -> tuple[GrantCreate, str]:
            valid_key = idempotency_key(key)
            try:
                return GrantCreate.model_validate(raw), valid_key
            except ValidationError:
                raise INVALID from None

        async def create(admission: Admission, request: tuple[GrantCreate, str]) -> Response:
            payload, status, replayed = await self.grants.create(
                admission.context, *request, self.creating.record(admission)
            )
            if replayed:
                unaudited(admission, status)
            return _json(payload, status)

        return await self.creating.run(authorization, create, validate)

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

    @router.post(
        CREATE.route,
        status_code=201,
        response_model=Grant,
        responses=errors(400, 401, 403, 404, 409, 422, 503),
        openapi_extra={
            "parameters": [idempotency_key_parameter()],
            **request_body(GrantCreate),
            **CREATE.openapi_extra,
        },
    )
    async def create_grant(
        request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_of
    ) -> Response:
        return await routes.create_grant(
            await raw_json(request),
            authorization_from(credentials, request),
            request.headers.get("idempotency-key"),
        )

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

    @router.delete(
        REVOKE.route,
        status_code=204,
        responses=errors(401, 403, 404, 422, 503),
        openapi_extra=REVOKE.openapi_extra,
    )
    async def revoke_grant(
        grant_id: str,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = credentials_of,
    ) -> Response:
        return await routes.revoke_grant(grant_id, authorization_from(credentials, request))

    return router
