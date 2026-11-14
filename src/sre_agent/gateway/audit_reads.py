"""Admin audit reads over the published 2.3.0 contract (issue #25, chain B2b)."""

import re
from copy import deepcopy
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Path, Request, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sre_agent.gate.errors import AuthenticationFailed, GovernedError
from sre_agent.gate.pipeline import (
    Admission,
    Gate,
    Refusals,
    Released,
    Scope,
    Terminal,
    declare,
    failing_as,
)
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.dto import AuditEvent
from sre_agent.persistence.models import AuditEventRow
from sre_agent.persistence.repositories import (
    AuditRepository,
    ResourceRepository,
)
from sre_agent.vocabulary import IDENTIFIER_PATTERN, is_identifier

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
CANONICAL_UUID_PATTERN = (
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
RFC3339_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
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
            "pattern": IDENTIFIER_PATTERN,
            "not": {"pattern": CANONICAL_UUID_PATTERN},
        },
    ]
}
RUNTIME_METADATA_SCHEMA_ID = "urn:sre-agent:runtime-schema:audit-event-metadata"
RUNTIME_METADATA_SCHEMA = "RuntimeAuditEventMetadata"


def _runtime_metadata_schema() -> dict[str, Any]:
    """Describe the actual runtime projection without changing frozen releases."""
    schema = AuditEvent.model_json_schema(ref_template="#/$defs/{model}")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = RUNTIME_METADATA_SCHEMA_ID
    schema["title"] = RUNTIME_METADATA_SCHEMA
    schema["x-sre-agent-schema-scope"] = "runtime-local-projection"
    schema["properties"]["event_id"] = deepcopy(AUDIT_EVENT_ID_SCHEMA)
    schema["properties"].pop("redacted_content", None)
    if "redacted_content" in schema.get("required", []):
        schema["required"].remove("redacted_content")
    for definition, field in (
        ("Redaction", "tool_schema_version"),
        ("AllowDecisionEvidence", "policy_ref"),
        ("DenyDecisionEvidence", "policy_ref"),
    ):
        nested = schema.get("$defs", {}).get(definition)
        if nested is not None:
            nested.get("properties", {}).pop(field, None)
            if field in nested.get("required", []):
                nested["required"].remove(field)
    return schema


