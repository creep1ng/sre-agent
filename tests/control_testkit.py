"""Builders shared by the database-free control-plane tests."""

from datetime import UTC, datetime

from sre_agent.control.service import ControlService
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext


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


def _service() -> ControlService:
    return ControlService(None, _Audit(), AuditProjector(b"x" * 32))
