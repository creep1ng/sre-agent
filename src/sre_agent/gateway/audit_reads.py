"""Admin audit reads over the published 2.3.0 contract (issue #25, chain B2b)."""

import re
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import Principal, PrincipalContext
from sre_agent.persistence.api_keys import is_api_key
from sre_agent.persistence.models import AuditEventRow
from sre_agent.persistence.repositories import (
    AuditRepository,
    CredentialRepository,
    GrantRepository,
    ResourceRepository,
)

READ_ACTION = "admin.read"
RESOURCE_TYPE = "administrative_control"
RESOURCE_ID = "audit"
DEFAULT_LIMIT = 100
MAX_LIMIT = 100
FILTER_KEYS = (
    "principal_id decision model_alias_id request_id incident_id run_id task_id trace_id from to"
).split()
FORBIDDEN_PARAMS = (
    "cursor page offset continuation_token next content raw_content"
    " redacted_content include_content"
).split()
ID_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"

ERRORS = {
    401: ("authentication_failed", "Authentication is required."),
    403: ("resource_unavailable", "Resource unavailable."),
    404: ("resource_not_found", "The requested resource was not found."),
    422: ("validation_error", "Request validation failed."),
    503: ("audit_unavailable", "Audit storage is temporarily unavailable."),
}


def project_metadata(values: dict[str, Any]) -> dict[str, Any]:
    """The 2.3.0 metadata projection: the audit event without content.

    Drops redacted_content, the post-2.3.0 redaction.tool_schema_version
    marker, and the keys the 2.3.0 schema types as non-nullable objects.
    Nullable keys (reason_code, denial cause, consumption) are preserved.
    """
    projected = {key: value for key, value in values.items() if key != "redacted_content"}
    redaction = dict(projected.get("redaction") or {})
    redaction.pop("tool_schema_version", None)
    projected["redaction"] = redaction
    correlation = {
        key: value
        for key, value in dict(projected.get("correlation") or {}).items()
        if value is not None
    }
    projected["correlation"] = correlation
    decision = dict(projected.get("policy_decision") or {})
    decision.pop("policy_ref", None)
    if decision:
        projected["policy_decision"] = decision
    else:
        projected.pop("policy_decision", None)
    return {
        key: value
        for key, value in projected.items()
        if value is not None or key in ("reason_code", "authorization_denial_cause", "consumption")
    }


