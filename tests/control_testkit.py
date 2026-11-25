"""Builders shared by the database-free control-plane tests."""

import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from sre_agent.gate.pipeline import Gate
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext
from sre_agent.persistence import repositories


def _context() -> PrincipalContext:
    now = datetime(2026, 9, 18, tzinfo=UTC)
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


def _deny() -> AuthorizationEvaluation:
    return AuthorizationEvaluation(
        PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None),
        AuthorizationDenialCause.GRANT_NOT_APPLICABLE,
    )


class _Audit:
    async def append(self, event: object) -> object:
        return event


class _TargetAccessed:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("target repository access must follow authorization")


def _refuse_repositories(monkeypatch, names, replacement=_TargetAccessed) -> None:
    """Replace each named repository in every control module that holds it, so a route cannot
    reach it through a helper module either; a name no control module holds fails the test."""
    for name in names:
        repository = getattr(repositories, name)
        holders = [
            module
            for module_name, module in tuple(sys.modules.items())
            if module_name.startswith("sre_agent.control")
            and getattr(module, name, None) is repository
        ]
        assert holders, f"no control module holds {name}"
        for module in holders:
            monkeypatch.setattr(module, name, replacement)


def _gate(monkeypatch, context, evaluation=None) -> AsyncMock:
    """Stub the gate: authenticate as `context` (None: unauthenticated) and answer every scope
    with `evaluation`; the returned mock records the scopes asked."""
    monkeypatch.setattr("sre_agent.gate.pipeline.active_principal", AsyncMock(return_value=context))
    authorize = AsyncMock(return_value=evaluation)
    monkeypatch.setattr(Gate, "authorize", authorize)
    return authorize


def _routes(routes_class, sessions=None):
    """A resource's routes on the gate, with an audit sink that accepts every event."""
    return routes_class(sessions, _Audit(), AuditProjector(b"x" * 32))
