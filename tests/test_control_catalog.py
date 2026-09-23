"""Focused T6 RED evidence: catalog reads + creates for all 5 types (issue #184 T6).

DB-free by construction: validation, authorization-order, scope, router, DTO,
and contract-schema assertions only. Stateful behavior is proven by acceptance.
"""

import asyncio
import json
from pathlib import Path
from typing import get_args
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sre_agent.control.scopes import CONTROL_SCOPES
from sre_agent.control.service import CONTROL_OPERATIONS, ControlService
from sre_agent.control.service import control_router as build_control_router
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDenialCause, AuthorizationEvaluation
from sre_agent.governance.dto import AuditEvent, PolicyDecision, Principal, PrincipalContext

CATALOG_SCOPE = ("administrative_control", "catalog")
LIST_ROUTE = ("GET", "/v1/catalog/resources")
READ_ROUTE = ("GET", "/v1/catalog/resources/{type}/{id}")
CREATE_ROUTE = ("POST", "/v1/catalog/resources")

CATALOG_BODY = {
    "resource_type": "mcp_server",
    "resource_id": "server-tools",
    "owner_id": "mcp-platform",
    "source": "mcp",
    "source_ref": "mcp-platform/server-tools",
    "status": "registered",
    "discoverability": {
        "display_name": "Tool server",
        "visibility": "private",
        "description": "Registered MCP tool server.",
        "tags": ["mcp", "tools"],
    },
}


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


def test_catalog_scopes_require_admin_catalog_governance() -> None:
    assert CONTROL_SCOPES[LIST_ROUTE] == ("admin.read", *CATALOG_SCOPE)
    assert CONTROL_SCOPES[READ_ROUTE] == ("admin.read", *CATALOG_SCOPE)
    assert CONTROL_SCOPES[CREATE_ROUTE] == ("admin.write", *CATALOG_SCOPE)


def test_catalog_operations_match_scopes() -> None:
    assert CONTROL_OPERATIONS[LIST_ROUTE][0] == "catalog.list"
    assert CONTROL_OPERATIONS[READ_ROUTE][0] == "catalog.read"
    assert CONTROL_OPERATIONS[CREATE_ROUTE][0] == "catalog.create"
    assert CONTROL_OPERATIONS[LIST_ROUTE][1:] == CONTROL_SCOPES[LIST_ROUTE]
    assert CONTROL_OPERATIONS[READ_ROUTE][1:] == CONTROL_SCOPES[READ_ROUTE]
    assert CONTROL_OPERATIONS[CREATE_ROUTE][1:] == CONTROL_SCOPES[CREATE_ROUTE]
    assert set(CONTROL_OPERATIONS) == set(CONTROL_SCOPES)


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in CATALOG_BODY.items() if k != "owner_id"},
        {k: v for k, v in CATALOG_BODY.items() if k != "discoverability"},
        {**CATALOG_BODY, "resource_type": "llm_model"},
        {**CATALOG_BODY, "resource_type": "unknown"},
        {**CATALOG_BODY, "source": "model_alias"},
        {**CATALOG_BODY, "source": "unknown"},
        {**CATALOG_BODY, "status": "active", "resource_type": "skill"},
        {**CATALOG_BODY, "secret": "sre_do_not_store"},
        {**CATALOG_BODY, "concrete_model": "openai/gpt-4o-mini"},
        {**CATALOG_BODY, "router": "openrouter"},
        {**CATALOG_BODY, "owner_id": "INVALID"},
        {
            **CATALOG_BODY,
            "discoverability": {**CATALOG_BODY["discoverability"], "visibility": "secret"},
        },
        {
            **CATALOG_BODY,
            "discoverability": {**CATALOG_BODY["discoverability"], "tags": ["BAD-TAG"]},
        },
    ],
)
def test_catalog_create_rejects_non_closed_bodies(body: dict) -> None:
    service = _service()

    async def run():
        return await service.create_catalog_resource(body, "Bearer sre_valid_key", "k" * 16)

    response = asyncio.run(run())
    assert response.status_code == 422
    assert json.loads(response.body)["error"]["code"] == "validation_error"


def test_catalog_create_requires_idempotency_key() -> None:
    service = _service()

    async def run():
        return await service.create_catalog_resource(CATALOG_BODY, "Bearer sre_valid_key", None)

    response = asyncio.run(run())
    assert response.status_code == 400


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
        ("100", {"unknown": "z"}),
        ("100", {"resource_type": "unknown"}),
        ("100", {"visibility": "secret"}),
        ("100", {"status": "unknown"}),
        ("100", {"owner_id": "INVALID"}),
    ],
)
def test_catalog_list_rejects_bad_limits_filters_and_unknown_params(
    limit: str, extra: dict
) -> None:
    service = _service()

    async def run():
        return await service.list_catalog_resources(
            "Bearer sre_valid_key",
            extra.get("resource_type"),
            extra.get("owner_id"),
            extra.get("status"),
            extra.get("visibility"),
            limit,
            {
                k: v
                for k, v in extra.items()
                if k not in {"resource_type", "owner_id", "status", "visibility", "limit"}
            },
        )

    response = asyncio.run(run())
    # Unknown pagination must 422; unknown resource_type/visibility/status/owner must 422
    assert response.status_code == 422