class AuditReadsService:
    def __init__(self, sessions: Any, hmac_key: bytes) -> None:
        self.sessions = sessions
        self._projector = AuditProjector(hmac_key)

    def _error(
        self, request_id: UUID, status: int, headers: dict[str, str] | None = None
    ) -> JSONResponse:
        code, message = ERRORS[status][0], ERRORS[status][1]
        response = JSONResponse(
            {
                "error": {"code": code, "message": message},
                "request_id": str(request_id),
                "retryable": status == 503,
            },
            status,
        )
        for name, value in dict(headers or {}).items():
            response.headers[name] = value
        return response

    async def _authenticate(self, authorization: str | None) -> PrincipalContext | None:
        scheme, sep, key = authorization.partition(" ") if authorization else ("", "", "")
        if not sep or scheme.casefold() != "bearer" or not is_api_key(key):
            return None
        async with self.sessions() as session:
            return await CredentialRepository(session).authenticate(key)

    async def _authorized(
        self,
        request_id: UUID,
        authorization: str | None,
    ) -> tuple[Principal | None, JSONResponse | None]:
        try:
            context = await self._authenticate(authorization)
            if context is None:
                return None, self._error(request_id, 401, headers={"WWW-Authenticate": "Bearer"})
            async with self.sessions() as session:
                evaluation = await AuthorizationDecisionEngine(
                    ResourceRepository(session), GrantRepository(session)
                ).evaluate(context.principal, READ_ACTION, RESOURCE_TYPE, RESOURCE_ID)
        except Exception:
            return None, self._error(request_id, 503)
        if evaluation.decision.decision != "allow":
            return None, self._error(request_id, 403)
        return context.principal, None

    def _digest(self, domain: str, value: str) -> str:
        return self._projector.reference(domain, value).digest

    def _filters(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if any(key in raw for key in FORBIDDEN_PARAMS):
            return None
        parsed: dict[str, Any] = {}
        if (value := raw.get("decision")) is not None:
            if value not in ("allow", "deny"):
                return None
            parsed["decision"] = value
        if (value := raw.get("request_id")) is not None:
            try:
                parsed["request_id"] = str(UUID(str(value)))
            except ValueError:
                return None
        if (value := raw.get("principal_id")) is not None:
            if not re.fullmatch(ID_PATTERN, str(value)):
                return None
            parsed["principal_digest"] = self._digest("principal", str(value))
        for key, domain in (
            ("model_alias_id", "model_alias"),
            ("incident_id", "incident_id"),
            ("run_id", "run_id"),
            ("task_id", "task_id"),
            ("trace_id", "trace_id"),
        ):
            if (value := raw.get(key)) is not None:
                if not isinstance(value, str) or not value:
                    return None
                parsed[f"{key[:-3]}_digest"] = self._digest(domain, value)
        start = end = None
        if raw.get("from") is not None:
            try:
                start = datetime.fromisoformat(raw["from"])
            except ValueError:
                return None
            if start.tzinfo is None:
                return None
        if raw.get("to") is not None:
            try:
                end = datetime.fromisoformat(raw["to"])
            except ValueError:
                return None
            if end.tzinfo is None:
                return None
        if start is not None and end is not None and not start < end:
            return None
        parsed["start"], parsed["end"] = start, end
        try:
            limit = int(raw["limit"]) if raw.get("limit") is not None else DEFAULT_LIMIT
        except (TypeError, ValueError):
            return None
        if not 1 <= limit <= MAX_LIMIT:
            return None
        parsed["limit"] = limit
        if not any(raw.get(key) is not None for key in FILTER_KEYS):
            return None
        return parsed

    async def list_events(self, raw: dict[str, Any], authorization: str | None) -> JSONResponse:
        request_id = uuid4()
        filters = self._filters(raw)
        if filters is None:
            return self._error(request_id, 422)
        _, error = await self._authorized(request_id, authorization)
        if error is not None:
            return error
        limit = filters.pop("limit")
        try:
            async with self.sessions() as session:
                events, has_more = await AuditRepository(session).query_filtered(
                    limit=limit, **filters
                )
        except Exception:
            return self._error(request_id, 503)
        return JSONResponse(
            {
                "items": [project_metadata(e.model_dump(mode="json")) for e in events],
                "limit": limit,
                "truncated": has_more,
            }
        )

    async def get_event(self, event_id: str, authorization: str | None) -> JSONResponse:
        request_id = uuid4()
        if not re.fullmatch(ID_PATTERN, event_id):
            return self._error(request_id, 422)
        _, error = await self._authorized(request_id, authorization)
        if error is not None:
            return error
        try:
            async with self.sessions() as session:
                row = await session.get(AuditEventRow, event_id)
                event = None
                if row is not None:
                    from sre_agent.persistence.projections import project_audit_event

                    event = project_audit_event(row)
        except Exception:
            return self._error(request_id, 503)
        if event is None:
            return self._error(request_id, 404)
        return JSONResponse(project_metadata(event.model_dump(mode="json")))


def audit_reads_router(service: AuditReadsService) -> APIRouter:
    router = APIRouter(tags=["Audit"])

    @router.get("/v1/audit-events")
    async def list_events(request: Request) -> JSONResponse:
        return await service.list_events(
            dict(request.query_params), request.headers.get("authorization")
        )

    @router.get("/v1/audit-events/{event_id}")
    async def get_event(event_id: str, request: Request) -> JSONResponse:
        return await service.get_event(event_id, request.headers.get("authorization"))

    return router
