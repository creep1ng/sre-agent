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
from sre_agent.triage.service import TriageError, TriageService

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
    "triage_declare": frozenset({"operation", "expected_version", "reason", "severity"}),
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
        allowed_keys = ALLOWED_KEYS.get(raw.get("operation")) if isinstance(raw, dict) else None
        if allowed_keys is None or set(raw) - allowed_keys:
            return self._error(request_id, 422, "validation_error")
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
                "actor": result.actor,
                "decided_at": result.decided_at,
            },
            status_code=result.http_status,
        )


def triage_router(service: TriageHttpService) -> APIRouter:
    router = APIRouter()

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
