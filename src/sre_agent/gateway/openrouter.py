"""Direct async OpenRouter Responses adapter with closed routing evidence."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast
from uuid import uuid4

import httpx
from pydantic import ValidationError

from sre_agent import _core
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
        stage, detail = _core.inspect_provider_response(body, request.model, request.provider)
        if stage == "reject":
            raise ProviderFailure(
                cast(ProviderFailureKind, detail),
                consumption=(
                    _failure_consumption(body)
                    if isinstance(body, Mapping)
                    else _empty_consumption("unavailable")
                ),
            ) from None
        if stage == "catalog_required" and not await self._catalog_confirms_selected_model(
            cast(str, detail), request
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
        return _core.confirm_provider_catalog(body, selected_model, request.model, request.provider)


def _completed_output_text(body: Mapping[str, Any]) -> str:
    text = _core.completed_openrouter_output_text(body)
    if text is None:
        raise ProviderFailure("invalid_response")
    return text


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
    return _consumption(body, failure_context=True)


def _consumption(body: Mapping[str, Any], *, failure_context: bool = False) -> Consumption:
    usage = body.get("usage")
    missing = (None, False, False)
    if usage is None:
        state: Literal["missing", "invalid", "mapping"] = "missing"
        nonempty = False
        input_fact = output_fact = total_fact = cost_fact = missing
    elif not isinstance(usage, Mapping):
        state = "invalid"
        nonempty = False
        input_fact = output_fact = total_fact = cost_fact = missing
    else:
        state = "mapping"
        nonempty = bool(usage)
        input_fact = _token_value(usage, "input_tokens", "prompt_tokens")
        output_fact = _token_value(usage, "output_tokens", "completion_tokens")
        total_fact = _token_value(usage, "total_tokens")
        cost_fact = _decimal_value(usage, "cost")

    observed_at = _observed_at(body.get("created_at")) if cost_fact[0] is not None else None
    availability, input_value, output_value, total_value, billed_usd, billing_context = (
        _core.project_openrouter_consumption(
            state,
            nonempty,
            _token_fact(input_fact),
            _token_fact(output_fact),
            _token_fact(total_fact),
            cost_fact,
            observed_at is not None,
            failure_context,
        )
    )
    pricing_context: PricingContext | None = None
    if billing_context:
        assert observed_at is not None
        observed = observed_at.isoformat().replace("+00:00", "Z")
        pricing_context = PricingContext(
            observed_at=observed_at,
            price_version=f"openrouter:{observed}",
        )
    currency: Literal["USD"] | None = "USD" if billing_context else None
    precision: Literal["exact"] | None = "exact" if billing_context else None
    return _build_consumption(
        cast(ConsumptionAvailability, availability),
        int(input_value) if input_value is not None else None,
        int(output_value) if output_value is not None else None,
        int(total_value) if total_value is not None else None,
        billed_usd,
        currency,
        precision,
        pricing_context,
    )


def _token_fact(fact: tuple[int | None, bool, bool]) -> tuple[str | None, bool, bool]:
    value, invalid, present = fact
    return (str(value) if value is not None else None, invalid, present)


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


def _error_envelope(response: httpx.Response) -> bool:
    body = _json_body(response)
    return isinstance(body, Mapping) and isinstance(body.get("error"), Mapping)


def _retry_after(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    seconds = int(value)
    return seconds if 1 <= seconds <= 999_999 else None
