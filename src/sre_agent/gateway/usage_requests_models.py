"""Closed public DTOs for the historical request-attribution contract."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sre_agent.governance.dto import Consumption


class AvailableRequestedAssignment(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    availability: Literal["available"]
    alias: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$", max_length=64)]
    model: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$", max_length=200)]
    provider: Annotated[str, Field(min_length=1, max_length=100)]
    router: Annotated[str, Field(min_length=1, max_length=100)]


class UnavailableRequestedAssignment(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    availability: Literal["unavailable"]
    alias: Literal[None]
    model: Literal[None]
    provider: Literal[None]
    router: Literal[None]


RequestedAssignment = AvailableRequestedAssignment | UnavailableRequestedAssignment


class AvailableModelCredit(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    availability: Literal["available"]
    value: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$", max_length=200)]


class AvailableProviderCredit(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    availability: Literal["available"]
    value: Annotated[str, Field(pattern=r"^[a-z][a-z0-9._-]{0,63}$", max_length=64)]


class UnavailableCredit(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    availability: Literal["unavailable"]
    value: Literal[None]


ModelCredit = AvailableModelCredit | UnavailableCredit
ProviderCredit = AvailableProviderCredit | UnavailableCredit


class RequestIdFilter(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    request_id: UUID


class IncidentIdFilter(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    incident_id: Annotated[str, Field(min_length=1, max_length=128)]


class MonthFilter(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    month: Annotated[
        str,
        Field(
            pattern=(
                r"^(?:(?:000[1-9]|00[1-9][0-9]|0[1-9][0-9]{2}|[1-8][0-9]{3}|"
                r"9[0-8][0-9]{2}|99[0-8][0-9]|999[0-8])-(?:0[1-9]|1[0-2])|"
                r"9999-(?:0[1-9]|1[01]))$"
            )
        ),
    ]


RequestFilter = RequestIdFilter | IncidentIdFilter | MonthFilter


class UnsupportedNavigation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    status: Literal["unsupported"]


def _attribution_json_schema(schema: dict[str, Any]) -> None:
    """Publish the runtime validator's evidence states to OpenAPI consumers too."""
    names = tuple(schema["properties"])

    def condition(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {**dict.fromkeys(names, {}), **properties},
        }

    def availability(field: str, state: str) -> dict[str, Any]:
        values = (
            ("alias", "model", "provider", "router")
            if field == "requested_assignment"
            else ("value",)
        )
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {"availability": {"const": state}, **dict.fromkeys(values, {})},
        }

    fields = ("requested_assignment", "credited_model", "credited_provider")
    rules = []
    for status in ("available", "legacy", "unavailable", "partial"):
        state = "available" if status in {"available", "partial"} else "unavailable"
        required = fields if status != "partial" else ("requested_assignment",)
        expected = condition({field: availability(field, state) for field in required})
        if status == "partial":
            expected["anyOf"] = [
                condition({field: availability(field, "unavailable")}) for field in fields[1:]
            ]
        rules.append({"if": condition({"attribution_status": {"const": status}}), "then": expected})
    schema["allOf"] = rules


class UsageRequestItem(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", json_schema_extra=_attribution_json_schema
    )

    request_id: UUID
    month: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    requested_assignment: RequestedAssignment
    credited_model: ModelCredit
    credited_provider: ProviderCredit
    attribution_status: Literal["available", "partial", "unavailable", "legacy"]
    consumption: Consumption | None
    navigation: UnsupportedNavigation

    @model_validator(mode="after")
    def validate_attribution_status(self) -> UsageRequestItem:
        requested = self.requested_assignment.availability == "available"
        model = self.credited_model.availability == "available"
        provider = self.credited_provider.availability == "available"
        if self.attribution_status == "legacy":
            valid = not requested and not model and not provider
        elif self.attribution_status == "available":
            valid = requested and model and provider
        elif self.attribution_status == "partial":
            valid = requested and not (model and provider)
        else:
            valid = not requested and not model and not provider
        if not valid:
            raise ValueError("attribution status must match persisted evidence availability")
        return self


class UsageRequestsResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    filter: RequestFilter
    items: Annotated[list[UsageRequestItem], Field(max_length=1000)]
