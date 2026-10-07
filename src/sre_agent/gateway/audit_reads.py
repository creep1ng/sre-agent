"""Admin audit reads over the published 2.3.0 contract (issue #25, chain B2b)."""

import re
from datetime import datetime
from time import monotonic
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import PrincipalContext
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
CANONICAL_UUID_PATTERN = (
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
AUDIT_EVENT_ID_SCHEMA = {
    "oneOf": [
        {
            "type": "string",
            "format": "uuid",
            "pattern": CANONICAL_UUID_PATTERN,
        },
        {
            "type": "string",
            "pattern": ID_PATTERN,
            "not": {"pattern": CANONICAL_UUID_PATTERN},
        },
    ]
}
AUDIT_LIST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items", "limit", "truncated"],
    "properties": {
        "items": {
            "type": "array",
            "maxItems": MAX_LIMIT,
            "items": {"$ref": "urn:sre-agent:schema:audit-event-metadata:2.7.0"},
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
        "truncated": {"type": "boolean"},
    },
}
AUDIT_QUERY_PARAMETERS = [
    {"name": "principal_id", "in": "query", "schema": {"type": "string", "pattern": ID_PATTERN}},
    {"name": "decision", "in": "query", "schema": {"enum": ["allow", "deny"]}},
    {"name": "model_alias_id", "in": "query", "schema": {"type": "string"}},
    {"name": "request_id", "in": "query", "schema": {"type": "string", "format": "uuid"}},
    {"name": "incident_id", "in": "query", "schema": {"type": "string"}},
    {"name": "run_id", "in": "query", "schema": {"type": "string"}},
    {"name": "task_id", "in": "query", "schema": {"type": "string"}},
    {"name": "trace_id", "in": "query", "schema": {"type": "string"}},
    {"name": "from", "in": "query", "schema": {"type": "string", "format": "date-time"}},
    {"name": "to", "in": "query", "schema": {"type": "string", "format": "date-time"}},
    {
        "name": "limit",
        "in": "query",
        "schema": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": DEFAULT_LIMIT},
    },
]
AUDIT_LIST_REQUIRED_FILTERS = FILTER_KEYS.copy()
AUDIT_FORBIDDEN_QUERY_PARAMETERS = FORBIDDEN_PARAMS.copy()
AUDIT_SCOPE = {
    "action": READ_ACTION,
    "resource_type": RESOURCE_TYPE,
    "resource_id": RESOURCE_ID,
}
AUDIT_ERROR_DESCRIPTIONS = {
    401: "Authentication failed before lookup",
    403: "Authenticated Principal is not permitted",
    404: "Identical response for hidden and absent resources",
    422: "Closed-body, unsafe-list, unsupported-pagination, or audit-content validation failure",
    503: "Authoritative audit store did not durably accept the safe event",
}
_audit_bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


def _valid_event_id(value: Any) -> bool:
    event_id = str(value)
    return (
        re.fullmatch(CANONICAL_UUID_PATTERN, event_id) is not None
        or re.fullmatch(ID_PATTERN, event_id) is not None
    )


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
    def __init__(self, sessions: Any, hmac_key: bytes, audit: Any) -> None:
        self.sessions, self.audit = sessions, audit
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
        authorization: str | None,
    ) -> tuple[PrincipalContext | None, Any | None, int | None]:
        try:
            context = await self._authenticate(authorization)
            if context is None:
                return None, None, 401
            async with self.sessions() as session:
                evaluation = await AuthorizationDecisionEngine(
                    ResourceRepository(session), GrantRepository(session)
                ).evaluate(context.principal, READ_ACTION, RESOURCE_TYPE, RESOURCE_ID)
        except Exception:
            return None, None, 503
        if evaluation.decision.decision != "allow":
            return context, evaluation, 403
        return context, evaluation, None

    async def _finish(
        self,
        request_id: UUID,
        started: float,
        status: int,
        stage: str,
        *,
        error_code: str | None = None,
        payload: dict[str, Any] | None = None,
        context: PrincipalContext | None = None,
        evaluation: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        try:
            audit_reason = {
                "validation_error": "contract_validation_failed",
            }.get(error_code or "", error_code)
            event = self._projector.control_event(
                request_id,
                status,
                max(0, int((monotonic() - started) * 1000)),
                stage,
                operation="audit.project",
                action="read_metadata",
                reason=audit_reason,
                retryable=status == 503,
                context=context if stage == "authorization" else None,
                resource_ref=("administrative_control", "audit")
                if stage == "authorization"
                else None,
                decision=evaluation.decision if stage == "authorization" else None,
                authorization_denial_cause=(
                    evaluation.denial_cause
                    if stage == "authorization" and status in {403, 404}
                    else None
                ),
            )
            await self.audit.append(event)
        except Exception:
            return self._error(request_id, 503)
        if payload is not None:
            return JSONResponse(payload, status_code=status)
        code = error_code or ERRORS[status][0]
        return JSONResponse(
            {
                "error": {"code": code, "message": ERRORS[status][1]},
                "request_id": str(request_id),
                "retryable": status == 503,
            },
            status_code=status,
            headers=headers,
        )

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
        request_id, started = uuid4(), monotonic()
        filters = self._filters(raw)
        if filters is None:
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                error_code="validation_error",
            )
        context, evaluation, auth_status = await self._authorized(authorization)
        if auth_status is not None:
            stage = (
                "authentication"
                if auth_status == 401
                else ("authorization" if auth_status == 403 else "audit")
            )
            return await self._finish(
                request_id,
                started,
                auth_status,
                stage,
                error_code=ERRORS[auth_status][0],
                context=context,
                evaluation=evaluation,
                headers={"WWW-Authenticate": "Bearer"} if auth_status == 401 else None,
            )
        limit = filters.pop("limit")
        try:
            async with self.sessions() as session:
                events, has_more = await AuditRepository(session).query_filtered(
                    limit=limit, **filters
                )
        except Exception:
            return await self._finish(
                request_id,
                started,
                503,
                "authorization",
                error_code="audit_unavailable",
                context=context,
                evaluation=evaluation,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            context=context,
            evaluation=evaluation,
            payload={
                "items": [project_metadata(e.model_dump(mode="json")) for e in events],
                "limit": limit,
                "truncated": has_more,
            },
        )

    async def get_event(self, event_id: str, authorization: str | None) -> JSONResponse:
        request_id, started = uuid4(), monotonic()
        if not _valid_event_id(event_id):
            return await self._finish(
                request_id,
                started,
                422,
                "validation",
                error_code="validation_error",
            )
        context, evaluation, auth_status = await self._authorized(authorization)
        if auth_status is not None:
            stage = (
                "authentication"
                if auth_status == 401
                else ("authorization" if auth_status == 403 else "audit")
            )
            return await self._finish(
                request_id,
                started,
                auth_status,
                stage,
                error_code=ERRORS[auth_status][0],
                context=context,
                evaluation=evaluation,
                headers={"WWW-Authenticate": "Bearer"} if auth_status == 401 else None,
            )
        try:
            async with self.sessions() as session:
                row = await session.get(AuditEventRow, event_id)
                event = None
                if row is not None:
                    from sre_agent.persistence.projections import project_audit_event

                    event = project_audit_event(row)
        except Exception:
            return await self._finish(
                request_id,
                started,
                503,
                "authorization",
                error_code="audit_unavailable",
                context=context,
                evaluation=evaluation,
            )
        if event is None:
            return await self._finish(
                request_id,
                started,
                404,
                "authorization",
                error_code="resource_not_found",
                context=context,
                evaluation=evaluation,
            )
        return await self._finish(
            request_id,
            started,
            200,
            "authorization",
            context=context,
            evaluation=evaluation,
            payload=project_metadata(event.model_dump(mode="json")),
        )


