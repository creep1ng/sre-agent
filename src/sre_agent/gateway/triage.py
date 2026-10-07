# ruff: noqa: E501, I001
"""Alert triage commands over HTTP (issue #23, chain C2b). Thin delegation."""

import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sre_agent.governance.dto import PrincipalContext
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository
from sre_agent.triage.service import ID_PATTERN, TriageError, TriageService

KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
RETRY_AFTER_SECONDS = "5"
MALFORMED = object()

# Closed command payloads mirrored from triage-command.schema.yaml (no new
# runtime dependency to load it here): unknown operations and extra keys are
# 422; required/type/value rules stay owned by the service.
ALLOWED_KEYS = {
    "open_triage": frozenset({"operation", "expected_version"}),
    "triage_dismiss": frozenset({"operation", "expected_version", "reason"}),
    "triage_link": frozenset({"operation", "expected_version", "reason", "target_incident_id"}),
    "triage_declare": frozenset({"operation", "expected_version", "reason", "severity", "impact"}),
}

MESSAGES = {
    400: "Malformed command envelope.",
    401: "Missing or invalid bearer credential.",
    403: "Authenticated without the command action.",
    404: "Unknown alert or target incident.",
    409: "Stale expected_version or duplicate declare.",
    422: "Closed payload or reason rule violated.",
    503: "Storage unavailable.",
}


class TriageHttpService:
    """HTTP boundary for triage commands; the service decides everything else."""

    def __init__(self, database: Database, workflow: IncidentWorkflow) -> None:
        self._database = database
        self._sessions = database.sessions
        self._service = TriageService(database, workflow)

    async def _authenticate(self, authorization: str | None) -> PrincipalContext | None:
        scheme, separator, key = authorization.partition(" ") if authorization else ("", "", "")
        if not separator or scheme.casefold() != "bearer" or not is_api_key(key):
            return None
        async with self._sessions() as session:
            return await CredentialRepository(session).authenticate(key)

    def _error(
        self,
        request_id: Any,
        status: int,
        code: str,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        response = JSONResponse(
            {
                "error": {"code": code, "message": MESSAGES[status]},
                "request_id": str(request_id),
                "retryable": status == 503,
            },
            status,
        )
        merged = dict(headers or {})
        if status == 503:
            merged.setdefault("Retry-After", RETRY_AFTER_SECONDS)
        for name, value in merged.items():
            response.headers[name] = value
        return response

    async def post_command(
        self, alert_id: str, raw: Any, authorization: str | None, idempotency_key: str | None
    ) -> JSONResponse:
        request_id = uuid4()
        if idempotency_key is None or re.fullmatch(KEY_PATTERN, idempotency_key) is None:
            return self._error(request_id, 400, "invalid_idempotency_key")
        if raw is MALFORMED:
            return self._error(request_id, 400, "invalid_command")
        operation = raw.get("operation") if isinstance(raw, dict) else None
        allowed_keys = ALLOWED_KEYS.get(operation) if isinstance(operation, str) else None
        if allowed_keys is None or set(raw) - allowed_keys:
            return self._error(request_id, 422, "validation_error")
        expected_version = raw.get("expected_version")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int):
            return self._error(request_id, 400, "invalid_command")
        for field in ("reason", "severity", "impact", "target_incident_id"):
            value = raw.get(field)
            if value is not None and not isinstance(value, str):
                return self._error(request_id, 400, "invalid_command")
        try:
            context = await self._authenticate(authorization)
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        if context is None:
            return self._error(
                request_id, 401, "authentication_failed", headers={"WWW-Authenticate": "Bearer"}
            )
        try:
            result = await self._service.execute(
                context.principal,
                alert_id=alert_id,
                operation=raw["operation"],
                expected_version=raw["expected_version"],
                reason=raw.get("reason"),
                severity=raw.get("severity"),
                impact=raw.get("impact"),
                target_incident_id=raw.get("target_incident_id"),
                idempotency_key=idempotency_key,
            )
        except TriageError as error:
            return self._error(request_id, error.http_status, error.code)
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        return JSONResponse(
            {
                "alert_id": alert_id,
                "status": result.status,
                "incident_id": result.incident_id,
                "expected_version": result.expected_version,
                "reason": raw.get("reason"),
                "actor": result.actor,
                "decided_at": result.decided_at,
            },
            status_code=result.http_status,
        )

    async def get_state(self, alert_id: str, authorization: str | None) -> JSONResponse:
        """Contract getAlertTriage: current triage state, no mutation."""
        request_id = uuid4()
        if not isinstance(alert_id, str) or re.fullmatch(ID_PATTERN, alert_id) is None:
            return self._error(request_id, 400, "invalid_command")
        try:
            context = await self._authenticate(authorization)
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        if context is None:
            return self._error(
                request_id, 401, "authentication_failed", headers={"WWW-Authenticate": "Bearer"}
            )
        try:
            read = await self._service.read_state(context.principal, alert_id=alert_id)
        except TriageError as error:
            return self._error(request_id, error.http_status, error.code)
        except Exception:
            return self._error(request_id, 503, "storage_unavailable")
        return JSONResponse(read, status_code=200)


def triage_router(service: TriageHttpService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/alerts/{alert_id}/triage")
    async def get_state(alert_id: str, request: Request) -> JSONResponse:
        return await service.get_state(alert_id, request.headers.get("authorization"))

    @router.post("/v1/alerts/{alert_id}/triage/commands")
    async def post_command(alert_id: str, request: Request) -> JSONResponse:
        try:
            raw = await request.json()
        except Exception:
            raw = MALFORMED
        return await service.post_command(
            alert_id,
            raw,
            request.headers.get("authorization"),
            request.headers.get("idempotency-key"),
        )

    return router
