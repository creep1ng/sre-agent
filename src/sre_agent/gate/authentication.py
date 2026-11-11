"""The one reading of a bearer credential, for every governed route."""

from typing import Annotated, Any

from fastapi import Header, Request

from sre_agent.gate.errors import AuthenticationFailed
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import CredentialRepository


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


async def authenticate_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    """A FastAPI dependency for a route that needs only the authenticated principal."""
    context = await principal_for(request.app.state.session_provider, authorization)
    if context is None:
        raise AuthenticationFailed
    return context
