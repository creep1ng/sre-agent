import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from jsonschema import Draft202012Validator

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.responses import ResponsesService, responses_router


class RecordingAuditStore:
    def __init__(self) -> None:
        self.events = []

    async def append(self, event: object) -> None:
        self.events.append(event)


class FailingSessions:
    def __call__(self):
        return self

    async def __aenter__(self):
        raise RuntimeError("database secret must not escape")

    async def __aexit__(self, *_args: object) -> None:
        return None


class UnexpectedProvider:
    async def create(self, _request: object) -> None:
        raise AssertionError("provider must not be called")


class FailingAuditStore:
    async def append(self, _event: object) -> None:
        raise RuntimeError("audit database is unavailable")


class CancelledSessions(FailingSessions):
    async def __aenter__(self):
        raise asyncio.CancelledError


def application(sessions: object, audit: RecordingAuditStore) -> FastAPI:
    app = FastAPI()
    service = ResponsesService(
        sessions,
        UnexpectedProvider(),  # type: ignore[arg-type]
        audit,
        AuditProjector(b"test-audit-key"),
    )
    app.include_router(responses_router(service))
    return app


@pytest.mark.asyncio
async def test_session_exception_returns_safe_audited_error_envelope() -> None:
    audit = RecordingAuditStore()
    transport = httpx.ASGITransport(
        app=application(FailingSessions(), audit), raise_app_exceptions=False
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "triage-agent", "input": "incident"},
            headers={"Authorization": "Bearer sre_test_0123456789abcdefghijklmnop"},
        )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"] == {
        "code": "audit_unavailable",
        "message": "Audit unavailable.",
    }
    assert response.json()["retryable"] is True
    assert response.json()["request_id"] == str(audit.events[0].correlation.request_id)
    assert audit.events[0].stage == "audit"
    assert audit.events[0].authoritative_acceptance == "rejected"
    assert audit.events[0].ordinary_result == "suppressed"
    assert "database secret" not in response.text
    schema = json.loads(
        Path("schemas/releases/1.3.0/json-schema/domain/audit-event.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(
        audit.events[0].model_dump(mode="json", exclude_none=True)
    )


@pytest.mark.asyncio
async def test_invalid_utf8_returns_audited_contract_error_envelope() -> None:
    audit = RecordingAuditStore()
    transport = httpx.ASGITransport(app=application(FailingSessions(), audit))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            content=b'{"model":"triage-agent","input":"\xff"}',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "contract_validation_failed",
        "message": "Request validation failed.",
    }
    assert response.json()["request_id"] == str(audit.events[0].correlation.request_id)
    assert audit.events[0].stage == "validation"
    assert response.json()["retryable"] is False
    assert "detail" not in response.json()


@pytest.mark.asyncio
async def test_session_exception_does_not_claim_audit_when_audit_append_fails() -> None:
    transport = httpx.ASGITransport(
        app=application(FailingSessions(), FailingAuditStore()),  # type: ignore[arg-type]
        raise_app_exceptions=False,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "triage-agent", "input": "incident"},
            headers={"Authorization": "Bearer sre_test_0123456789abcdefghijklmnop"},
        )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "audit_unavailable",
        "message": "Audit unavailable.",
    }


@pytest.mark.asyncio
async def test_session_cancellation_is_not_normalized_as_an_error() -> None:
    audit = RecordingAuditStore()
    service = ResponsesService(
        CancelledSessions(),
        UnexpectedProvider(),  # type: ignore[arg-type]
        audit,
        AuditProjector(b"test-audit-key"),
    )

    with pytest.raises(asyncio.CancelledError):
        await service.create(
            {"model": "triage-agent", "input": "incident"},
            "Bearer sre_test_0123456789abcdefghijklmnop",
        )

    assert audit.events == []
