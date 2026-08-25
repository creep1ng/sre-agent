"""FastAPI bearer authentication boundary."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Header, Request
from fastapi.responses import JSONResponse

from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.repositories import CredentialRepository


class AuthenticationFailed(Exception):
    """Secret-free authentication failure shared by every credential condition."""


async def authenticate_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> PrincipalContext:
    if authorization is None:
        raise AuthenticationFailed
    scheme, separator, key = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not is_api_key(key):
        raise AuthenticationFailed
    session_provider = request.app.state.session_provider
    async with session_provider() as session:
        context = await CredentialRepository(session).authenticate(key)
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
