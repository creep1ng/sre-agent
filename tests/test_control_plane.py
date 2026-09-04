"""Evidence for issue #147: administrative control-plane authorization scope."""

import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sre_agent.control import scopes
from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.control.service import (
    CONTROL_OPERATIONS,
    _key_digest,
    _payload_sha256,
    _public_principal,
    control_router,
)
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.dto import Principal, Resource


def _principal(principal_id: str = "admin-human") -> Principal:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    return Principal(
        principal_id=principal_id,
        kind="human",
        display_name="Admin",
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_administrative_control_is_a_governed_resource_type() -> None:
    resource = Resource.model_validate(
        {"resource_type": "administrative_control", "resource_id": "principals"}
    )

    assert resource.resource_type == "administrative_control"


def test_control_grant_actions_cover_read_and_write() -> None:
    from sre_agent.control.scopes import CONTROL_SCOPES

    assert CONTROL_SCOPES[("GET", "/v1/principals")] == (
        "admin.read",
        "administrative_control",
        "principals",
    )
    assert CONTROL_SCOPES[("POST", "/v1/principals")] == (
        "admin.write",
        "administrative_control",
        "principals",
    )
    assert CONTROL_SCOPES[("POST", "/v1/principals/{id}/credentials")] == (
        "admin.write",
        "administrative_control",
        "credentials",
    )
    assert CONTROL_SCOPES[("GET", "/v1/principals/{id}/credentials")] == (
        "admin.read",
        "administrative_control",
        "credentials",
    )
    assert CONTROL_SCOPES[("DELETE", "/v1/credentials/{id}")] == (
        "admin.write",
        "administrative_control",
        "credentials",
    )
    assert CONTROL_SCOPES[("POST", "/v1/credentials/{id}/rotation")] == (
        "admin.write",
        "administrative_control",
        "credentials",
    )


def test_control_scopes_cover_all_routes_exactly_once() -> None:
    assert set(CONTROL_SCOPES) == {
        ("POST", "/v1/principals"),
        ("GET", "/v1/principals"),
        ("GET", "/v1/principals/{id}"),
        ("PUT", "/v1/principals/{id}/status"),
        ("POST", "/v1/principals/{id}/credentials"),
        ("GET", "/v1/principals/{id}/credentials"),
        ("DELETE", "/v1/credentials/{id}"),
        ("POST", "/v1/credentials/{id}/rotation"),
    }
    assert len({*CONTROL_SCOPES.values()}) == 4
    assert scopes.CONTROL_SCOPES is CONTROL_SCOPES


def test_idempotency_hashing_is_stable_and_domain_separated() -> None:
    payload = {"principal_id": "new-human", "kind": "human", "display_name": "New"}
    assert (
        _payload_sha256(payload)
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert _key_digest("k" * 16) != _payload_sha256("k" * 16)


def test_public_principal_projection_never_carries_secrets() -> None:
    dumped = json.dumps(_public_principal(_principal()))

    assert _public_principal(_principal())["principal_id"] == "admin-human"
    assert "key_hash" not in dumped
    assert "sre_" not in dumped


def test_control_operations_match_scopes() -> None:
    assert set(CONTROL_OPERATIONS) == set(CONTROL_SCOPES)
    assert CONTROL_OPERATIONS[("POST", "/v1/principals")][0] == "principals.create"
    assert CONTROL_OPERATIONS[("PUT", "/v1/principals/{id}/status")][0] == (
        "principals.status.replace"
    )
    assert CONTROL_OPERATIONS[("POST", "/v1/credentials/{id}/rotation")][0] == (
        "credentials.rotate"
    )


def test_control_projector_rejects_llm_routing_evidence() -> None:
    from sre_agent.governance.dto import PolicyDecision

    projector = AuditProjector(b"x" * 32)
    now = datetime(2026, 9, 4, tzinfo=UTC)
    context = {
        "principal": _principal(),
        "credential_id": "credential-admin-human",
        "authenticated_at": now,
    }
    event = projector.control_event(
        uuid4(),
        201,
        3,
        "authorization",
        operation="principals.create",
        action="admin.write",
        context=type("Context", (), context)(),
        resource_ref=("administrative_control", "principals"),
        decision=PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="g"),
    )

    assert event.policy_decision is not None
    assert event.model_alias_ref is None
    assert event.routing is None

    class BadDecision:
        decision = "allow"
        reason_code = "grant_matched"
        policy_id = None

    try:
        projector.control_event(
            uuid4(),
            201,
            3,
            "authorization",
            operation="principals.create",
            action="admin.write",
            context=type("Context", (), context)(),
            resource_ref=("administrative_control", "principals"),
            decision=BadDecision(),
        )
    except ValueError as error:
        assert "grant policy_id" in str(error)
    else:
        raise AssertionError("allow without grant must fail")


def _stub_service(monkey_result=None, status=201, payload=None):
    from sre_agent.control.service import ControlService

    service = ControlService.__new__(ControlService)
    service.create_principal = AsyncMock(
        return_value=type(
            "Response",
            (),
            {"status_code": status, "body": payload or {"ok": True}},
        )()
    )
    service.list_principals = AsyncMock(
        return_value=type("Response", (), {"status_code": 200, "body": {"items": []}})()
    )
    service.get_principal = AsyncMock(
        return_value=type("Response", (), {"status_code": 200, "body": {"ok": True}})()
    )
    return service


def test_router_exposes_three_typed_principals_routes() -> None:
    app = FastAPI()
    app.include_router(control_router(_stub_service()))
    routes = {(r.path, tuple(sorted(r.methods))) for r in app.routes if r.path.startswith("/v1/")}

    assert ("/v1/principals", ("GET",)) in routes
    assert ("/v1/principals/{principal_id}", ("GET",)) in routes
    assert any(path == "/v1/principals" and "POST" in methods for path, methods in routes)
    assert "/v1/principals/{principal_id}/status" not in {path for path, _ in routes}

    client = TestClient(app, raise_server_exceptions=False)
    created = client.post(
        "/v1/principals",
        json={"principal_id": "new-human", "kind": "human", "display_name": "New"},
        headers={"idempotency-key": "k" * 16},
    )
    assert created.status_code in {201, 200}
    bad_path = client.get("/v1/principals/INVALID")
    assert bad_path.status_code in {404, 422}
    bad_query = client.get("/v1/principals?limit=101")
    assert bad_query.status_code == 422
