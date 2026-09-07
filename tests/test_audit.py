import hmac  # noqa: I001
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sre_agent.governance.authorization import AuthorizationDenialCause
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext
from sre_agent.gateway.audit import AuditProjector


def test_audit_references_follow_adr_005_domain_separation() -> None:
    key = b"test-audit-key-not-for-production"
    reference = AuditProjector(key).reference("principal", "incident-harness")
    expected = hmac.digest(key, b"sre-audit-v1\0principal\0incident-harness", "sha256").hex()
    assert reference.digest == expected and "incident-harness" not in repr(reference)


@pytest.mark.parametrize("identifier", ("incident_id", "run_id", "task_id"))
def test_audit_projector_normalizes_identifier_correlation_keys(identifier: str) -> None:
    projector = AuditProjector(b"test-audit-key-not-for-production")
    event = projector.event(
        request_id=uuid4(),
        status=503,
        latency_ms=1,
        stage="audit",
        identifiers={identifier: "correlation-harness"},
    )

    correlation_ref = getattr(event.correlation, f"{identifier.removesuffix('_id')}_ref")

    assert correlation_ref == projector.reference(identifier, "correlation-harness")


def test_audit_projector_carries_the_exact_cause_only_for_authorization_denies() -> None:
    occurred_at = datetime(2026, 9, 3, tzinfo=UTC)
    context = PrincipalContext(
        principal=Principal(
            principal_id="incident-harness",
            kind="agent",
            display_name="Incident harness",
            status="active",
            created_at=occurred_at,
            updated_at=occurred_at,
        ),
        credential_id="credential-harness",
        authenticated_at=occurred_at,
    )

    event = AuditProjector(b"test-audit-key-not-for-production").event(
        request_id=uuid4(),
        status=403,
        latency_ms=1,
        stage="authorization",
        reason="no_matching_grant",
        context=context,
        alias="triage-agent",
        decision=PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None),
        authorization_denial_cause=AuthorizationDenialCause.RESOURCE_MISSING,
    )

    assert event.authorization_denial_cause == "resource_missing"
    assert event.reason_code == "no_matching_grant"
    assert event.policy_decision.model_dump() == {
        "decision": "deny",
        "reason_code": "no_matching_grant",
    }
