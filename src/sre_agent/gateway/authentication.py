"""Authorization for routes that have not moved to the gate (`sre_agent.gate`) yet."""

from typing import Any

from sre_agent.gate.authentication import authenticate_principal, bearer_key
from sre_agent.gate.errors import AuthenticationFailed
from sre_agent.gate.errors import governed_error_handler as authentication_failed_handler
from sre_agent.governance.authorization import (
    AuthorizationDecisionEngine,
    AuthorizationEvaluation,
)
from sre_agent.governance.dto import PrincipalContext
from sre_agent.persistence.repositories import (
    CredentialRepository,
    GrantRepository,
    OwnerResourceFactReader,
)

__all__ = [
    "AuthenticationFailed",
    "authenticate_principal",
    "authentication_failed_handler",
    "authorize_governed_access",
    "authorize_governed_access_for_context",
]


async def authorize_governed_access(
    sessions: Any,
    authorization: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
) -> tuple[PrincipalContext, AuthorizationEvaluation]:
    """Authenticate a bearer credential and evaluate a server-owned governed scope."""
    context = await _authorization_context(sessions, authorization)
    evaluation = await authorize_governed_access_for_context(
        sessions, context, action, resource_type, resource_id
    )
    return context, evaluation


async def authorize_governed_access_for_context(
    sessions: Any,
    context: PrincipalContext,
    action: str,
    resource_type: str,
    resource_id: str,
) -> AuthorizationEvaluation:
    """Evaluate an additional scope for an already-authenticated request principal."""
    async with sessions() as session:
        evaluation = await AuthorizationDecisionEngine(
            OwnerResourceFactReader(session), GrantRepository(session)
        ).evaluate(context.principal, action, resource_type, resource_id)
    return evaluation


async def _authorization_context(sessions: Any, authorization: str | None) -> PrincipalContext:
    key = bearer_key(authorization)
    if key is None:
        raise AuthenticationFailed
    async with sessions() as session:
        context = await CredentialRepository(session).resolve_authorization_context(key)
    if context is None:
        raise AuthenticationFailed
    return context
