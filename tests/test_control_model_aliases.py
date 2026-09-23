"""Focused T3 evidence: ModelAlias create and reads for issue #184.

DB-free by construction: validation, authorization-order, scope, router, DTO,
and contract-schema assertions only. Stateful behavior (replay, rollback,
ordering, audit persistence) is proven by the acceptance suite.
"""

import asyncio
import json
from pathlib import Path
from typing import get_args
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.control.service import (
    CONTROL_OPERATIONS,
    ControlService,
)
from sre_agent.control.service import (
    control_router as build_control_router,
)
from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import AuditEvent, PolicyDecision, Principal, PrincipalContext

ALIAS_BODY = {
    "model_alias_id": "t3-alias",
    "alias": "t3-alias",
    "concrete_model": "openai/gpt-4o-mini",
    "router": "openrouter",
    "inference_provider": "openai",
}

ALIAS_SCOPE = ("administrative_control", "model_aliases")


def _context() -> PrincipalContext:
    from datetime import UTC, datetime

    now = datetime(2026, 9, 17, tzinfo=UTC)
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


def _service() -> ControlService:
    return ControlService(None, _Audit(), AuditProjector(b"x" * 32))


def test_alias_create_rejects_non_openrouter_router_before_effects(monkeypatch) -> None:
    """Non-openrouter routers must fail closed-body validation pre-auth (422).

    Regression scope: router="direct" previously passed Pydantic and failed at
    DB CK ck_resources_llm_assignment, surfacing as 409 idempotency_conflict
    with audit reason status_conflict instead of 422 validation_error with
    audit reason contract_validation_failed.
    """
    from contextlib import asynccontextmanager

    from sqlalchemy.exc import IntegrityError

    import sre_agent.control.service as service_module
    from sre_agent.persistence.repositories import IdempotencyBinding

    touched: list[str] = []

    async def allowed(*_args: object):
        return _context(), AuthorizationEvaluation(
            PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="grant-admin"),
            None,
        )

    monkeypatch.setattr(service_module, "authorize_governed_access", allowed)

    class _Session:
        @asynccontextmanager
        async def begin(self):
            yield self

    class _Sessions:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *_args: object):
            return None

    class _ClaimingIdempotency:
        def __init__(self, _session: object) -> None:
            pass

        async def claim_or_replay(self, **kwargs: object):
            touched.append("idempotency")
            return IdempotencyBinding(outcome=kwargs["outcome"], replayed=False)

        async def set_response_payload(self, **_kwargs: object) -> None:
            touched.append("idempotency-payload")

    class _CkRejectingAliases:
        """Simulates DB CK ck_resources_llm_assignment for router != openrouter."""

        def __init__(self, _session: object) -> None:
            pass

        async def create(self, *_args: object):
            touched.append("alias")
            raise IntegrityError(
                "INSERT INTO resources", {}, Exception("ck_resources_llm_assignment")
            )

    monkeypatch.setattr(service_module, "IdempotencyRepository", _ClaimingIdempotency)
    monkeypatch.setattr(service_module, "ModelAliasRepository", _CkRejectingAliases)

    recorded: list = []

    class _RecordingAudit:
        async def append(self, event: object) -> object:
            recorded.append(event)
            return event

        async def append_in_transaction(self, event: object, _session: object) -> object:
            recorded.append(event)
            return event

    service = ControlService(lambda: _Sessions(), _RecordingAudit(), AuditProjector(b"x" * 32))
    body = {**ALIAS_BODY, "model_alias_id": "t3-direct", "alias": "t3-direct", "router": "direct"}

    async def run():
        return await service.create_alias(body, "Bearer sre_valid_key", "d" * 16)

    response = asyncio.run(run())
    payload = json.loads(response.body)
    assert response.status_code == 422
    assert payload["error"]["code"] == "validation_error"
    assert set(payload) == {"error", "request_id", "retryable"}
    assert touched == []
    assert len(recorded) == 1
    assert recorded[0].operation == "aliases.create"
    assert recorded[0].action == "admin.write"
    assert recorded[0].stage == "audit"
    assert recorded[0].reason_code == "contract_validation_failed"
    assert recorded[0].identity is None and recorded[0].resource is None


def test_alias_scopes_require_admin_model_aliases_governance() -> None:
    assert CONTROL_SCOPES[("POST", "/v1/model-aliases")] == (
        "admin.write",
        *ALIAS_SCOPE,
    )
    assert CONTROL_SCOPES[("GET", "/v1/model-aliases")] == ("admin.read", *ALIAS_SCOPE)
    assert CONTROL_SCOPES[("GET", "/v1/model-aliases/{id}")] == ("admin.read", *ALIAS_SCOPE)