def test_catalog_read_rejects_malformed_identifiers() -> None:
    service = _service()
    service._authenticate = AsyncMock(return_value=_context())

    async def run():
        return await service.get_catalog_resource("unknown_type", "server-tools", "Bearer k")

    response = asyncio.run(run())
    assert response.status_code == 422


def test_catalog_reads_admit_incident_workflow(monkeypatch) -> None:
    from contextlib import asynccontextmanager

    import sre_agent.control.service as service_module
    from sre_agent.governance.dto import CatalogDiscoverability, ResourceCatalogEntry

    service = _service()
    context = _context()
    allowed = AuthorizationEvaluation(
        PolicyDecision(decision="allow", reason_code="grant_matched", policy_id="test-policy"),
        None,
    )

    async def governed_access(*_args: object, **_kwargs: object):
        return context, allowed

    monkeypatch.setattr(service_module, "authorize_governed_access", governed_access)
    service._authenticate = AsyncMock(return_value=context)
    service._authorize = AsyncMock(return_value=allowed)

    entry = ResourceCatalogEntry(
        resource_type="incident_workflow",
        resource_id="incident-response",
        owner_id="papiarcacamilo",
        source="incident_workflow",
        source_ref="incident-response@1.0.0",
        status="active",
        discoverability=CatalogDiscoverability(
            display_name="Incident response workflow",
            visibility="private",
            description="Stable governed incident workflow resource.",
            tags=["incident", "workflow"],
        ),
    )

    class Catalog:
        def __init__(self, _session: object) -> None:
            pass

        async def list(self, **_filters: object):
            return [entry], False

        async def get(self, resource_type: str, resource_id: str):
            assert (resource_type, resource_id) == ("incident_workflow", "incident-response")
            return entry

    monkeypatch.setattr(service_module, "CatalogRepository", Catalog)

    @asynccontextmanager
    async def sessions():
        yield object()

    service.sessions = sessions

    async def run():
        listed = await service.list_catalog_resources(
            "Bearer safe", "incident_workflow", None, "active", "private", "100", {}
        )
        read = await service.get_catalog_resource(
            "incident_workflow", "incident-response", "Bearer safe"
        )
        return listed, read

    listed, read = asyncio.run(run())
    assert listed.status_code == read.status_code == 200
    assert json.loads(listed.body)["items"][0]["resource_type"] == "incident_workflow"
    assert json.loads(read.body)["resource_id"] == "incident-response"


def test_catalog_denial_precedes_lookup(monkeypatch) -> None:
    import sre_agent.control.service as service_module

    for repository in ("CatalogRepository", "ModelAliasRepository"):
        monkeypatch.setattr(
            service_module,
            repository,
            type(
                "_T",
                (),
                {
                    "__init__": lambda self, *a, **k: (_ for _ in ()).throw(
                        AssertionError("target access must follow authorization")
                    )
                },
            ),
        )
    service = _service()
    service._authenticate = AsyncMock(return_value=_context())
    service._authorize = AsyncMock(return_value=_deny())

    async def denied_access(*_args: object, **_kwargs: object):
        return _context(), _deny()

    monkeypatch.setattr(service_module, "authorize_governed_access", denied_access)
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def sessions():
        yield object()

    service.sessions = sessions

    async def run_list():
        return await service.list_catalog_resources(
            "Bearer safe", None, None, None, None, "100", {}
        )

    async def run_read():
        return await service.get_catalog_resource("mcp_server", "server-tools", "Bearer safe")

    assert asyncio.run(run_list()).status_code == 403
    assert asyncio.run(run_read()).status_code == 403


def _stub_catalog_service():
    service = ControlService.__new__(ControlService)
    service.create_catalog_resource = AsyncMock(return_value=JSONResponse(CATALOG_BODY, 201))
    service.list_catalog_resources = AsyncMock(
        return_value=JSONResponse({"items": [], "limit": 100, "truncated": False}, 200)
    )
    service.get_catalog_resource = AsyncMock(return_value=JSONResponse(CATALOG_BODY, 200))
    return service


def test_router_exposes_catalog_routes() -> None:
    app = FastAPI()
    app.include_router(build_control_router(_stub_catalog_service()))
    routes = {(r.path, tuple(sorted(r.methods))) for r in app.routes if r.path.startswith("/v1/")}
    assert ("/v1/catalog/resources", ("GET",)) in routes or any(
        p == "/v1/catalog/resources" and "GET" in m for p, m in routes
    )
    assert ("/v1/catalog/resources/{resource_type}/{id}", ("GET",)) in routes
    assert any(p == "/v1/catalog/resources" and "POST" in m for p, m in routes)


def test_audit_event_dto_admits_catalog_operations() -> None:
    admitted = set(get_args(AuditEvent.model_fields["operation"].annotation))
    assert {"catalog.create", "catalog.list", "catalog.read"} <= admitted


def test_release_230_audit_schema_admits_catalog_authorization_success() -> None:
    schema_path = (
        Path(__file__).parents[1]
        / "schemas/releases/2.3.0/json-schema/domain/audit-event.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert {"catalog.create", "catalog.list", "catalog.read"} <= set(
        schema["properties"]["operation"]["enum"]
    )
