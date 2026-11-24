"""Authorization-order proof for every Issue #147 control operation."""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from control_testkit import _Audit, _TargetAccessed

from sre_agent.control.aliases import AliasRoutes
from sre_agent.control.catalog import CatalogRoutes
from sre_agent.control.credentials import CredentialRoutes
from sre_agent.control.grants import GrantRoutes
from sre_agent.control.operations import CONTROL_SCOPES
from sre_agent.control.principals import PrincipalRoutes
from sre_agent.gate.pipeline import Gate, Scope
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext

REPOSITORIES = (
    "PrincipalRepository",
    "CredentialRepository",
    "GrantRepository",
    "IdempotencyRepository",
    "ModelAliasRepository",
    "CatalogRepository",
)


def _context() -> PrincipalContext:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    return PrincipalContext(
        principal=Principal(
            principal_id="admin-human",
            kind="human",
            display_name="Admin",
            status="active",
            created_at=now,
            updated_at=now,
        ),
        credential_id="credential-admin-human",
        authenticated_at=now,
    )


# Every control operation is served on the gate by the routes of its resource module,
# authenticated and authorized by the gate (`active_principal`, `Gate.authorize`).
@pytest.mark.parametrize(
    ("routes_of", "operation", "invoke", "expected_status"),
    [
        (
            PrincipalRoutes,
            ("POST", "/v1/principals"),
            lambda routes: routes.create_principal(
                {"principal_id": "target-human", "kind": "human", "display_name": "Target"},
                "Bearer safe-key",
                "create-target-human",
            ),
            403,
        ),
        (
            PrincipalRoutes,
            ("GET", "/v1/principals"),
            lambda routes: routes.list_principals("Bearer safe-key", "100", {}),
            403,
        ),
        (
            PrincipalRoutes,
            ("GET", "/v1/principals/{id}"),
            lambda routes: routes.get_principal("target-human", "Bearer safe-key"),
            403,
        ),
        (
            PrincipalRoutes,
            ("PUT", "/v1/principals/{id}/status"),
            lambda routes: routes.replace_principal_status(
                "target-human",
                {"status": "inactive", "expected_updated_at": "2026-09-07T00:00:00Z"},
                "Bearer safe-key",
            ),
            403,
        ),
        (
            CredentialRoutes,
            ("POST", "/v1/principals/{id}/credentials"),
            lambda routes: routes.issue_credential(
                "target-human",
                {},
                "Bearer safe-key",
                "issue-target-human",
            ),
            403,
        ),
        (
            CredentialRoutes,
            ("GET", "/v1/principals/{id}/credentials"),
            lambda routes: routes.list_credentials("target-human", "Bearer safe-key", "100", {}),
            404,
        ),
        (
            CredentialRoutes,
            ("DELETE", "/v1/credentials/{id}"),
            lambda routes: routes.revoke_credential("credential-target-human", "Bearer safe-key"),
            403,
        ),
        (
            CredentialRoutes,
            ("POST", "/v1/credentials/{id}/rotation"),
            lambda routes: routes.rotate_credential(
                "credential-target-human",
                {},
                "Bearer safe-key",
                "rotate-target-human",
            ),
            403,
        ),
        (
            GrantRoutes,
            ("POST", "/v1/grants"),
            lambda routes: routes.create_grant(
                {
                    "grant_id": "grant-target-human",
                    "principal_id": "target-human",
                    "action": "invoke",
                    "resource": {"resource_type": "llm_model", "resource_id": "target-model"},
                    "effect": "allow",
                },
                "Bearer safe-key",
                "create-target-grant",
            ),
            403,
        ),
        (
            GrantRoutes,
            ("GET", "/v1/grants"),
            lambda routes: routes.list_grants("Bearer safe-key", "target-human", None, "100", {}),
            403,
        ),
        (
            GrantRoutes,
            ("DELETE", "/v1/grants/{id}"),
            lambda routes: routes.revoke_grant("grant-target-human", "Bearer safe-key"),
            403,
        ),
        (
            AliasRoutes,
            ("POST", "/v1/model-aliases"),
            lambda routes: routes.create_alias(
                {
                    "model_alias_id": "target-alias",
                    "alias": "target-alias",
                    "concrete_model": "openai/gpt-4o-mini",
                    "router": "openrouter",
                    "inference_provider": "openai",
                },
                "Bearer safe-key",
                "create-target-alias",
            ),
            403,
        ),
        (
            AliasRoutes,
            ("GET", "/v1/model-aliases"),
            lambda routes: routes.list_aliases("Bearer safe-key", "100", {}),
            403,
        ),
        (
            AliasRoutes,
            ("GET", "/v1/model-aliases/{id}"),
            lambda routes: routes.get_alias("target-alias", "Bearer safe-key"),
            403,
        ),
        (
            AliasRoutes,
            ("PUT", "/v1/model-aliases/{id}/assignment"),
            lambda routes: routes.replace_alias_assignment(
                "target-alias",
                {
                    "concrete_model": "openai/gpt-4o-mini",
                    "router": "openrouter",
                    "inference_provider": "openai",
                    "expected_updated_at": "2026-09-18T00:00:00Z",
                },
                "Bearer safe-key",
            ),
            403,
        ),
        (
            AliasRoutes,
            ("PUT", "/v1/model-aliases/{id}/status"),
            lambda routes: routes.replace_alias_status(
                "target-alias",
                {"status": "inactive", "expected_updated_at": "2026-09-18T00:00:00Z"},
                "Bearer safe-key",
            ),
            403,
        ),
        (
            CatalogRoutes,
            ("POST", "/v1/catalog/resources"),
            lambda routes: routes.create_catalog_resource(
                {
                    "resource_type": "mcp_server",
                    "resource_id": "server-tools",
                    "owner_id": "mcp-platform",
                    "source": "mcp",
                    "source_ref": "mcp-platform/server-tools",
                    "status": "registered",
                    "discoverability": {
                        "display_name": "Tool server",
                        "visibility": "private",
                        "description": "Registered MCP tool server.",
                        "tags": ["mcp"],
                    },
                },
                "Bearer safe-key",
                "create-target-catalog",
            ),
            403,
        ),
        (
            CatalogRoutes,
            ("GET", "/v1/catalog/resources"),
            lambda routes: routes.list_catalog_resources(
                "Bearer safe-key", None, None, None, None, "100", {}
            ),
            403,
        ),
        (
            CatalogRoutes,
            ("GET", "/v1/catalog/resources/{type}/{id}"),
            lambda routes: routes.get_catalog_resource(
                "mcp_server", "server-tools", "Bearer safe-key"
            ),
            403,
        ),
    ],
)
def test_engine_denial_precedes_target_access_for_every_control_operation(
    monkeypatch: pytest.MonkeyPatch,
    routes_of: type,
    operation: tuple[str, str],
    invoke: object,
    expected_status: int,
) -> None:
    """A denied control action cannot probe any target principal or credential."""
    module = sys.modules[routes_of.__module__]
    for repository in REPOSITORIES:
        if hasattr(module, repository):
            monkeypatch.setattr(module, repository, _TargetAccessed)
    monkeypatch.setattr(
        "sre_agent.gate.pipeline.active_principal", AsyncMock(return_value=_context())
    )
    denied = AuthorizationEvaluation(
        decision=PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None),
        denial_cause=AuthorizationDenialCause.GRANT_NOT_APPLICABLE,
    )
    authorize = AsyncMock(return_value=denied)
    monkeypatch.setattr(Gate, "authorize", authorize)

    @asynccontextmanager
    async def sessions():
        yield object()

    routes = routes_of(sessions, _Audit(), AuditProjector(b"x" * 32))
    response = asyncio.run(invoke(routes))

    assert response.status_code == expected_status
    authorize.assert_awaited_once_with(_context(), Scope(*CONTROL_SCOPES[operation]))
