"""Bounded aggregates over persisted response-consumption audit evidence."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.governance.dto import AuthorizationDenialCause
from sre_agent.persistence.models import AuditEventRow

SUPPORTED_MONTH_PATTERN = (
    r"^(?:(?:000[1-9]|00[1-9][0-9]|0[1-9][0-9]{2}|"
    r"[1-8][0-9]{3}|9[0-8][0-9]{2}|99[0-8][0-9]|999[0-8])-"
    r"(?:0[1-9]|1[0-2])|9999-(?:0[1-9]|1[01]))$"
)


class UsageReadLimitExceeded(RuntimeError):
    """The selected persisted evidence exceeds the explicit projection bound."""


class UsageReadCost(BaseModel):
    # FastAPI omits const: None when serializing OpenAPI; type: null survives.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "if": {"properties": {"amount": {"type": "null"}}},
            "then": {"properties": {"currency": {"type": "null"}, "precision": {"type": "null"}}},
            "else": {"properties": {"currency": {"const": "USD"}, "precision": {"const": "exact"}}},
        },
    )
    amount: Annotated[str | None, Field(pattern=r"^(0|[1-9]\d*)(\.\d+)?$")]
    currency: Literal["USD"] | None
    nature: Literal["billed"]
    precision: Literal["exact"] | None
    price_versions: list[str]

    @model_validator(mode="after")
    def validate_metadata(self) -> UsageReadCost:
        expected = (None, None) if self.amount is None else ("USD", "exact")
        if (self.currency, self.precision) != expected:
            raise ValueError("cost metadata must match the billed amount availability")
        return self


class UsageReadTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: Annotated[int | None, Field(ge=0)]
    output_tokens: Annotated[int | None, Field(ge=0)]
    total_tokens: Annotated[int | None, Field(ge=0)]
    cost: UsageReadCost


class UsageReadCoverage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "properties": {
                        "status": {"const": "complete"},
                        "incomplete": {"const": 0},
                        "unknown": {"const": 0},
                    }
                },
                {
                    "properties": {
                        "status": {"const": "unknown"},
                        "known": {"const": 0},
                        "incomplete": {"const": 0},
                        "unknown": {"type": "integer", "minimum": 1},
                    }
                },
                {
                    "properties": {"status": {"const": "partial"}},
                    "anyOf": [
                        {"properties": {"incomplete": {"type": "integer", "minimum": 1}}},
                        {
                            "properties": {
                                "known": {"type": "integer", "minimum": 1},
                                "unknown": {"type": "integer", "minimum": 1},
                            }
                        },
                    ],
                },
            ]
        },
    )
    status: Literal["complete", "partial", "unknown"]
    known: Annotated[int, Field(ge=0)]
    incomplete: Annotated[int, Field(ge=0)]
    unknown: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_status(self) -> UsageReadCoverage:
        if self.incomplete or (self.known and self.unknown):
            expected = "partial"
        else:
            expected = "unknown" if self.unknown else "complete"
        if self.status != expected:
            raise ValueError("coverage status must match the request evidence counts")
        return self


class UsageReadMonth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    request_count: Annotated[int, Field(ge=0)]


class RequestIdUsageFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID


class IncidentUsageFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: Annotated[str, Field(min_length=1, max_length=128)]


class MonthUsageFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: Annotated[str, Field(pattern=SUPPORTED_MONTH_PATTERN)]


UsageReadFilter = Annotated[
    RequestIdUsageFilter | IncidentUsageFilter | MonthUsageFilter,
    Field(union_mode="left_to_right"),
]


class UsageReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter: UsageReadFilter
    request_count: Annotated[int, Field(ge=0)]
    incident_runs: Annotated[int, Field(ge=0)]
    months: list[UsageReadMonth]
    totals: UsageReadTotals
    coverage: UsageReadCoverage

    @model_validator(mode="after")
    def validate_request_count(self) -> UsageReadResponse:
        coverage = self.coverage
        if coverage.known + coverage.incomplete + coverage.unknown != self.request_count:
            raise ValueError("coverage counts must sum to request_count")
        return self


# The dependency is module-scoped so FastAPI can resolve its postponed annotation
# while generating OpenAPI (local dependency variables are not in that namespace).
_usage_bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


class UsageReadProjection:
    """Read and aggregate only bounded ``responses.create`` audit evidence."""

    MAX_ROWS = 1000

    def __init__(
        self, sessions: async_sessionmaker, audit_hmac_key: bytes, audit_store: Any | None = None
    ) -> None:
        self._sessions = sessions
        self._audit = AuditProjector(audit_hmac_key)
        self._audit_store = audit_store

    async def read(
        self,
        *,
        request_id: UUID | None = None,
        incident_id: str | None = None,
        month: str | None = None,
    ) -> dict[str, Any]:
        """Return one selector's aggregate or fail rather than silently truncating."""
        rows, selected_filter, incident_ref = await self.select_evidence(
            request_id=request_id, incident_id=incident_id, month=month
        )
        return self._aggregate(rows, selected_filter, incident_ref)

    async def select_evidence(
        self,
        *,
        request_id: UUID | None = None,
        incident_id: str | None = None,
        month: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any] | None]:
        """Select the authoritative bounded audit evidence shared by usage reads."""
        selectors = sum(value is not None for value in (request_id, incident_id, month))
        if selectors != 1:
            raise ValueError("exactly one usage selector is required")

        statement = select(
            AuditEventRow.event_id.label("event_id"),
            AuditEventRow.occurred_at,
            AuditEventRow.stage.label("stage"),
            AuditEventRow.correlation["request_id"].astext.label("request_id"),
            AuditEventRow.correlation["incident_ref"].label("incident_ref"),
            AuditEventRow.correlation["run_ref"].label("run_ref"),
            AuditEventRow.consumption,
        )
        request_ids = AuditEventRow.correlation["request_id"].astext
        canonical_months = (
            select(
                request_ids.label("request_id"),
                func.min(AuditEventRow.occurred_at).label("canonical_at"),
            )
            .where(AuditEventRow.operation == "responses.create")
            .group_by(request_ids)
            .subquery()
        )
        statement = (
            statement.add_columns(canonical_months.c.canonical_at)
            .join(canonical_months, request_ids == canonical_months.c.request_id)
            .where(AuditEventRow.operation == "responses.create")
        )

        incident_ref = None
        if request_id is not None:
            statement = statement.where(
                AuditEventRow.correlation["request_id"].astext == str(request_id)
            )
            selected_filter: dict[str, str] = {"request_id": str(request_id)}
        elif incident_id is not None:
            incident_ref = self._audit.reference("incident_id", incident_id).model_dump(mode="json")
            # Select requests first: conflicting attribution must remain visible.
            incident_requests = select(request_ids).where(
                AuditEventRow.operation == "responses.create",
                AuditEventRow.correlation["incident_ref"]["digest"].astext
                == incident_ref["digest"],
                AuditEventRow.correlation["incident_ref"]["key_version"].as_integer()
                == incident_ref["key_version"],
                AuditEventRow.correlation["incident_ref"]["algorithm"].astext
                == incident_ref["algorithm"],
            )
            statement = statement.where(request_ids.in_(incident_requests))
            selected_filter = {"incident_id": incident_id}
        else:
            month_start, month_end = self._month_range(month or "")
            statement = statement.where(
                canonical_months.c.canonical_at >= month_start,
                canonical_months.c.canonical_at < month_end,
            )
            selected_filter = {"month": month}

        statement = statement.order_by(
            canonical_months.c.canonical_at.asc(),
            request_ids.asc(),
            AuditEventRow.occurred_at.asc(),
            AuditEventRow.event_id.asc(),
        ).limit(self.MAX_ROWS + 1)
        async with self._sessions() as session:
            rows = (await session.execute(statement)).mappings().all()
        if len(rows) > self.MAX_ROWS:
            raise UsageReadLimitExceeded("usage scope exceeds the evidence row limit")
        return rows, selected_filter, incident_ref

    @staticmethod
    def _month_range(month: str) -> tuple[datetime, datetime]:
        try:
            year_text, month_text = month.split("-", maxsplit=1)
            year, month_number = int(year_text), int(month_text)
            if len(year_text) != 4 or len(month_text) != 2 or not 1 <= month_number <= 12:
                raise ValueError
            start = datetime(year, month_number, 1, tzinfo=UTC)
        except (ValueError, TypeError) as error:
            raise ValueError("month must use YYYY-MM format") from error
        if month_number == 12:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(year, month_number + 1, 1, tzinfo=UTC)
        return start, end

    @classmethod
    def _aggregate(
        cls,
        rows: list[dict[str, Any]],
        selected_filter: dict[str, str],
        selected_incident_ref: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        requests: dict[str, list[dict[str, Any]]] = defaultdict(list)
        runs: set[tuple[str, int, str]] = set()
        monthly_requests: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            request_key = str(row["request_id"])
            requests[request_key].append(row)
            # Foreign related rows are consistency evidence, not selected runs.
            if row["run_ref"] is not None and (
                selected_incident_ref is None or row["incident_ref"] == selected_incident_ref
            ):
                run_ref = row["run_ref"]
                runs.add((run_ref["algorithm"], run_ref["key_version"], run_ref["digest"]))
            month_key = row["canonical_at"].astimezone(UTC).strftime("%Y-%m")
            monthly_requests[month_key].add(request_key)

        reconciled = cls._reconcile_requests(requests)
        known: list[dict[str, Any]] = []
        incomplete = 0
        unknown = 0
        for request in reconciled.values():
            if not request["consistent"]:
                unknown += 1
                continue
            consumption = request["consumption"]
            availability = consumption.get("availability") if consumption else None
            if availability == "complete":
                known.append(consumption)
            elif availability == "partial":
                incomplete += 1
            else:
                unknown += 1

        request_count = len(requests)
        if unknown:
            status = "unknown" if not known and not incomplete else "partial"
        elif incomplete:
            status = "partial"
        else:
            status = "complete"

        complete_coverage = not incomplete and not unknown
        totals = cls._totals(known, complete_coverage and request_count > 0)
        return {
            "filter": selected_filter,
            "request_count": request_count,
            "incident_runs": len(runs),
            "months": [
                {"month": month_key, "request_count": len(monthly_requests[month_key])}
                for month_key in sorted(monthly_requests)
            ],
            "totals": totals,
            "coverage": {
                "status": status,
                "known": len(known),
                "incomplete": incomplete,
                "unknown": unknown,
            },
        }

    @staticmethod
    def _reconcile_requests(
        requests: dict[str, list[dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        """Deduplicate request evidence and detect inconsistent per-request facts."""
        reconciled: dict[str, dict[str, Any]] = {}
        for request_key, evidence in requests.items():
            consumption_values = {
                json.dumps(row["consumption"], sort_keys=True, separators=(",", ":"))
                if row["consumption"] is not None
                else "null"
                for row in evidence
            }
            incident_refs = {json.dumps(row["incident_ref"], sort_keys=True) for row in evidence}
            consistent = len(consumption_values) == 1 and len(incident_refs) == 1
            reconciled[request_key] = {
                "consistent": consistent,
                "consumption": evidence[0]["consumption"] if consistent else None,
                "canonical_at": min(row["canonical_at"] for row in evidence),
            }
        return reconciled

    @classmethod
    def _totals(cls, known: list[dict[str, Any]], complete: bool) -> dict[str, Any]:
        if not complete:
            inputs = outputs = totals = None
        else:
            inputs = sum(item["input_tokens"] for item in known)
            outputs = sum(item["output_tokens"] for item in known)
            totals = sum(item["total_tokens"] for item in known)

        versions = sorted(
            {
                item["pricing_context"]["price_version"]
                for item in known
                if item.get("pricing_context") is not None
            }
        )
        cost_amount = None
        if (
            complete
            and known
            and len(versions) == 1
            and all(
                item.get("billed_usd") is not None
                and item.get("currency") == "USD"
                and item.get("precision") == "exact"
                and item.get("pricing_context") is not None
                for item in known
            )
        ):
            cost_amount = cls._sum_billed_usd([item["billed_usd"] for item in known])
        return {
            "input_tokens": inputs,
            "output_tokens": outputs,
            "total_tokens": totals,
            "cost": {
                "amount": cost_amount,
                "currency": "USD" if cost_amount is not None else None,
                "nature": "billed",
                "precision": "exact" if cost_amount is not None else None,
                "price_versions": versions,
            },
        }

    @staticmethod
    def _sum_billed_usd(amounts: list[str]) -> str:
        """Sum nonnegative fixed-point USD strings with integer arithmetic."""
        scale = max(
            (len(amount.split(".", maxsplit=1)[1]) for amount in amounts if "." in amount),
            default=0,
        )
        scaled_total = 0
        for amount in amounts:
            whole, separator, fraction = amount.partition(".")
            scaled_total += int(whole + (fraction.ljust(scale, "0") if separator else "0" * scale))
        digits = str(scaled_total)
        if scale == 0:
            return digits
        digits = digits.zfill(scale + 1)
        return f"{digits[:-scale]}.{digits[-scale:]}"


def usage_router(projection: UsageReadProjection) -> APIRouter:
    """Expose the usage projection only behind the governed administrator scope."""

    async def finish(
        request: Request,
        *,
        status: int,
        stage: str,
        code: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | UsageReadResponse | None = None,
        context: Any = None,
        decision: Any = None,
        authorization_denial_cause: AuthorizationDenialCause | None = None,
        resource_ref: tuple[str, str] | None = None,
    ) -> JSONResponse | UsageReadResponse:
        request_id = UUID(str(getattr(request.state, "usage_request_id", None) or UUID(int=0)))
        started = getattr(request.state, "usage_started", monotonic())
        reason = {
            "validation_error": "contract_validation_failed",
            "usage_scope_too_large": "contract_validation_failed",
            "storage_unavailable": "upstream_unavailable",
            "authentication_failed": "authentication_failed",
            "resource_unavailable": "no_matching_grant",
        }.get(code, code)
        if projection._audit_store is None:
            audit_failed = True
        else:
            try:
                event = projection._audit.control_event(
                    request_id,
                    status,
                    max(0, int((monotonic() - started) * 1000)),
                    stage,
                    operation="usage.read",
                    action="admin.read",
                    reason=reason,
                    retryable=status in {500, 503, 504},
                    context=context,
                    resource_ref=resource_ref,
                    decision=decision,
                    authorization_denial_cause=authorization_denial_cause,
                )
                await projection._audit_store.append(event)
                audit_failed = False
            except Exception:
                audit_failed = True
        if audit_failed:
            return JSONResponse(
                {
                    "error": {"code": "audit_unavailable", "message": "Audit unavailable."},
                    "request_id": str(request_id),
                    "retryable": True,
                },
                status_code=503,
            )
        if isinstance(payload, UsageReadResponse):
            return payload
        if payload is not None:
            return JSONResponse(payload, status_code=status)
        public_code = code or "storage_unavailable"
        public_message = message or "Usage storage is temporarily unavailable."
        return JSONResponse(
            {
                "error": {"code": public_code, "message": public_message},
                "request_id": str(request_id),
                "retryable": status in {500, 503, 504},
            },
            status_code=status,
            headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
        )

    async def authorize_usage(request: Request) -> tuple[Any, Any, JSONResponse | None]:
        """Share the governed authorization and audited denial path across usage reads."""
        try:
            context, evaluation = await authorize_governed_access(
                projection._sessions,
                request.headers.get("authorization"),
                "admin.read",
                "administrative_control",
                "usage",
            )
        except AuthenticationFailed:
            denied = await finish(
                request,
                status=401,
                stage="authentication",
                code="authentication_failed",
                message="Authentication failed.",
            )
            return None, None, denied
        except Exception:
            denied = await finish(request, status=503, stage="audit", code="storage_unavailable")
            return None, None, denied
        if evaluation.decision.decision == "deny":
            denied = await finish(
                request,
                status=403,
                stage="authorization",
                code="resource_unavailable",
                message="Administrative read is not authorized.",
                context=context,
                decision=evaluation.decision,
                authorization_denial_cause=evaluation.denial_cause,
                resource_ref=("administrative_control", "usage"),
            )
            return None, None, denied
        return context, evaluation, None

    class UsageReadRoute(APIRoute):
        def get_route_handler(self):
            route_handler = super().get_route_handler()

            async def validation_audited_handler(request: Request):
                request.state.usage_request_id = uuid4()
                request.state.usage_started = monotonic()
                try:
                    return await route_handler(request)
                except RequestValidationError:
                    return await finish(
                        request,
                        status=422,
                        stage="validation",
                        code="validation_error",
                        message="Exactly one bounded usage selector is required.",
                    )

            return validation_audited_handler

    router = APIRouter(route_class=UsageReadRoute)
    selector_names = {"request_id", "incident_id", "month"}
    known_unbounded = {
        "from",
        "to",
        "cursor",
        "page",
        "offset",
        "continuation_token",
        "prompt",
        "output",
        "api_key",
    }

    @router.get(
        "/v1/usage/consumption",
        response_model=UsageReadResponse,
        operation_id="readUsageConsumption",
        summary="Read persisted request consumption aggregates",
        description=(
            "Reads only persisted consumption evidence. Exactly one bounded selector is required. "
            "Months use half-open UTC calendar intervals. Reads do not create consumption evidence."
        ),
        responses={
            401: {"description": "Authentication failed; no usage data or counts are returned."},
            403: {"description": "Administrative read is not authorized; no counts are returned."},
            413: {"description": "The matching evidence exceeds the projection bound."},
            422: {"description": "Selector is missing, malformed, or supplied more than once."},
            503: {"description": "Persisted usage could not be read."},
        },
        openapi_extra={
            "x-required-query-one-of": ["request_id", "incident_id", "month"],
            "x-maximum-evidence-rows": UsageReadProjection.MAX_ROWS,
            "x-governed-scope": {
                "action": "admin.read",
                "resource_type": "administrative_control",
                "resource_id": "usage",
            },
        },
    )
    async def read_usage(
        request: Request,
        request_id: Annotated[
            UUID | None, Query(description="Effective response request UUID.")
        ] = None,
        incident_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        month: Annotated[str | None, Query(pattern=SUPPORTED_MONTH_PATTERN)] = None,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_usage_bearer)] = None,
    ) -> UsageReadResponse | JSONResponse:
        request.state.usage_request_id = uuid4()
        supplied = list(request.query_params.multi_items())
        supplied_names = [name for name, _ in supplied]
        if (
            any(name not in selector_names for name in supplied_names)
            or any(name in known_unbounded for name in supplied_names)
            or len(supplied) != 1
        ):
            return await finish(
                request,
                status=422,
                stage="validation",
                code="validation_error",
                message="Exactly one bounded usage selector is required.",
            )

        filters: dict[str, Any] = {
            "request_id": request_id,
            "incident_id": incident_id,
            "month": month,
        }
        filters = {name: value for name, value in filters.items() if value is not None}
        if len(filters) != 1:
            return await finish(
                request,
                status=422,
                stage="validation",
                code="validation_error",
                message="Exactly one bounded usage selector is required.",
            )
        if month is not None and re.fullmatch(SUPPORTED_MONTH_PATTERN, month) is None:
            return await finish(
                request,
                status=422,
                stage="validation",
                code="validation_error",
                message="The usage selector is invalid.",
            )

        _context, evaluation, denial = await authorize_usage(request)
        if denial is not None:
            return denial

        try:
            result = await projection.read(**filters)
        except UsageReadLimitExceeded:
            return await finish(
                request,
                status=413,
                stage="validation",
                code="usage_scope_too_large",
                message="The usage scope exceeds the read limit.",
                context=_context,
                decision=evaluation.decision,
                resource_ref=("administrative_control", "usage"),
            )
        except ValueError:
            return await finish(
                request,
                status=422,
                stage="validation",
                code="validation_error",
                message="The usage selector is invalid.",
                context=_context,
                decision=evaluation.decision,
                resource_ref=("administrative_control", "usage"),
            )
        except Exception:
            return await finish(
                request,
                status=503,
                stage="audit",
                code="storage_unavailable",
                context=_context,
                decision=evaluation.decision,
                resource_ref=("administrative_control", "usage"),
            )
        return await finish(
            request,
            status=200,
            stage="authorization",
            payload=UsageReadResponse.model_validate(result),
            context=_context,
            decision=evaluation.decision,
            resource_ref=("administrative_control", "usage"),
        )

    return router