def test_alias_operations_match_scopes() -> None:
    assert CONTROL_OPERATIONS[("POST", "/v1/model-aliases")][0] == "aliases.create"
    assert CONTROL_OPERATIONS[("GET", "/v1/model-aliases")][0] == "aliases.list"
    assert CONTROL_OPERATIONS[("GET", "/v1/model-aliases/{id}")][0] == "aliases.get"
    assert set(CONTROL_OPERATIONS) == set(CONTROL_SCOPES)


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in ALIAS_BODY.items() if k != "model_alias_id"},
        {**ALIAS_BODY, "status": "active"},
        {**ALIAS_BODY, "secret": "sre_do_not_store"},
        {**ALIAS_BODY, "api_key": "sre_do_not_store"},
        {**ALIAS_BODY, "routing": {"router": "openrouter"}},
        {**ALIAS_BODY, "provider": "openai"},
        {**ALIAS_BODY, "model": "openai/gpt-4o-mini"},
        {**ALIAS_BODY, "model_alias_id": "INVALID"},
        {**ALIAS_BODY, "alias": "has_underscore"},
        {**ALIAS_BODY, "concrete_model": "not-a-model-ref"},
        {**ALIAS_BODY, "router": ""},
        {**ALIAS_BODY, "inference_provider": ""},
    ],
)
def test_alias_create_rejects_non_closed_bodies(body: dict) -> None:
    service = _service()

    async def run():
        return await service.create_alias(body, "Bearer sre_valid_key", "k" * 16)

    response = asyncio.run(run())
    assert response.status_code == 422
    assert json.loads(response.body)["error"]["code"] == "validation_error"


def test_alias_create_requires_idempotency_key() -> None:
    service = _service()

    async def run():
        return await service.create_alias(ALIAS_BODY, "Bearer sre_valid_key", None)

    response = asyncio.run(run())
    assert response.status_code == 400
    assert json.loads(response.body)["error"]["code"] == "invalid_idempotency_key"


def test_alias_create_denial_precedes_target_access(monkeypatch) -> None:
    import sre_agent.control.service as service_module

    for repository in (
        "ModelAliasRepository",
        "GrantRepository",
        "IdempotencyRepository",
        "ResourceRepository",
    ):
        monkeypatch.setattr(service_module, repository, _TargetAccessed)
    context = _context()

    async def denied(*_args):
        return context, _deny()

    monkeypatch.setattr(service_module, "authorize_governed_access", denied)
    service = _service()

    async def run():
        return await service.create_alias(ALIAS_BODY, "Bearer safe-key", "k" * 16)

    response = asyncio.run(run())
    assert response.status_code == 403


def test_alias_create_rejects_unauthenticated_before_effects(monkeypatch) -> None:
    import sre_agent.control.service as service_module

    async def invalid(*_args):
        raise AuthenticationFailed

    monkeypatch.setattr(service_module, "authorize_governed_access", invalid)
    service = _service()

    async def run():
        return await service.create_alias(ALIAS_BODY, "Bearer bad-key", "k" * 16)

    response = asyncio.run(run())
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("limit", "extra"),
    [
        ("0", {}),
        ("101", {}),
        ("not-a-number", {}),
        ("100", {"cursor": "opaque"}),
        ("100", {"page": "2"}),
        ("100", {"offset": "5"}),
        ("100", {"continuation_token": "x"}),
        ("100", {"next": "y"}),
        ("100", {"unknown": "z"}),
    ],
)
def test_alias_list_rejects_bad_limits_and_unknown_params(limit: str, extra: dict) -> None:
    service = _service()

    async def run():
        return await service.list_aliases("Bearer sre_valid_key", limit, extra)

    response = asyncio.run(run())
    assert response.status_code == 422


def test_alias_list_denial_precedes_target_access(monkeypatch) -> None:
    import sre_agent.control.service as service_module

    monkeypatch.setattr(service_module, "ModelAliasRepository", _TargetAccessed)
    context = _context()

    async def denied(*_args):
        return context, _deny()

    monkeypatch.setattr(service_module, "authorize_governed_access", denied)
    service = _service()

    async def run():
        return await service.list_aliases("Bearer safe-key", "100", {})

    response = asyncio.run(run())
    assert response.status_code == 403


@pytest.mark.parametrize(
    "alias_id", ["INVALID", "ab", "has space", "upper-ok-but-long-" + "x" * 60]
)
def test_alias_get_rejects_malformed_identifiers(alias_id: str) -> None:
    service = _service()
    service._authenticate = AsyncMock(return_value=_context())

    async def run():
        return await service.get_alias(alias_id, "Bearer sre_valid_key")

    response = asyncio.run(run())
    assert response.status_code == 422


