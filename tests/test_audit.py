import hmac  # noqa: I001
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from sre_agent.governance.authorization import AuthorizationDenialCause
from sre_agent.governance.dto import (
    AuditEvent,
    Consumption,
    PolicyDecision,
    Principal,
    PrincipalContext,
)
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


def skill_resolution_event(request_id: UUID | None = None) -> AuditEvent:
    occurred_at = datetime(2026, 9, 26, tzinfo=UTC)
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
    request_id = request_id or uuid4()

    event = AuditProjector(b"test-audit-key-not-for-production").control_event(
        request_id=request_id,
        status=200,
        latency_ms=1,
        stage="authorization",
        operation="skills.resolve",
        action="invoke",
        context=context,
        resource_ref=("skill", "incident-triage-demo@1.0.0"),
        decision=PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="grant-1"),
    )
    return event


def test_skill_resolution_audit_is_request_correlated_and_metadata_only() -> None:
    request_id = uuid4()
    event = skill_resolution_event(request_id)
    serialized = event.model_dump(mode="json")

    assert event.operation == "skills.resolve"
    assert event.correlation.request_id == request_id
    assert event.resource is not None and event.resource.resource_type == "skill"
    assert event.content_state == "absent" and event.redacted_content is None
    assert event.model_alias_ref is None and event.routing is None
    assert "incident-triage-demo@1.0.0" not in str(serialized)
    assert "instructions" not in serialized


NON_LLM_TYPES = ["skill", "administrative_control", "mcp_server", "mcp_tool"]


def non_llm_consumption_event(resource_type: str) -> AuditEvent:
    event = skill_resolution_event()
    # Deliberately bypass DTO construction to exercise the persistence boundary too.
    return event.model_copy(
        update={
            "resource": event.resource.model_copy(update={"resource_type": resource_type}),
            "consumption": Consumption(
                availability="partial",
                source="openrouter",
                input_tokens=1,
                output_tokens=None,
                total_tokens=None,
                billed_usd=None,
                currency=None,
                precision=None,
                pricing_context=None,
            ),
        }
    )


@pytest.mark.parametrize("resource_type", NON_LLM_TYPES)
def test_non_llm_audit_rejects_provider_consumption(resource_type: str) -> None:
    event = non_llm_consumption_event(resource_type)
    with pytest.raises(ValueError, match="non-LLM"):
        AuditEvent.model_validate(event.model_dump())
