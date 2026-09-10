"""Authorization-order proof for every Issue #147 control operation."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock

import pytest

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.control.service import ControlService
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext


class _Audit:
    async def append(self, event: object) -> object:
        return event


class _TargetAccessed:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("target repository access must follow authorization")


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


@pytest.mark.parametrize(
    ("operation", "invoke", "expected_status"),
    [
        (
            ("POST", "/v1/principals"),
            lambda service: service.create_principal(
                {"principal_id": "target-human", "kind": "human", "display_name": "Target"},
                "Bearer safe-key",
                "create-target-human",
            ),
            403,
        ),
        (
            ("GET", "/v1/principals"),
            lambda service: service.list_principals("Bearer safe-key", "100", {}),
            403,
        ),
        (
            ("GET", "/v1/principals/{id}"),
            lambda service: service.get_principal("target-human", "Bearer safe-key"),
            403,
        ),
        (
            ("PUT", "/v1/principals/{id}/status"),
            lambda service: service.replace_principal_status(
                "target-human",
                {"status": "inactive", "expected_updated_at": "2026-09-07T00:00:00Z"},
                "Bearer safe-key",
            ),
            403,
        ),
        (
            ("POST", "/v1/principals/{id}/credentials"),
            lambda service: service.issue_credential(
                "target-human",
                {},
                "Bearer safe-key",
                "issue-target-human",
            ),
            403,
        ),
        (
            ("GET", "/v1/principals/{id}/credentials"),
            lambda service: service.list_credentials("target-human", "Bearer safe-key", "100", {}),
            404,
        ),
        (
            ("DELETE", "/v1/credentials/{id}"),
            lambda service: service.revoke_credential("credential-target-human", "Bearer safe-key"),
            403,
        ),
        (
            ("POST", "/v1/credentials/{id}/rotation"),
            lambda service: service.rotate_credential(
                "credential-target-human",
                {},
                "Bearer safe-key",
                "rotate-target-human",
            ),
            403,
        ),
    ],
)
def test_engine_denial_precedes_target_access_for_every_control_operation(
    monkeypatch: pytest.MonkeyPatch,
    operation: tuple[str, str],
    invoke: object,
    expected_status: int,
) -> None:
    """A denied control action cannot probe any target principal or credential."""
    import sre_agent.control.service as service_module

    for repository in (
        "PrincipalRepository",
        "CredentialRepository",
        "IdempotencyRepository",
    ):
        monkeypatch.setattr(service_module, repository, _TargetAccessed)

    service = ControlService.__new__(ControlService)
    service.audit = _Audit()
    service.projector = AuditProjector(b"x" * 32)
    service._authenticate = AsyncMock(return_value=_context())
    denied = AuthorizationEvaluation(
        decision=PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None),
        denial_cause=AuthorizationDenialCause.GRANT_NOT_APPLICABLE,
    )
    service._authorize = AsyncMock(return_value=denied)

    @asynccontextmanager
    async def sessions():
        yield object()

    service.sessions = sessions
    shared = AsyncMock(return_value=(_context(), denied))
    monkeypatch.setattr(service_module, "authorize_governed_access", shared)
    response = asyncio.run(invoke(service))

    assert response.status_code == expected_status
    action, resource_type, resource_id = CONTROL_SCOPES[operation]
    if operation in {
        ("POST", "/v1/principals"),
        ("GET", "/v1/principals"),
        ("GET", "/v1/principals/{id}"),
    }:
        shared.assert_awaited_once_with(
            service.sessions, "Bearer safe-key", action, resource_type, resource_id
        )
    else:
        service._authorize.assert_awaited_once_with(
            ANY,
            _context().principal,
            (action, resource_type, resource_id),
        )