def test_alias_get_denial_precedes_lookup() -> None:
    from contextlib import asynccontextmanager

    service = _service()
    service._authenticate = AsyncMock(return_value=_context())
    service._authorize = AsyncMock(return_value=_deny())

    @asynccontextmanager
    async def sessions():
        yield object()

    service.sessions = sessions

    async def run():
        return await service.get_alias("t3-alias", "Bearer safe-key")

    response = asyncio.run(run())
    assert response.status_code == 403
    service._authorize.assert_awaited_once()


def test_alias_get_rejects_unauthenticated_before_lookup() -> None:
    service = _service()
    service._authenticate = AsyncMock(return_value=None)

    async def run():
        return await service.get_alias("t3-alias", "Bearer bad-key")

    response = asyncio.run(run())
    assert response.status_code == 401


def _stub_alias_service():
    service = ControlService.__new__(ControlService)
    created = JSONResponse({**ALIAS_BODY, "status": "active"}, 201)
    service.create_alias = AsyncMock(return_value=created)
    service.list_aliases = AsyncMock(
        return_value=JSONResponse({"items": [], "limit": 100, "truncated": False}, 200)
    )
    service.get_alias = AsyncMock(
        return_value=JSONResponse({**ALIAS_BODY, "status": "active"}, 200)
    )
    return service


def test_router_exposes_alias_create_and_reads() -> None:
    app = FastAPI()
    app.include_router(build_control_router(_stub_alias_service()))
    routes = {(r.path, tuple(sorted(r.methods))) for r in app.routes if r.path.startswith("/v1/")}

    assert ("/v1/model-aliases", ("GET", "POST")) in routes or (
        any(path == "/v1/model-aliases" and "POST" in methods for path, methods in routes)
        and ("/v1/model-aliases", ("GET",)) in routes
    )
    assert ("/v1/model-aliases/{alias_id}", ("GET",)) in routes

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return (
                await client.post(
                    "/v1/model-aliases", json=ALIAS_BODY, headers={"idempotency-key": "k" * 16}
                ),
                await client.get("/v1/model-aliases"),
                await client.get("/v1/model-aliases/t3-alias"),
            )

    created, listed, fetched = asyncio.run(exercise())
    assert (created.status_code, listed.status_code, fetched.status_code) == (201, 200, 200)


def test_alias_openapi_marks_idempotency_scope_and_closed_list() -> None:
    app = FastAPI()
    app.include_router(build_control_router(_stub_alias_service()))
    paths = app.openapi()["paths"]

    create = paths["/v1/model-aliases"]["post"]
    key = next(p for p in create["parameters"] if p["name"] == "Idempotency-Key")
    assert key["required"] is True
    closed = create["requestBody"]["content"]["application/json"]["schema"]
    assert closed["additionalProperties"] is False
    assert sorted(closed["required"]) == sorted(ALIAS_BODY)
    assert create["x-governed-scope"] == {
        "action": "admin.write",
        "resource_type": "administrative_control",
        "resource_id": "model_aliases",
    }

    listed = paths["/v1/model-aliases"]["get"]
    assert listed["x-governed-scope"] == {
        "action": "admin.read",
        "resource_type": "administrative_control",
        "resource_id": "model_aliases",
    }
    assert listed["x-forbidden-query-parameters"] == [
        "cursor",
        "page",
        "offset",
        "continuation_token",
        "next",
    ]
    limit = next(p for p in listed["parameters"] if p["name"] == "limit")
    assert limit["schema"] == {"type": "integer", "default": 100, "minimum": 1, "maximum": 100}

    fetched = paths["/v1/model-aliases/{alias_id}"]["get"]
    assert fetched["x-governed-scope"] == {
        "action": "admin.read",
        "resource_type": "administrative_control",
        "resource_id": "model_aliases",
    }


def test_audit_event_dto_admits_alias_operations() -> None:
    admitted = set(get_args(AuditEvent.model_fields["operation"].annotation))
    assert {"aliases.create", "aliases.list", "aliases.get"} <= admitted


def test_release_230_audit_schema_admits_alias_authorization_success() -> None:
    schema_path = (
        Path(__file__).parents[1]
        / "schemas/releases/2.3.0/json-schema/domain/audit-event.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert {"aliases.create", "aliases.list", "aliases.get"} <= set(
        schema["properties"]["operation"]["enum"]
    )
    fixture_path = (
        Path(__file__).parents[1]
        / "schemas/releases/2.3.0/fixtures/positive"
        / "control.audit.aliases-create-allow.positive.v2.3.0.fixture.json"
    )
    fixture = json.loads(fixture_path.read_text())
    assert fixture["target"] == "urn:sre-agent:schema:audit-event:2.3.0"
    assert fixture["data"]["operation"] == "aliases.create"
    assert fixture["data"]["stage"] == "authorization"
    assert fixture["data"]["outcome"] == "success"
    assert fixture["data"]["reason_code"] == "grant_matched"
