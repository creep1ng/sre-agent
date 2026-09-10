"""FastAPI bearer authentication boundary."""

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Header, Request
from fastapi.responses import JSONResponse

from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationEvaluation,
)
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import (
    CredentialRepository,
    GrantRepository,
    ResourceRepository,
)


class AuthenticationFailed(Exception):
    """Secret-free authentication failure shared by every credential condition."""


async def authenticate_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    context = await _authorization_context(request.app.state.session_provider, authorization)
    if context.principal.status != "active":
        raise AuthenticationFailed
    return context


async def authorize_governed_access(
    sessions: Any,
    authorization: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
) -> tuple[PrincipalContext, AuthorizationEvaluation]:
    """Authenticate a bearer credential and evaluate a server-owned governed scope."""
    context = await _authorization_context(sessions, authorization)
    async with sessions() as session:
        evaluation = await AuthorizationDecisionEngine(
            ResourceRepository(session), GrantRepository(session)
        ).evaluate(context.principal, action, resource_type, resource_id)
    return context, evaluation


async def _authorization_context(sessions: Any, authorization: str | None) -> PrincipalContext:
    scheme, separator, key = authorization.partition(" ") if authorization else ("", "", "")
    if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
        raise AuthenticationFailed
    async with sessions() as session:
        context = await CredentialRepository(session).resolve_authorization_context(key)
    if context is None:
        raise AuthenticationFailed
    return context


async def authentication_failed_handler(
    request: Request, error: AuthenticationFailed
) -> JSONResponse:
    del error
    supplied_request_id = request.headers.get("x-request-id")
    try:
        request_id = str(UUID(supplied_request_id)) if supplied_request_id else str(uuid4())
    except ValueError:
        request_id = str(uuid4())
    return JSONResponse(
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
        content={
            "error": {"code": "authentication_failed", "message": "Authentication failed."},
            "request_id": request_id,
            "retryable": False,
        },
    )
