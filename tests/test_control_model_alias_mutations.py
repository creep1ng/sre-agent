"""Focused T5 evidence: ModelAlias assignment/status CAS mutations for issue #184.

DB-free by construction: validation, authorization-order, scope, router, DTO,
and contract-schema assertions only. Stateful behavior (CAS 409, replay-safe
mutation, rollback, ordering, audit persistence) is proven by the acceptance
suite.
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
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import AuditEvent, PolicyDecision, Principal, PrincipalContext

EXPECTED_UPDATED_AT = "2026-09-18T00:00:00Z"
ASSIGNMENT_BODY = {
    "concrete_model": "openai/gpt-4o-mini",
    "router": "openrouter",
    "inference_provider": "openai",
    "expected_updated_at": EXPECTED_UPDATED_AT,
}
STATUS_BODY = {"status": "inactive", "expected_updated_at": EXPECTED_UPDATED_AT}

ALIAS_SCOPE = ("administrative_control", "model_aliases")
ASSIGNMENT_ROUTE = ("PUT", "/v1/model-aliases/{id}/assignment")
STATUS_ROUTE = ("PUT", "/v1/model-aliases/{id}/status")


def _context() -> PrincipalContext:
    from datetime import UTC, datetime

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


def test_alias_mutation_scopes_require_admin_write_model_aliases() -> None:
    assert CONTROL_SCOPES[ASSIGNMENT_ROUTE] == ("admin.write", *ALIAS_SCOPE)
    assert CONTROL_SCOPES[STATUS_ROUTE] == ("admin.write", *ALIAS_SCOPE)


def test_alias_mutation_operations_match_scopes() -> None:
    assert CONTROL_OPERATIONS[ASSIGNMENT_ROUTE][0] == "aliases.assignment.replace"
    assert CONTROL_OPERATIONS[STATUS_ROUTE][0] == "aliases.status.replace"
    assert CONTROL_OPERATIONS[ASSIGNMENT_ROUTE][1:] == CONTROL_SCOPES[ASSIGNMENT_ROUTE]
    assert CONTROL_OPERATIONS[STATUS_ROUTE][1:] == CONTROL_SCOPES[STATUS_ROUTE]
    assert set(CONTROL_OPERATIONS) == set(CONTROL_SCOPES)


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in ASSIGNMENT_BODY.items() if k != "expected_updated_at"},
        {**ASSIGNMENT_BODY, "status": "active"},
        {**ASSIGNMENT_BODY, "secret": "sre_do_not_store"},
        {**ASSIGNMENT_BODY, "api_key": "sre_do_not_store"},
        {**ASSIGNMENT_BODY, "alias": "t5-alias"},
        {**ASSIGNMENT_BODY, "model_alias_id": "t5-alias"},
        {**ASSIGNMENT_BODY, "routing": {"router": "openrouter"}},
        {**ASSIGNMENT_BODY, "provider": "openai"},
        {**ASSIGNMENT_BODY, "model": "openai/gpt-4o-mini"},
        {**ASSIGNMENT_BODY, "concrete_model": "not-a-model-ref"},
        {**ASSIGNMENT_BODY, "router": "direct"},
        {**ASSIGNMENT_BODY, "router": ""},
        {**ASSIGNMENT_BODY, "inference_provider": ""},
        {**ASSIGNMENT_BODY, "expected_updated_at": "not-a-datetime"},
        {**ASSIGNMENT_BODY, "expected_updated_at": "2026-09-18"},
    ],
)
def test_alias_assignment_rejects_non_closed_bodies(body: dict) -> None:
    service = _service()
    service._authenticate = AsyncMock(return_value=_context())

    async def run():
        return await service.replace_alias_assignment("t5-alias", body, "Bearer sre_valid_key")

    response = asyncio.run(run())
    assert response.status_code == 422
    assert json.loads(response.body)["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in STATUS_BODY.items() if k != "expected_updated_at"},
        {k: v for k, v in STATUS_BODY.items() if k != "status"},
        {**STATUS_BODY, "concrete_model": "openai/gpt-4o-mini"},
        {**STATUS_BODY, "router": "openrouter"},
        {**STATUS_BODY, "inference_provider": "openai"},
        {**STATUS_BODY, "secret": "sre_do_not_store"},
        {**STATUS_BODY, "status": "retired"},
        {**STATUS_BODY, "status": "active", "expected_updated_at": "not-a-datetime"},
    ],
)
def test_alias_status_rejects_non_closed_bodies(body: dict) -> None:
    service = _service()
    service._authenticate = AsyncMock(return_value=_context())

    async def run():
        return await service.replace_alias_status("t5-alias", body, "Bearer sre_valid_key")

    response = asyncio.run(run())
    assert response.status_code == 422
    assert json.loads(response.body)["error"]["code"] == "validation_error"


@pytest.mark.parametrize("method", ["replace_alias_assignment", "replace_alias_status"])
def test_alias_mutations_need_no_idempotency_key_but_require_closed_token(
    method: str,
) -> None:
    """PUT mutations are naturally idempotent like principal status replace.

    No Idempotency-Key is accepted; the expected_updated_at CAS token alone
    guards concurrent writers.
    """
    import inspect

    assert "idempotency" not in inspect.signature(getattr(ControlService, method)).parameters


@pytest.mark.parametrize(
    "alias_id", ["INVALID", "ab", "has space", "upper-ok-but-long-" + "x" * 60]
)
@pytest.mark.parametrize("method", ["replace_alias_assignment", "replace_alias_status"])
def test_alias_mutations_reject_malformed_identifiers(alias_id: str, method: str) -> None:
    service = _service()
    service._authenticate = AsyncMock(return_value=_context())
    body = ASSIGNMENT_BODY if method == "replace_alias_assignment" else STATUS_BODY

    async def run():
        return await getattr(service, method)(alias_id, body, "Bearer sre_valid_key")

    response = asyncio.run(run())
    assert response.status_code == 422


@pytest.mark.parametrize("method", ["replace_alias_assignment", "replace_alias_status"])
def test_alias_mutation_denial_precedes_lookup(method: str, monkeypatch) -> None:
    import sre_agent.control.service as service_module

    class _TargetAccessed:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("target repository access must follow authorization")

    monkeypatch.setattr(service_module, "ModelAliasRepository", _TargetAccessed)
    from contextlib import asynccontextmanager

    service = _service()
    service._authenticate = AsyncMock(return_value=_context())
    service._authorize = AsyncMock(return_value=_deny())
    body = ASSIGNMENT_BODY if method == "replace_alias_assignment" else STATUS_BODY

    @asynccontextmanager
    async def sessions():
        yield object()

    service.sessions = sessions

    async def run():
        return await getattr(service, method)("t5-alias", body, "Bearer safe-key")

    response = asyncio.run(run())
    assert response.status_code == 403
    service._authorize.assert_awaited_once()


@pytest.mark.parametrize("method", ["replace_alias_assignment", "replace_alias_status"])
def test_alias_mutations_reject_unauthenticated_before_lookup(method: str) -> None:
    service = _service()
    service._authenticate = AsyncMock(return_value=None)
    body = ASSIGNMENT_BODY if method == "replace_alias_assignment" else STATUS_BODY

    async def run():
        return await getattr(service, method)("t5-alias", body, "Bearer bad-key")

    response = asyncio.run(run())
    assert response.status_code == 401


def _stub_mutation_service():
    service = ControlService.__new__(ControlService)
    mutated = JSONResponse({**ASSIGNMENT_BODY, "model_alias_id": "t5-alias"}, 200)
    service.replace_alias_assignment = AsyncMock(return_value=mutated)
    service.replace_alias_status = AsyncMock(return_value=mutated)
    return service


def test_router_exposes_alias_assignment_and_status_replace() -> None:
    app = FastAPI()
    app.include_router(build_control_router(_stub_mutation_service()))
    routes = {(r.path, tuple(sorted(r.methods))) for r in app.routes if r.path.startswith("/v1/")}

    assert ("/v1/model-aliases/{alias_id}/assignment", ("PUT",)) in routes
    assert ("/v1/model-aliases/{alias_id}/status", ("PUT",)) in routes

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return (
                await client.put("/v1/model-aliases/t5-alias/assignment", json=ASSIGNMENT_BODY),
                await client.put("/v1/model-aliases/t5-alias/status", json=STATUS_BODY),
            )

    assignment, status = asyncio.run(exercise())
    assert (assignment.status_code, status.status_code) == (200, 200)


def test_alias_mutation_openapi_marks_closed_cas_bodies_without_idempotency_key() -> None:
    app = FastAPI()
    app.include_router(build_control_router(_stub_mutation_service()))
    paths = app.openapi()["paths"]

    for route, required in (
        (
            "/v1/model-aliases/{alias_id}/assignment",
            {
                "concrete_model",
                "router",
                "inference_provider",
                "expected_updated_at",
            },
        ),
        ("/v1/model-aliases/{alias_id}/status", {"status", "expected_updated_at"}),
    ):
        put = paths[route]["put"]
        assert all(p["name"] != "Idempotency-Key" for p in put.get("parameters", []))
        assert "409" in put["responses"]
        closed = put["requestBody"]["content"]["application/json"]["schema"]
        assert closed["additionalProperties"] is False
        assert set(closed["required"]) == required
        assert put["x-governed-scope"] == {
            "action": "admin.write",
            "resource_type": "administrative_control",
            "resource_id": "model_aliases",
        }


def test_audit_event_dto_admits_alias_mutation_operations() -> None:
    admitted = set(get_args(AuditEvent.model_fields["operation"].annotation))
    assert {"aliases.assignment.replace", "aliases.status.replace"} <= admitted


def test_release_230_audit_schema_admits_alias_mutation_authorization_success() -> None:
    schema_path = (
        Path(__file__).parents[1]
        / "schemas/releases/2.3.0/json-schema/domain/audit-event.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert {"aliases.assignment.replace", "aliases.status.replace"} <= set(
        schema["properties"]["operation"]["enum"]
    )
    for slug, operation in (
        ("aliases-assignment-replace-allow", "aliases.assignment.replace"),
        ("aliases-status-replace-allow", "aliases.status.replace"),
    ):
        fixture = json.loads(
            (
                Path(__file__).parents[1]
                / "schemas/releases/2.3.0/fixtures/positive"
                / f"control.audit.{slug}.positive.v2.3.0.fixture.json"
            ).read_text()
        )
        assert fixture["target"] == "urn:sre-agent:schema:audit-event:2.3.0"
        assert fixture["data"]["operation"] == operation
        assert fixture["data"]["stage"] == "authorization"
        assert fixture["data"]["outcome"] == "success"
        assert fixture["data"]["reason_code"] == "grant_matched"
