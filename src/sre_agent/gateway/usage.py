"""Bounded aggregates over persisted response-consumption audit evidence."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from sre_agent.gateway.audit import AuditProjector
from sre_agent.gateway.authentication import AuthenticationFailed, authorize_governed_access
from sre_agent.persistence.models import AuditEventRow


class UsageReadLimitExceeded(RuntimeError):
    """The selected persisted evidence exceeds the explicit projection bound."""


class UsageReadCost(BaseModel):
    amount: Annotated[str | None, Field(pattern=r"^(0|[1-9]\d*)(\.\d+)?$")]
    currency: Literal["USD"] | None
    nature: Literal["billed"]
    precision: Literal["exact"] | None
    price_versions: list[str]


class UsageReadTotals(BaseModel):
    input_tokens: Annotated[int | None, Field(ge=0)]
    output_tokens: Annotated[int | None, Field(ge=0)]
    total_tokens: Annotated[int | None, Field(ge=0)]
    cost: UsageReadCost


class UsageReadCoverage(BaseModel):
    status: Literal["complete", "partial", "unknown"]
    known: Annotated[int, Field(ge=0)]
    incomplete: Annotated[int, Field(ge=0)]
    unknown: Annotated[int, Field(ge=0)]


class UsageReadMonth(BaseModel):
    month: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    request_count: Annotated[int, Field(ge=0)]


class UsageReadResponse(BaseModel):
    filter: dict[str, str]
    request_count: Annotated[int, Field(ge=0)]
    incident_runs: Annotated[int, Field(ge=0)]
    months: list[UsageReadMonth]
    totals: UsageReadTotals
    coverage: UsageReadCoverage


# The dependency is module-scoped so FastAPI can resolve its postponed annotation
# while generating OpenAPI (local dependency variables are not in that namespace).
_usage_bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


class UsageReadProjection:
    """Read and aggregate only bounded ``responses.create`` audit evidence."""

    MAX_ROWS = 1000

    def __init__(self, sessions: async_sessionmaker, audit_hmac_key: bytes) -> None:
        self._sessions = sessions
        self._audit = AuditProjector(audit_hmac_key)

    async def read(
        self,
        *,
        request_id: UUID | None = None,
        incident_id: str | None = None,
        month: str | None = None,
    ) -> dict[str, Any]:
        """Return one selector's aggregate or fail rather than silently truncating."""
        selectors = sum(value is not None for value in (request_id, incident_id, month))
        if selectors != 1:
            raise ValueError("exactly one usage selector is required")

        statement = select(
            AuditEventRow.occurred_at,
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

        if request_id is not None:
            statement = statement.where(
                AuditEventRow.correlation["request_id"].astext == str(request_id)
            )
            selected_filter: dict[str, str] = {"request_id": str(request_id)}
        elif incident_id is not None:
            incident_ref = self._audit.reference("incident_id", incident_id).model_dump(mode="json")
            statement = statement.where(
                AuditEventRow.correlation["incident_ref"]["digest"].astext
                == incident_ref["digest"],
                AuditEventRow.correlation["incident_ref"]["key_version"].as_integer()
                == incident_ref["key_version"],
                AuditEventRow.correlation["incident_ref"]["algorithm"].astext
                == incident_ref["algorithm"],
            )
            selected_filter = {"incident_id": incident_id}
        else:
            month_start, month_end = self._month_range(month or "")
            statement = statement.where(
                canonical_months.c.canonical_at >= month_start,
                canonical_months.c.canonical_at < month_end,
            )
            selected_filter = {"month": month}

        statement = statement.order_by(
            AuditEventRow.occurred_at.asc(), AuditEventRow.event_id.asc()
        ).limit(self.MAX_ROWS + 1)
        async with self._sessions() as session:
            rows = (await session.execute(statement)).mappings().all()
        if len(rows) > self.MAX_ROWS:
            raise UsageReadLimitExceeded("usage scope exceeds the evidence row limit")

        return self._aggregate(rows, selected_filter)

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
        cls, rows: list[dict[str, Any]], selected_filter: dict[str, str]
    ) -> dict[str, Any]:
        requests: dict[str, list[dict[str, Any]]] = defaultdict(list)
        runs: set[tuple[str, int, str]] = set()
        monthly_requests: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            request_key = str(row["request_id"])
            requests[request_key].append(row)
            if row["run_ref"] is not None:
                run_ref = row["run_ref"]
                runs.add((run_ref["algorithm"], run_ref["key_version"], run_ref["digest"]))
            month_key = row["canonical_at"].astimezone(UTC).strftime("%Y-%m")
            monthly_requests[month_key].add(request_key)

        known: list[dict[str, Any]] = []
        incomplete = 0
        unknown = 0
        for evidence in requests.values():
            consumption_values = {
                json.dumps(row["consumption"], sort_keys=True, separators=(",", ":"))
                if row["consumption"] is not None
                else "null"
                for row in evidence
            }
            if len(consumption_values) != 1:
                unknown += 1
                continue
            consumption = evidence[0]["consumption"]
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
    router = APIRouter()
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

    def error(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "error": {"code": code, "message": message},
                "request_id": str(UUID(int=0)),
                "retryable": status == 503,
            },
        )

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
        month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
        _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_usage_bearer)] = None,
    ) -> UsageReadResponse | JSONResponse:
        supplied = list(request.query_params.multi_items())
        supplied_names = [name for name, _ in supplied]
        if (
            any(name not in selector_names for name in supplied_names)
            or any(name in known_unbounded for name in supplied_names)
            or len(supplied) != 1
        ):
            return error(422, "validation_error", "Exactly one bounded usage selector is required.")

        filters: dict[str, Any] = {
            "request_id": request_id,
            "incident_id": incident_id,
            "month": month,
        }
        filters = {name: value for name, value in filters.items() if value is not None}
        if len(filters) != 1:
            return error(422, "validation_error", "Exactly one bounded usage selector is required.")

        try:
            _context, evaluation = await authorize_governed_access(
                projection._sessions,
                request.headers.get("authorization"),
                "admin.read",
                "administrative_control",
                "usage",
            )
        except AuthenticationFailed:
            return error(401, "authentication_failed", "Authentication failed.")
        except Exception:
            return error(503, "storage_unavailable", "Usage storage is temporarily unavailable.")

        if evaluation.decision.decision == "deny":
            return error(403, "resource_unavailable", "Administrative read is not authorized.")

        try:
            result = await projection.read(**filters)
        except UsageReadLimitExceeded:
            return error(413, "usage_scope_too_large", "The usage scope exceeds the read limit.")
        except ValueError:
            return error(422, "validation_error", "The usage selector is invalid.")
        except Exception:
            return error(503, "storage_unavailable", "Usage storage is temporarily unavailable.")
        return result

    return router
