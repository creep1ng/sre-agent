"""The one reading of a bearer credential, for every governed route."""

from typing import Annotated, Any

from fastapi import Header, Request

from sre_agent.gate.errors import AuthenticationFailed, InactivePrincipal
from sre_agent.governance.authorization import AuthorizationDecisionEngine, AuthorizationEvaluation
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import (
    CredentialRepository,
    GrantRepository,
    OwnerResourceFactReader,
)


def bearer_key(authorization: str | None) -> str | None:
    """The API key of an `Authorization: Bearer <key>` header, or None for anything else."""
    if not authorization:
        return None
    scheme, separator, key = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
        return None
    return key


async def principal_for(sessions: Any, authorization: str | None) -> PrincipalContext | None:
    """The active principal a valid credential names. An unknown, revoked or expired credential
    and an inactive principal all give None, so no route can tell them apart."""
    key = bearer_key(authorization)
    if key is None:
        return None
    async with sessions() as session:
        return await CredentialRepository(session).authenticate(key)


async def active_principal(sessions: Any, authorization: str | None) -> PrincipalContext | None:
    """As `principal_for`, but an inactive principal raises `InactivePrincipal`, so a route that
    audits can record the refusal; the answer is the same 401."""
    key = bearer_key(authorization)
    if key is None:
        return None
    async with sessions() as session:
        context = await CredentialRepository(session).resolve_authorization_context(key)
    if context is not None and context.principal.status != "active":
        raise InactivePrincipal
    return context


async def authenticate_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    """A FastAPI dependency for a route that needs only the authenticated principal."""
    context = await principal_for(request.app.state.session_provider, authorization)
    if context is None:
        raise AuthenticationFailed
    return context


async def authorize_governed_access(
    sessions: Any, authorization: str | None, action: str, resource_type: str, resource_id: str
) -> tuple[PrincipalContext, AuthorizationEvaluation]:
    """Authenticate (an inactive principal is not authenticated) and evaluate one scope against
    the owner rows, in one call: a gate's `admit` for a route that checks scope by scope."""
    context = await principal_for(sessions, authorization)
    if context is None:
        raise AuthenticationFailed
    async with sessions() as session:
        evaluation = await AuthorizationDecisionEngine(
            OwnerResourceFactReader(session), GrantRepository(session)
        ).evaluate(context.principal, action, resource_type, resource_id)
    return context, evaluation