def audit_reads_router(service: AuditReadsService) -> APIRouter:
    router = APIRouter(tags=["Audit"])
    audit_responses = {
        status: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": "urn:sre-agent:schema:error-envelope:2.7.0"}
                }
            },
        }
        for status, description in AUDIT_ERROR_DESCRIPTIONS.items()
    }
    audit_list_responses = {
        status: response for status, response in audit_responses.items() if status != 404
    }

    @router.get(
        "/v1/audit-events",
        operation_id="listAuditEvents",
        summary="List filtered audit metadata",
        description=(
            "Requires a listed identity, decision, alias, correlation, or bounded-time filter; "
            "ordered by (occurred_at,event_id) descending. Content parameters are rejected."
        ),
        responses={
            **audit_list_responses,
            200: {
                "description": "Bounded metadata-only AuditEvent list",
                "content": {"application/json": {"schema": AUDIT_LIST_SCHEMA}},
            },
        },
        openapi_extra={
            "parameters": AUDIT_QUERY_PARAMETERS,
            "x-required-query-any-of": AUDIT_LIST_REQUIRED_FILTERS,
            "x-forbidden-query-parameters": AUDIT_FORBIDDEN_QUERY_PARAMETERS,
            "x-governed-scope": AUDIT_SCOPE,
        },
    )
    async def list_events(
        request: Request,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_audit_bearer)] = None,
    ) -> JSONResponse:
        return await service.list_events(
            dict(request.query_params), request.headers.get("authorization")
        )

    @router.get(
        "/v1/audit-events/{id}",
        operation_id="getAuditEvent",
        summary="Get audit metadata",
        description=(
            "Metadata and redaction state only. Raw or redacted content retrieval is unsupported."
        ),
        responses={
            **audit_responses,
            200: {
                "description": "Metadata-only AuditEvent projection",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "urn:sre-agent:schema:audit-event-metadata:2.7.0"}
                    }
                },
            },
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": AUDIT_EVENT_ID_SCHEMA,
                }
            ],
            "x-governed-scope": AUDIT_SCOPE,
        },
    )
    async def get_event(
        id: str,
        request: Request,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_audit_bearer)] = None,
    ) -> JSONResponse:
        return await service.get_event(id, request.headers.get("authorization"))

    return router
