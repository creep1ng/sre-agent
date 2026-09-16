"""Direct async OpenRouter Responses adapter with closed routing evidence."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from re import fullmatch
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import ValidationError

from sre_agent.gateway.providers import (
    ProviderFailure,
    ProviderFailureKind,
    ProviderRequest,
    ProviderResult,
)
from sre_agent.governance.dto import Consumption, PricingContext

ConsumptionAvailability = Literal["complete", "partial", "absent", "unavailable"]


class OpenRouterProvider:
    def __init__(self, client: httpx.AsyncClient, *, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def create(self, request: ProviderRequest) -> ProviderResult:
        try:
            response = await self._client.post(
                "/api/v1/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "X-OpenRouter-Metadata": "enabled",
                },
                json={
                    "input": request.input,
                    "model": request.model,
                    "provider": {
                        "order": [request.provider],
                        "allow_fallbacks": False,
                        "data_collection": "deny",
                    },
                    "store": False,
                    "stream": False,
                },
            )
        except httpx.TimeoutException:
            raise ProviderFailure(
                "timeout", consumption=_empty_consumption("unavailable")
            ) from None
        except httpx.TransportError:
            raise ProviderFailure(
                "unavailable", consumption=_empty_consumption("unavailable")
            ) from None

        retry_after = _retry_after(response.headers.get("Retry-After"))
        if response.status_code in {408, 504}:
            raise _failure("timeout", response, retry_after=retry_after)
        if response.status_code in {429, 500, 502, 503, 529}:
            raise _failure("unavailable", response, retry_after=retry_after)
        if response.status_code == 404 and _error_envelope(response):
            # A documented OpenRouter 404 can mean that provider selection
            # produced no eligible endpoint. It is a routing availability
            # failure, not malformed provider output (issue #204).
            raise _failure("unavailable", response, retry_after=retry_after)
        if not response.is_success:
            raise _failure("invalid_response", response)

        body = _json_body(response)
        if not isinstance(body, Mapping):
            raise ProviderFailure("invalid_response", consumption=_empty_consumption("unavailable"))
        if (
            not _generation_id(body.get("id"))
            or body.get("model") != request.model
            or body.get("error") is not None
            or body.get("incomplete_details") is not None
        ):
            raise ProviderFailure("invalid_response", consumption=_failure_consumption(body))
        try:
            selected_model = _selected_model(body.get("openrouter_metadata"), request)
        except ProviderFailure as failure:
            raise ProviderFailure(
                failure.kind,
                retry_after=failure.retry_after,
                consumption=_failure_consumption(body),
            ) from None
        if selected_model != request.model and not await self._catalog_confirms_selected_model(
            selected_model, request
        ):
            raise ProviderFailure("evidence_invalid", consumption=_failure_consumption(body))
        try:
            return ProviderResult(
                # OpenRouter Responses uses generation IDs (for example,
                # ``gen-...``). Keep the public contract independent of that
                # vendor identifier and never use an upstream value as ours.
                response_id=f"resp_{uuid4().hex}",
                model=request.model,
                text=_completed_output_text(body),
                provider=request.provider,
                consumption=_consumption(body),
            )
        except ProviderFailure as failure:
            raise ProviderFailure(
                failure.kind,
                retry_after=failure.retry_after,
                consumption=_failure_consumption(body),
            ) from None
        except ValidationError:
            raise ProviderFailure(
                "invalid_response", consumption=_failure_consumption(body)
            ) from None

    async def _catalog_confirms_selected_model(
        self, selected_model: str, request: ProviderRequest
    ) -> bool:
        """Confirm a documented alias-to-canonical endpoint identity exactly once.

        The successful-router metadata is authoritative for the selected
        provider, but OpenRouter may resolve a requested alias to a dated
        canonical model. Accept that drift only when the model's public
        endpoint catalog independently records the exact provider/model pair.
        This avoids unsafe suffix trimming and still rejects implicit
        fallbacks.
        """
        try:
            response = await self._client.get(
                f"/api/v1/models/{request.model}/endpoints",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            body = response.json() if response.is_success else None
        except (ValueError, httpx.HTTPError):
            return False
        return _catalog_match(body, selected_model, request)


def _selected_model(metadata: Any, request: ProviderRequest) -> str:
    if not isinstance(metadata, Mapping):
        raise ProviderFailure("evidence_invalid")
    endpoints = metadata.get("endpoints")
    available = endpoints.get("available") if isinstance(endpoints, Mapping) else None
    selected = (
        [item for item in available if isinstance(item, Mapping) and item.get("selected") is True]
        if isinstance(available, list)
        else []
    )
    evidence = selected[0] if len(selected) == 1 else {}
    attempts = metadata.get("attempts")
    valid_attempts = attempts is None or (
        isinstance(attempts, list)
        and len(attempts) == 1
        and _matches_provider(attempts[0], request)
        and attempts[0].get("model") == evidence.get("model")
        and attempts[0].get("status") == 200
    )
    if not (
        metadata.get("requested") == request.model
        and metadata.get("strategy") == "direct"
        and metadata.get("attempt") == 1
        and _matches_provider(evidence, request)
        and valid_attempts
    ):
        raise ProviderFailure("evidence_invalid")
    model = evidence.get("model") if isinstance(evidence, Mapping) else None
    if not isinstance(model, str):
        raise ProviderFailure("evidence_invalid")
    return model


def _matches_provider(evidence: Any, request: ProviderRequest) -> bool:
    return (
        isinstance(evidence, Mapping)
        and isinstance(evidence.get("provider"), str)
        and evidence["provider"].casefold() == request.provider.casefold()
    )


def _catalog_match(body: Any, selected_model: str, request: ProviderRequest) -> bool:
    data = body.get("data") if isinstance(body, Mapping) else None
    endpoints = data.get("endpoints") if isinstance(data, Mapping) else None
    if (
        not isinstance(data, Mapping)
        or data.get("id") != request.model
        or not isinstance(endpoints, list)
    ):
        return False
    candidates = []
    for endpoint in endpoints:
        if not isinstance(endpoint, Mapping):
            continue
        provider_name = endpoint.get("provider_name")
        tag = endpoint.get("tag")
        if not isinstance(provider_name, str) or not isinstance(tag, str):
            continue
        if (
            endpoint.get("model_id") == request.model
            and provider_name.casefold() == request.provider.casefold()
            and (tag == request.provider or tag.startswith(f"{request.provider}/"))
            and endpoint.get("name") == f"{provider_name} | {selected_model}"
        ):
            candidates.append(endpoint)
    return len(candidates) == 1


def _completed_output_text(body: Mapping[str, Any]) -> str:
    if body.get("status") != "completed" or not isinstance(body.get("output"), list):
        raise ProviderFailure("invalid_response")
    text: list[str] = []
    for item in body["output"]:
        if not (
            isinstance(item, Mapping)
            and item.get("type") == "message"
            and item.get("role") == "assistant"
            and item.get("status") == "completed"
            and isinstance(item.get("content"), list)
        ):
            continue
        for content in item["content"]:
            if (
                isinstance(content, Mapping)
                and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ):
                text.append(content["text"])
    if not text:
        raise ProviderFailure("invalid_response")
    return "\n".join(text)


def _json_body(response: httpx.Response) -> Any:
    try:
        return json.loads(
            response.content,
            parse_float=_parse_decimal,
            parse_constant=Decimal,
        )
    except (TypeError, ValueError):
        return None


def _parse_decimal(value: str) -> Decimal | str:
    try:
        return Decimal(value)
    except InvalidOperation:
        return value


def _failure(
    kind: ProviderFailureKind,
    response: httpx.Response,
    *,
    retry_after: int | None = None,
) -> ProviderFailure:
    body = _json_body(response)
    consumption = (
        _failure_consumption(body)
        if isinstance(body, Mapping)
        else _empty_consumption("unavailable")
    )
    return ProviderFailure(
        kind,
        retry_after=retry_after,
        consumption=consumption,
    )


def _failure_consumption(body: Mapping[str, Any]) -> Consumption:
    consumption = _consumption(body)
    return (
        _empty_consumption("unavailable") if consumption.availability == "absent" else consumption
    )


def _consumption(body: Mapping[str, Any]) -> Consumption:
    usage = body.get("usage")
    if usage is None:
        return _empty_consumption("absent")
    if not isinstance(usage, Mapping):
        return _empty_consumption("unavailable")

    input_tokens, input_invalid, input_present = _token_value(
        usage, "input_tokens", "prompt_tokens"
    )
    output_tokens, output_invalid, output_present = _token_value(
        usage, "output_tokens", "completion_tokens"
    )
    total_tokens, total_invalid, total_present = _token_value(usage, "total_tokens")
    billed_usd, cost_invalid, cost_present = _decimal_value(usage, "cost")
    invalid = input_invalid or output_invalid or total_invalid or cost_invalid
    if (
        input_tokens is not None
        and output_tokens is not None
        and total_tokens is not None
        and total_tokens != input_tokens + output_tokens
    ):
        total_tokens, invalid = None, True

    pricing_context: PricingContext | None = None
    if billed_usd is not None:
        observed_at = _observed_at(body.get("created_at"))
        if observed_at is None:
            billed_usd, cost_invalid = None, True
        else:
            observed = observed_at.isoformat().replace("+00:00", "Z")
            pricing_context = PricingContext(
                observed_at=observed_at,
                price_version=f"openrouter:{observed}",
            )

    has_values = any(
        value is not None for value in (input_tokens, output_tokens, total_tokens, billed_usd)
    )
    known_evidence = any((input_present, output_present, total_present, cost_present))
    availability: ConsumptionAvailability
    if not has_values:
        availability = "unavailable" if invalid or known_evidence or bool(usage) else "absent"
    else:
        currency: Literal["USD"] | None = "USD" if billed_usd is not None else None
        precision: Literal["exact"] | None = "exact" if billed_usd is not None else None
        complete = all(
            value is not None
            for value in (
                input_tokens,
                output_tokens,
                total_tokens,
                billed_usd,
                currency,
                precision,
                pricing_context,
            )
        )
        availability = "complete" if complete and not invalid else "partial"
        return _build_consumption(
            availability,
            input_tokens,
            output_tokens,
            total_tokens,
            billed_usd,
            currency,
            precision,
            pricing_context,
        )
    return _empty_consumption(availability)


def _build_consumption(
    availability: ConsumptionAvailability,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    billed_usd: str | None,
    currency: Literal["USD"] | None,
    precision: Literal["exact"] | None,
    pricing_context: PricingContext | None,
) -> Consumption:
    return Consumption(
        availability=availability,
        source="openrouter",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        billed_usd=billed_usd,
        currency=currency,
        precision=precision,
        pricing_context=pricing_context,
    )


def _empty_consumption(availability: ConsumptionAvailability) -> Consumption:
    return _build_consumption(availability, None, None, None, None, None, None, None)


def _token_value(usage: Mapping[str, Any], *names: str) -> tuple[int | None, bool, bool]:
    values = [usage[name] for name in names if name in usage]
    if not values:
        return None, False, False
    if any(type(value) is not int or value < 0 for value in values):
        return None, True, True
    value = values[0]
    if len(values) > 1 and any(value != values[0] for value in values[1:]):
        return None, True, True
    return value, False, True


def _decimal_value(usage: Mapping[str, Any], *names: str) -> tuple[str | None, bool, bool]:
    values = [usage[name] for name in names if name in usage]
    if not values:
        return None, False, False
    if len(values) > 1 and any(value != values[0] for value in values[1:]):
        return None, True, True
    try:
        value = Decimal(str(values[0]))
    except (InvalidOperation, ValueError):
        return None, True, True
    if not value.is_finite() or value.is_signed() or value < 0:
        return None, True, True
    digits = value.as_tuple().digits
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        return None, True, True
    integer_digits = len(digits) + exponent
    if exponent >= 0:
        rendered_length = len(digits) + exponent
    elif integer_digits > 0:
        rendered_length = len(digits) + 1
    else:
        rendered_length = 2 - integer_digits + len(digits)
    if rendered_length > 64:
        return None, True, True
    rendered = format(value, "f")
    return rendered, False, True


def _observed_at(value: Any) -> datetime | None:
    if type(value) is int:
        try:
            return datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


def _generation_id(value: Any) -> bool:
    return isinstance(value, str) and fullmatch(r"gen-[A-Za-z0-9_-]{8,128}", value) is not None


def _error_envelope(response: httpx.Response) -> bool:
    body = _json_body(response)
    return isinstance(body, Mapping) and isinstance(body.get("error"), Mapping)


def _retry_after(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    seconds = int(value)
    return seconds if 1 <= seconds <= 999_999 else None
