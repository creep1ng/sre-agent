"""Evidence for issue #147: administrative control-plane authorization scope."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator

from sre_agent.control import scopes
from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.control.service import (
    CONTROL_OPERATIONS,
    ControlService,
    _key_digest,
    _payload_sha256,
    _public_principal,
    control_router,
)
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import PolicyDecision, Principal, PrincipalContext, Resource


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


def test_finish_maps_terminal_attempts_to_valid_control_audit() -> None:
    import asyncio

    from sre_agent.control.service import ControlService
    from sre_agent.governance.dto import PolicyDecision

    projector = AuditProjector(b"x" * 32)
    appended: list = []

    class Audit:
        async def append(self, event):
            appended.append(event)
            return event

    service = ControlService.__new__(ControlService)
    service.projector = projector
    service.audit = Audit()

    async def run() -> None:
        allow = PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="g")
        deny = PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None)
        now = datetime(2026, 9, 4, tzinfo=UTC)
        context = type(
            "Context",
            (),
            {
                "principal": _principal(),
                "credential_id": "credential-admin-human",
                "authenticated_at": now,
            },
        )()
        ok_200 = await service._finish(
            uuid4(),
            0.0,
            200,
            "audit",
            "principals.list",
            "admin.read",
            payload={"items": []},
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=allow,
        )
        assert ok_200.status_code == 200
        denied_403 = await service._finish(
            uuid4(),
            0.0,
            403,
            "authorization",
            "principals.create",
            "admin.write",
            error_code="resource_unavailable",
            context=context,
            resource_ref=("administrative_control", "principals"),
            decision=deny,
            authorization_denial_cause="grant_not_applicable",
        )
        assert denied_403.status_code == 403

    asyncio.run(run())
    assert [event.stage for event in appended] == ["audit", "authorization"]
    assert appended[0].identity is None and appended[0].resource is None
    assert appended[0].reason_code is None
    assert appended[1].reason_code == "no_matching_grant"
    assert appended[1].authorization_denial_cause == "grant_not_applicable"


def _stub_service(monkey_result=None, status=201, payload=None):
    from sre_agent.control.service import ControlService

    service = ControlService.__new__(ControlService)
    service.create_principal = AsyncMock(
        return_value=JSONResponse(payload or _public_principal(_principal("new-human")), status)
    )
    service.list_principals = AsyncMock(
        return_value=JSONResponse({"items": [], "limit": 100, "truncated": False}, 200)
    )
    service.get_principal = AsyncMock(
        return_value=JSONResponse(_public_principal(_principal()), 200)
    )
    return service


def test_router_exposes_all_eight_control_routes() -> None:
    app = FastAPI()
    app.include_router(control_router(_stub_service()))
    routes = {(r.path, tuple(sorted(r.methods))) for r in app.routes if r.path.startswith("/v1/")}

    assert ("/v1/principals", ("GET",)) in routes
    assert ("/v1/principals/{principal_id}", ("GET",)) in routes
    assert any(path == "/v1/principals" and "POST" in methods for path, methods in routes)
    assert {path for path, _ in routes} == {
        "/v1/principals",
        "/v1/principals/{principal_id}",
        "/v1/principals/{principal_id}/status",
        "/v1/principals/{principal_id}/credentials",
        "/v1/credentials/{credential_id}",
        "/v1/credentials/{credential_id}/rotation",
    }

    async def exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return (
                await client.post(
                    "/v1/principals",
                    json={"principal_id": "new-human", "kind": "human", "display_name": "New"},
                    headers={"idempotency-key": "k" * 16},
                ),
                await client.get("/v1/principals/INVALID"),
                await client.get("/v1/principals?limit=101"),
            )

    created, bad_path, bad_query = asyncio.run(exercise())
    assert created.status_code in {201, 200}
    assert bad_path.status_code == 200
    assert bad_query.status_code == 200


def test_router_audits_invalid_inputs_with_contract_envelopes() -> None:
    from sre_agent.control.service import ControlService

    appended: list = []

    class Audit:
        async def append(self, event):
            appended.append(event)

    service = ControlService(None, Audit(), AuditProjector(b"x" * 32))
    app = FastAPI()
    app.include_router(control_router(service))

    async def exercise() -> tuple[httpx.Response, ...]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return (
                await client.post(
                    "/v1/principals",
                    json={"principal_id": "INVALID"},
                    headers={"idempotency-key": "k" * 16},
                ),
                await client.post(
                    "/v1/principals",
                    json={"principal_id": "valid-id", "kind": "human", "display_name": "Valid"},
                    headers={"idempotency-key": "short"},
                ),
                await client.get("/v1/principals?limit=101"),
                await client.get("/v1/principals/INVALID"),
            )

    cases = asyncio.run(exercise())

    assert [response.status_code for response in cases] == [422, 400, 422, 422]
    assert [response.json()["error"]["code"] for response in cases] == [
        "validation_error",
        "invalid_idempotency_key",
        "validation_error",
        "validation_error",
    ]
    assert len(appended) == 4
    assert all(event.stage == "audit" for event in appended)


def test_invalid_input_is_suppressed_when_audit_sink_rejects() -> None:
    from sre_agent.control.service import ControlService

    class RejectingAudit:
        async def append(self, event):
            raise RuntimeError("sink rejected")

    service = ControlService(None, RejectingAudit(), AuditProjector(b"x" * 32))
    app = FastAPI()
    app.include_router(control_router(service))

    async def exercise() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/v1/principals?limit=101")

    response = asyncio.run(exercise())
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "audit_unavailable",
        "message": "Audit unavailable.",
    }


def test_control_openapi_publishes_request_success_and_error_schemas() -> None:
    app = FastAPI()
    app.include_router(control_router(_stub_service()))
    paths = app.openapi()["paths"]

    create = paths["/v1/principals"]["post"]
    assert create["requestBody"]["content"]["application/json"]["schema"]
    idempotency = next(
        parameter for parameter in create["parameters"] if parameter["name"] == "Idempotency-Key"
    )
    assert idempotency["description"] == (
        "Client-owned request key, not configuration or a secret. Generate a fresh key per logical "
        "mutation; reuse it only to retry the identical payload. A different payload returns 409 "
        "idempotency_conflict."
    )
    assert idempotency["schema"] == {
        "type": "string",
        "minLength": 16,
        "maxLength": 128,
        "pattern": r"^[\x20-\x7E]{16,128}$",
    }
    for status in ("201", "400", "401", "403", "409", "422", "503"):
        assert create["responses"][status]["content"]["application/json"]["schema"]
    for operation in (
        paths["/v1/principals"]["get"],
        paths["/v1/principals/{principal_id}"]["get"],
    ):
        assert operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert operation["responses"]["422"]["content"]["application/json"]["schema"]
    limit = paths["/v1/principals"]["get"]["parameters"][0]
    assert limit["schema"] == {"type": "integer", "default": 100, "minimum": 1, "maximum": 100}
    principal_id = paths["/v1/principals/{principal_id}"]["get"]["parameters"][0]
    assert principal_id["schema"]["pattern"] == r"^[a-z][a-z0-9_-]{2,63}$"
    for operation, action in (
        (create, "admin.write"),
        (paths["/v1/principals"]["get"], "admin.read"),
        (paths["/v1/principals/{principal_id}"]["get"], "admin.read"),
    ):
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["x-governed-scope"] == {
            "action": action,
            "resource_type": "administrative_control",
            "resource_id": "principals",
        }


def test_control_openapi_error_responses_match_canonical_fixtures() -> None:
    release = Path(__file__).parents[1] / "schemas/releases/1.4.0"
    fixtures = {
        "positive": release
        / "fixtures/positive/shared.error-envelope.safe.positive.v1.4.0.fixture.json",
        "stack": release
        / "fixtures/negative/shared.error-envelope.stack.negative.v1.4.0.fixture.json",
        "authorization": release
        / "fixtures/negative/shared.error-envelope.authorization.negative.v1.4.0.fixture.json",
    }
    payloads = {name: json.loads(path.read_text())["data"] for name, path in fixtures.items()}

    app = FastAPI()
    app.include_router(control_router(_stub_service()))
    document = app.openapi()
    validator = Draft202012Validator(document)

    for path in document["paths"].values():
        for operation in path.values():
            for status, response in operation.get("responses", {}).items():
                if int(status) < 400:
                    continue
                schema = response["content"]["application/json"]["schema"]
                response_validator = validator.evolve(schema=schema)
                assert response_validator.is_valid(payloads["positive"])
                assert not response_validator.is_valid(payloads["stack"])
                assert not response_validator.is_valid(payloads["authorization"])


def test_principal_operations_use_shared_governed_authorization_before_effects(
    monkeypatch,
) -> None:
    class Session:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    class Audit:
        def __init__(self) -> None:
            self.events = []

        async def append(self, event) -> None:
            self.events.append(event)

    context = PrincipalContext(
        principal=_principal(),
        credential_id="credential-admin-human",
        authenticated_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    deny = AuthorizationEvaluation(
        PolicyDecision(decision="deny", reason_code="no_matching_grant", policy_id=None),
        AuthorizationDenialCause.GRANT_NOT_APPLICABLE,
    )
    allow = AuthorizationEvaluation(
        PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="grant-admin"),
        None,
    )
    audit = Audit()
    service = ControlService(lambda: Session(), audit, AuditProjector(b"x" * 32))
    effects = AsyncMock(return_value=None)
    monkeypatch.setattr("sre_agent.control.service.PrincipalRepository.create", effects)
    monkeypatch.setattr("sre_agent.control.service.PrincipalRepository.list", effects)
    monkeypatch.setattr("sre_agent.control.service.PrincipalRepository.get", effects)
    calls = []

    async def denied(*args):
        calls.append(args[2:])
        return context, deny

    monkeypatch.setattr("sre_agent.control.service.authorize_governed_access", denied)

    async def exercise_denials():
        return (
            await service.create_principal(
                {"principal_id": "new-human", "kind": "human", "display_name": "New"},
                "Bearer sre_valid_key",
                "k" * 16,
            ),
            await service.list_principals("Bearer sre_valid_key", "100", {}),
            await service.get_principal("missing-human", "Bearer sre_valid_key"),
        )

    denied_responses = asyncio.run(exercise_denials())
    assert [response.status_code for response in denied_responses] == [403, 403, 403]
    assert effects.await_count == 0
    assert calls == [
        ("admin.write", "administrative_control", "principals"),
        ("admin.read", "administrative_control", "principals"),
        ("admin.read", "administrative_control", "principals"),
    ]

    async def invalid(*_):
        raise AuthenticationFailed

    monkeypatch.setattr("sre_agent.control.service.authorize_governed_access", invalid)
    invalid_responses = asyncio.run(exercise_denials())
    assert [response.status_code for response in invalid_responses] == [401, 401, 401]
    assert effects.await_count == 0

    async def allowed(*_):
        return context, allow

    monkeypatch.setattr("sre_agent.control.service.authorize_governed_access", allowed)
    missing = asyncio.run(service.get_principal("missing-human", "Bearer sre_valid_key"))
    assert missing.status_code == 404
    assert effects.await_count == 1
    assert audit.events[-1].policy_decision is not None
    assert audit.events[-1].policy_decision.grant_ref is not None
