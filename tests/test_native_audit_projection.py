"""The native responses audit policy returns metadata-only reference plans."""

from importlib import import_module
from uuid import uuid4

import pytest
from pydantic import ValidationError

from sre_agent.gateway.audit import AuditProjector


def test_native_projection_keeps_hmac_domains_and_denial_semantics() -> None:
    native = import_module("sre_agent._core")
    projection = native.project_responses_audit(
        403,
        "no_matching_grant",
        ("principal-harness", "agent", "active", "credential-harness"),
        "triage-agent",
        ("deny", "no_matching_grant", None),
        None,
        [("incident_id", "incident-harness")],
    )

    assert projection["outcome"] == "denied"
    assert projection["correlation_refs"] == [("incident_ref", "incident_id", "incident-harness")]
    assert projection["identity"]["principal_ref"] == ("principal", "principal-harness")
    assert projection["resource"]["resource_ref"] == ("resource", "triage-agent")
    assert projection["model_alias_ref"] == ("model_alias", "triage-agent")
    assert projection["policy_decision"] == {
        "decision": "deny",
        "reason_code": "no_matching_grant",
    }
    assert projection["routing"] is None
    assert projection["content_state"] == "absent"


def test_native_projection_preserves_audit_unavailable_without_claiming_append() -> None:
    native = import_module("sre_agent._core")
    projection = native.project_responses_audit(
        503, "audit_unavailable", None, None, None, None, []
    )

    assert projection["outcome"] == "error"
    assert projection["authoritative_acceptance"] == "rejected"
    assert projection["ordinary_result"] == "suppressed"
    assert projection["exporter_result"] == "not_attempted"
    assert projection["identity"] is None


def test_native_projection_keeps_existing_routing_reference_domains() -> None:
    native = import_module("sre_agent._core")
    projection = native.project_responses_audit(
        200,
        None,
        None,
        "triage-agent",
        ("allow", "grant_matched", "grant-harness"),
        ("provider/model", "inference-partner"),
        [],
    )

    assert projection["outcome"] == "success"
    assert projection["identity"] is None
    assert projection["resource"] is None
    assert projection["policy_decision"]["grant_ref"] == ("grant", "grant-harness")
    assert projection["routing"] == {
        "model_ref": ("model", "provider/model"),
        "router": "openrouter",
        "provider_ref": ("provider", "inference-partner"),
    }


def test_python_adapter_resolves_native_plan_with_original_hmac_domain() -> None:
    projector = AuditProjector(b"test-audit-key-not-for-production")
    event = projector.event(
        request_id=uuid4(),
        status=503,
        latency_ms=1,
        stage="audit",
        identifiers={"run_id": "run-harness"},
    )

    assert event.correlation.run_ref == projector.reference("run_id", "run-harness")


@pytest.mark.parametrize("status", (-1, 70_000))
def test_python_dto_still_rejects_out_of_range_status(status: int) -> None:
    with pytest.raises(ValidationError):
        AuditProjector(b"test-audit-key-not-for-production").event(
            request_id=uuid4(),
            status=status,
            latency_ms=1,
            stage="validation",
            reason="contract_validation_failed",
        )


@pytest.mark.parametrize("status", (2**63, -(2**63) - 1))
def test_python_dto_rejects_status_beyond_native_integer_width(status: int) -> None:
    with pytest.raises(ValidationError):
        AuditProjector(b"test-audit-key-not-for-production").event(
            request_id=uuid4(),
            status=status,
            latency_ms=1,
            stage="validation",
            reason="contract_validation_failed",
        )