RUNTIME_METADATA_SCHEMA_VALUE = _runtime_metadata_schema()
AUDIT_LIST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items", "limit", "truncated"],
    "properties": {
        "items": {
            "type": "array",
            "maxItems": MAX_LIMIT,
            "items": deepcopy(RUNTIME_METADATA_SCHEMA_VALUE),
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
        "truncated": {"type": "boolean"},
    },
}
AUDIT_QUERY_PARAMETERS = [
    {
        "name": "principal_id",
        "in": "query",
        "schema": {"type": "string", "pattern": IDENTIFIER_PATTERN},
    },
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
SCOPE = Scope(READ_ACTION, RESOURCE_TYPE, RESOURCE_ID)
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
    return re.fullmatch(CANONICAL_UUID_PATTERN, event_id) is not None or is_identifier(event_id)


def _event_id_json_schema(schema: dict[str, Any]) -> None:
    schema.clear()
    schema.update(AUDIT_EVENT_ID_SCHEMA)


UNAVAILABLE = GovernedError(
    503, "audit_unavailable", "Audit storage is temporarily unavailable.", retryable=True
)
REFUSALS = Refusals(
    unauthenticated=AuthenticationFailed("Authentication is required."),
    denied=GovernedError(403, "resource_unavailable", "Resource unavailable."),
    unavailable=UNAVAILABLE,
    audit_unavailable=UNAVAILABLE,
)
INVALID = GovernedError(422, "validation_error", "Request validation failed.")
NOT_FOUND = GovernedError(404, "resource_not_found", "The requested resource was not found.")
LIST = declare(
    "GET",
    "/v1/audit-events",
    action=READ_ACTION,
    resource_type=RESOURCE_TYPE,
    resource_id=RESOURCE_ID,
)
GET = declare(
    "GET",
    "/v1/audit-events/{id}",
    action=READ_ACTION,
    resource_type=RESOURCE_TYPE,
    resource_id=RESOURCE_ID,
)


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
        self.gate: Gate[Any] = Gate(sessions, REFUSALS, facts=ResourceRepository, audit=self._audit)

    async def _audit(self, terminal: Terminal) -> None:
        # Once a request is admitted, every outcome carries its subject; before, none does.
        if terminal.stage == "response":
            stage = "authorization"
        elif terminal.error is UNAVAILABLE:
            stage = "audit"
        else:
            stage = terminal.stage
        subject = stage == "authorization"
        code = terminal.error.code if terminal.error is not None else None
        event = self._projector.control_event(
            terminal.request_id,
            terminal.status,
            terminal.latency_ms,
            stage,
            operation="audit.project",
            action="read_metadata",
            reason={"validation_error": "contract_validation_failed"}.get(code or "", code),
            retryable=terminal.status == 503,
            context=terminal.context if subject else None,
            resource_ref=("administrative_control", "audit") if subject else None,
            decision=terminal.evaluation.decision if subject else None,  # type: ignore[union-attr]
            authorization_denial_cause=(
                terminal.evaluation.denial_cause  # type: ignore[union-attr]
                if subject and terminal.status in {403, 404}
                else None
            ),
        )
        await self.audit.append(event)

    def _digest(self, domain: str, value: str) -> str:
        return self._projector.reference(domain, value).digest

    @staticmethod
    def _parse_rfc3339_timestamp(value: str) -> datetime:
        if RFC3339_TIMESTAMP_PATTERN.fullmatch(value) is None:
            raise ValueError("timestamp is not RFC 3339 date-time")
        normalized = value[:10] + "T" + value[11:]
        if normalized.endswith(("z", "Z")):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)

    def _filters(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if any(key in raw for key in FORBIDDEN_PARAMS):
            return None
        parsed: dict[str, Any] = {}
        if (value := raw.get("decision")) is not None:
            if value not in ("allow", "deny"):
                return None
            parsed["decision"] = value
        if (value := raw.get("request_id")) is not None:
            if re.fullmatch(CANONICAL_UUID_PATTERN, str(value)) is None:
                return None
            try:
                parsed["request_id"] = str(UUID(str(value)))
            except ValueError:
                return None
        if (value := raw.get("principal_id")) is not None:
            if not is_identifier(str(value)):
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
                start = self._parse_rfc3339_timestamp(raw["from"])
            except ValueError:
                return None
            if start.tzinfo is None:
                return None
        if raw.get("to") is not None:
            try:
                end = self._parse_rfc3339_timestamp(raw["to"])
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

    async def list_events(
        self,
        raw: dict[str, Any],
        authorization: str | None,
        has_body: bool = False,
    ) -> Response:
        def validate() -> dict[str, Any]:
            filters = self._filters(raw)
            if filters is None or has_body:
                raise INVALID
            return filters

        async def events(admission: Admission, filters: dict[str, Any]) -> Released:
            limit = filters.pop("limit")
            with failing_as(UNAVAILABLE):
                async with self.sessions() as session:
                    events, has_more = await AuditRepository(session).query_filtered(
                        limit=limit, **filters
                    )
            return Released(
                {
                    "items": [project_metadata(e.model_dump(mode="json")) for e in events],
                    "limit": limit,
                    "truncated": has_more,
                }
            )

        return await self.gate.run(LIST, authorization, SCOPE, events, validate=validate)

    async def get_event(
        self,
        event_id: str,
        authorization: str | None,
        query_params: dict[str, Any] | None = None,
        has_body: bool = False,
    ) -> Response:
        def validate() -> str:
            if (
                not _valid_event_id(event_id)
                or has_body
                or any(
                    key in (query_params or {})
                    for key in ("content", "raw_content", "redacted_content", "include_content")
                )
            ):
                raise INVALID
            if re.fullmatch(CANONICAL_UUID_PATTERN, event_id) is not None:
                return str(UUID(event_id))
            return event_id

        async def event(admission: Admission, lookup_id: str) -> Released:
            with failing_as(UNAVAILABLE):
                async with self.sessions() as session:
                    row = await session.get(AuditEventRow, lookup_id)
                    event = None
                    if row is not None:
                        from sre_agent.persistence.projections import project_audit_event

                        event = project_audit_event(row)
            if event is None:
                raise NOT_FOUND
            return Released(project_metadata(event.model_dump(mode="json")))

        return await self.gate.run(GET, authorization, SCOPE, event, validate=validate)


def audit_reads_router(service: AuditReadsService) -> APIRouter:
    router = APIRouter(tags=["Audit"])
    audit_responses = {
        status: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {"$ref": "urn:sre-agent:schema:error-envelope:2.8.0"}
                }
            },
        }
        for status, description in AUDIT_ERROR_DESCRIPTIONS.items()
    }
    audit_list_responses = {
        status: response for status, response in audit_responses.items() if status != 404
    }

    async def _has_nonempty_body(request: Request) -> bool:
        has_body = False
        async for chunk in request.stream():
            has_body = has_body or bool(chunk)
        return has_body

    @router.get(
        LIST.path,
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
            **LIST.openapi_extra,
        },
    )
    async def list_events(
        request: Request,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_audit_bearer)] = None,
    ) -> Response:
        return await service.list_events(
            dict(request.query_params),
            request.headers.get("authorization"),
            await _has_nonempty_body(request),
        )

    @router.get(
        GET.path,
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
                    "application/json": {"schema": deepcopy(RUNTIME_METADATA_SCHEMA_VALUE)}
                },
            },
        },
        openapi_extra=GET.openapi_extra,
    )
    async def get_event(
        id: Annotated[str, Path(json_schema_extra=_event_id_json_schema)],
        request: Request,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_audit_bearer)] = None,
    ) -> Response:
        return await service.get_event(
            id,
            request.headers.get("authorization"),
            dict(request.query_params),
            await _has_nonempty_body(request),
        )

    return router
