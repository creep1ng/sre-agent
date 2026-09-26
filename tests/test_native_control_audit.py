"""Native administrative terminal audit planning preserves current control parity."""

import asyncio
from datetime import UTC, datetime
from importlib import import_module
from time import monotonic
from uuid import uuid4

import pytest

from sre_agent.control.service import ControlService
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext


def _context() -> PrincipalContext:
    now = datetime(2026, 9, 22, tzinfo=UTC)
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


def test_native_plan_distinguishes_hidden_denial_and_authorized_target_miss() -> None:
    native = import_module("sre_agent._core")
    context = ("admin-human", "human", "active", "credential-admin-human")
    resource = ("administrative_control", "credentials")
    denial = native.project_control_audit(
        404,
        "authorization",
        "resource_unavailable",
        True,
        False,
        context,
        resource,
        ("deny", None),
        "grant_not_applicable",
    )
    assert denial["outcome"] == "denied"
    assert denial["reason"] == "no_matching_grant"
    assert denial["resource"]["resource_ref"] == ("resource", "administrative_control/credentials")
    assert denial["authorization_denial_cause"] == "grant_not_applicable"

    target_miss = native.project_control_audit(
        404,
        "authorization",
        "resource_not_found",
        True,
        False,
        context,
        resource,
        ("allow", "grant-admin"),
        None,
    )
    assert target_miss["outcome"] == "error"
    assert target_miss["reason"] == "resource_not_found"
    assert target_miss["policy_decision"]["grant_ref"] == ("grant", "grant-admin")


def test_native_plan_suppresses_non_authorization_subject_and_retries_500() -> None:
    native = import_module("sre_agent._core")
    projection = native.project_control_audit(
        422,
        "validation",
        "validation_error",
        True,
        False,
        ("admin-human", "human", "active", "credential-admin-human"),
        ("administrative_control", "credentials"),
        ("deny", None),
        "grant_not_applicable",
    )
    assert projection["stage"] == "audit"
    assert projection["identity"] is None
    assert projection["resource"] is None
    assert projection["policy_decision"] is None
    assert projection["reason"] == "contract_validation_failed"
    assert projection["authorization_denial_cause"] is None
    assert (
        native.project_control_audit(
            500,
            "authorization",
            "credential_issuance_failed",
            True,
            False,
            None,
            None,
            None,
            None,
        )["retryable"]
        is True
    )


def test_control_event_uses_native_plan_and_hmac_canonical_resource() -> None:
    projector = AuditProjector(b"test-audit-key-not-for-production")
    event = projector.control_event(
        uuid4(),
        200,
        1,
        "authorization",
        operation="credentials.list",
        action="admin.read",
        context=_context(),
        resource_ref=("administrative_control", "credentials"),
        decision=PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="g"),
    )
    assert event.resource.resource_ref == projector.reference(
        "resource", "administrative_control/credentials"
    )
    assert event.routing is None
    assert event.policy_decision.grant_ref == projector.reference("grant", "g")


def test_missing_allow_policy_still_fails_closed() -> None:
    class MissingPolicy:
        decision = "allow"
        reason_code = "grant_matched"
        policy_id = None

    with pytest.raises(ValueError, match="grant policy_id"):
        AuditProjector(b"test-audit-key-not-for-production").control_event(
            uuid4(),
            200,
            1,
            "authorization",
            operation="credentials.list",
            action="admin.read",
            context=_context(),
            resource_ref=("administrative_control", "credentials"),
            decision=MissingPolicy(),
        )


def test_finish_suppresses_public_result_after_audit_failure() -> None:
    class RejectingAudit:
        async def append(self, event: object) -> None:
            raise RuntimeError("sink rejected")

    service = ControlService(None, RejectingAudit(), AuditProjector(b"x" * 32))
    response = asyncio.run(
        service._finish(
            uuid4(),
            monotonic(),
            200,
            "authorization",
            "credentials.list",
            "admin.read",
            payload={"items": []},
            context=_context(),
            resource_ref=("administrative_control", "credentials"),
            decision=PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="g"),
        )
    )
    assert response.status_code == 503
    assert b"audit_unavailable" in response.body
    assert b'"retryable":true' in response.body


def test_finish_invokes_one_native_plan_for_success(monkeypatch: pytest.MonkeyPatch) -> None:
    native = import_module("sre_agent._core")
    original = native.project_control_audit
    calls: list[int] = []

    def counting_plan(*args: object) -> dict:
        calls.append(args[0])
        return original(*args)

    monkeypatch.setattr(native, "project_control_audit", counting_plan)

    class RecordingAudit:
        def __init__(self) -> None:
            self.events: list[object] = []

        async def append(self, event: object) -> None:
            self.events.append(event)

    audit = RecordingAudit()
    service = ControlService(None, audit, AuditProjector(b"x" * 32))
    response = asyncio.run(
        service._finish(
            uuid4(),
            monotonic(),
            200,
            "authorization",
            "credentials.list",
            "admin.read",
            payload={"items": []},
            context=_context(),
            resource_ref=("administrative_control", "credentials"),
            decision=PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="g"),
        )
    )
    assert response.status_code == 200
    assert calls == [200]
    assert len(audit.events) == 1


def test_non_authorization_stage_does_not_read_irrelevant_subject() -> None:
    class RecordingAudit:
        def __init__(self) -> None:
            self.events: list[object] = []

        async def append(self, event: object) -> None:
            self.events.append(event)

    audit = RecordingAudit()
    service = ControlService(None, audit, AuditProjector(b"x" * 32))
    response = asyncio.run(
        service._finish(
            uuid4(),
            monotonic(),
            422,
            "validation",
            "credentials.list",
            "admin.read",
            error_code="validation_error",
            context=object(),
            resource_ref=("administrative_control", "credentials"),
            decision=object(),
            authorization_denial_cause="grant_not_applicable",
        )
    )
    assert response.status_code == 422
    assert len(audit.events) == 1
    assert audit.events[0].stage == "audit"
    assert audit.events[0].identity is None


def test_persistent_native_failure_keeps_terminal_audit_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = import_module("sre_agent._core")
    calls: list[int] = []

    def unavailable(*args: object) -> dict:
        calls.append(args[0])
        raise RuntimeError("native plan unavailable")

    monkeypatch.setattr(native, "project_control_audit", unavailable)

    class RecordingAudit:
        def __init__(self) -> None:
            self.events: list[object] = []

        async def append(self, event: object) -> None:
            self.events.append(event)

    audit = RecordingAudit()
    service = ControlService(None, audit, AuditProjector(b"x" * 32))
    response = asyncio.run(
        service._finish(
            uuid4(),
            monotonic(),
            200,
            "audit",
            "credentials.list",
            "admin.read",
            payload={"items": []},
        )
    )
    assert response.status_code == 503
    assert b'"code":"audit_unavailable"' in response.body
    assert b'"retryable":true' in response.body
    assert calls == [200]
    assert audit.events == []


def test_duck_typed_allow_without_reason_code_is_not_accepted() -> None:
    class MissingReason:
        decision = "allow"
        policy_id = "grant-admin"

    with pytest.raises(AttributeError, match="reason_code"):
        AuditProjector(b"test-audit-key-not-for-production").control_event(
            uuid4(),
            200,
            1,
            "authorization",
            operation="credentials.list",
            action="admin.read",
            context=_context(),
            resource_ref=("administrative_control", "credentials"),
            decision=MissingReason(),
        )
