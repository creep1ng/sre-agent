"""RED evidence for issue #147: administrative control-plane authorization scope."""

import hashlib
import json
from datetime import UTC, datetime

from sre_agent.control import scopes
from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.control.service import (
    _key_digest,
    _payload_sha256,
    _public_principal,
)
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
