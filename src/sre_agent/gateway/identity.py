"""Authenticated, non-cacheable current-principal projection."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from sre_agent.gateway.authentication import authenticate_principal
from sre_agent.governance.dto import PrincipalContext


class WhoAmIResponse(BaseModel):
    principal_id: str


router = APIRouter()
_bearer_docs = HTTPBearer(auto_error=False)


@router.get(
    "/v1/whoami",
    response_model=WhoAmIResponse,
    summary="Identify the principal authenticated by this bearer credential",
    description="Returns only the authenticated principal ID. The response is not cacheable.",
    responses={
        200: {
            "description": "The principal authenticated by the supplied bearer credential.",
            "headers": {
                "Cache-Control": {
                    "description": "Always no-store; principal identity must not be cached.",
                    "schema": {"type": "string", "const": "no-store"},
                }
            },
        },
        401: {"description": "Missing, invalid, revoked, expired, or inactive bearer credential."},
    },
)
async def who_am_i(
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_docs)],
    context: Annotated[PrincipalContext, Depends(authenticate_principal)],
) -> JSONResponse:
    return JSONResponse(
        content=WhoAmIResponse(principal_id=context.principal.principal_id).model_dump(),
        headers={"Cache-Control": "no-store"},
    )
