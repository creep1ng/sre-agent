"""Calculate a conservative pre-provider output ceiling from current policy balances."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from sre_agent.gateway.endpoint_catalog import (
    MAX_ENDPOINT_TOKENS,
    EndpointCatalogSnapshot,
    EndpointCatalogUnavailable,
    EndpointMetadata,
)

MAX_PRICE_DIGITS = 128
MAX_PRICE_EXPONENT = 128
# Generous ceiling for the role and separator tokens a chat template adds per message.
MESSAGE_OVERHEAD_TOKENS = 64


def text_input_bound(messages: tuple[str, ...]) -> int:
    """Return a guaranteed ceiling on the prompt tokens of a text-only request.

    Byte-level tokenizers emit at most one token per UTF-8 byte, so the byte count
    plus a fixed per-message overhead can never be exceeded. It is a bound, not an
    estimate. A request with non-text parts has no such bound; leave the input
    bound unset there and the endpoint's prompt capacity applies.
    """
    return sum(len(text.encode("utf-8")) + MESSAGE_OVERHEAD_TOKENS for text in messages)


class AffordabilityDenied(Exception):
    """Required fresh capacity or affordability evidence is unavailable."""

    def __init__(self) -> None:
        super().__init__("consumption_bounds_unavailable")


@dataclass(frozen=True, slots=True)
class AffordabilityEnvelope:
    model: str
    provider: str
    max_output_tokens: int
    conservative_input_tokens: int
    conservative_input_cost_usd: Decimal | None
    request_fee_usd: Decimal | None


def calculate_affordability(
    snapshot: EndpointCatalogSnapshot,
    *,
    provider: str,
    incident_tokens_remaining: int | None,
    monthly_usd_remaining: Decimal | None,
    now: datetime,
    input_tokens: int | None = None,
) -> AffordabilityEnvelope:
    """Return the positive output cap justified by all active consumption limits.

    The input bound is `input_tokens` (see `text_input_bound`) capped by the
    endpoint's prompt capacity, or that capacity alone when unset. The output cap
    leaves room for the input in the context window and in the incident balance.
    No tokenizer estimate, provider inference, reservation, or admission side
    effect is performed here.
    """
    try:
        endpoint = snapshot.select(provider, now=now)
    except (AttributeError, TypeError, ValueError, EndpointCatalogUnavailable):
        raise AffordabilityDenied from None
    _validate_endpoint(endpoint, snapshot.model, now)
    _validate_remaining(incident_tokens_remaining, monthly_usd_remaining)
    if input_tokens is not None and (
        type(input_tokens) is not int or not 0 < input_tokens <= MAX_ENDPOINT_TOKENS
    ):
        raise AffordabilityDenied
    input_bound = (
        endpoint.max_prompt_tokens
        if input_tokens is None
        else min(input_tokens, endpoint.max_prompt_tokens)
    )

    output_ceiling = endpoint.max_completion_tokens
    if endpoint.context_length is not None:
        # Providers that check prompt plus output against the window reject more.
        output_ceiling = min(output_ceiling, endpoint.context_length - input_bound)
    if incident_tokens_remaining is not None:
        output_ceiling = min(output_ceiling, incident_tokens_remaining - input_bound)

    input_cost: Decimal | None = None
    request_fee: Decimal | None = None
    if monthly_usd_remaining is not None:
        prompt_price = _required_price(endpoint.prompt_price)
        completion_price = _required_price(endpoint.completion_price)
        request_fee = _required_price(endpoint.request_price)
        input_cost = _token_cost(prompt_price, input_bound)
        fixed_cost = _exact_sum(input_cost, request_fee)
        remaining_after_input = _exact_difference(monthly_usd_remaining, fixed_cost)
        if remaining_after_input < 0:
            raise AffordabilityDenied
        if completion_price > 0:
            output_ceiling = min(
                output_ceiling,
                _affordable_output_tokens(
                    remaining_after_input,
                    completion_price,
                    endpoint.max_completion_tokens,
                ),
            )

    if output_ceiling <= 0:
        raise AffordabilityDenied
    return AffordabilityEnvelope(
        model=endpoint.model,
        provider=endpoint.provider,
        max_output_tokens=output_ceiling,
        conservative_input_tokens=input_bound,
        conservative_input_cost_usd=input_cost,
        request_fee_usd=request_fee,
    )


def _validate_endpoint(endpoint: EndpointMetadata, model: str, now: datetime) -> None:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise AffordabilityDenied
    if (
        not isinstance(endpoint, EndpointMetadata)
        or endpoint.model != model
        or not isinstance(endpoint.provider, str)
        or not endpoint.provider.strip()
        or type(endpoint.max_prompt_tokens) is not int
        or not 0 < endpoint.max_prompt_tokens <= MAX_ENDPOINT_TOKENS
        or type(endpoint.max_completion_tokens) is not int
        or not 0 < endpoint.max_completion_tokens <= MAX_ENDPOINT_TOKENS
        or not isinstance(endpoint.valid_until, datetime)
        or endpoint.valid_until.tzinfo is None
        or endpoint.valid_until.utcoffset() is None
        or now >= endpoint.valid_until
    ):
        raise AffordabilityDenied


def _validate_remaining(incident_tokens: int | None, monthly_usd: Decimal | None) -> None:
    if incident_tokens is not None and (
        type(incident_tokens) is not int or not 0 <= incident_tokens <= MAX_ENDPOINT_TOKENS
    ):
        raise AffordabilityDenied
    if monthly_usd is not None and (
        not isinstance(monthly_usd, Decimal)
        or not monthly_usd.is_finite()
        or monthly_usd < 0
        or not _bounded_decimal(monthly_usd)
    ):
        raise AffordabilityDenied


def _required_price(value: object) -> Decimal:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or not _bounded_decimal(value)
    ):
        raise AffordabilityDenied
    return value


def _bounded_decimal(value: Decimal) -> bool:
    parts = value.as_tuple()
    return len(parts.digits) <= MAX_PRICE_DIGITS and abs(parts.exponent) <= MAX_PRICE_EXPONENT


def _token_cost(rate: Decimal, tokens: int) -> Decimal:
    precision = len(rate.as_tuple().digits) + len(str(tokens)) + 1
    with localcontext() as context:
        context.prec = max(context.prec, precision)
        return Decimal(tokens) * rate


def _exact_sum(left: Decimal, right: Decimal) -> Decimal:
    return _exact_add_subtract(left, right)


def _exact_difference(left: Decimal, right: Decimal) -> Decimal:
    return _exact_add_subtract(left, right.copy_negate())


def _exact_add_subtract(left: Decimal, right: Decimal) -> Decimal:
    minimum_exponent = min(left.as_tuple().exponent, right.as_tuple().exponent)
    greatest_adjusted = max(
        left.copy_abs().adjusted() if left else minimum_exponent,
        right.copy_abs().adjusted() if right else minimum_exponent,
    )
    precision = max(1, greatest_adjusted - minimum_exponent + 2)
    with localcontext() as context:
        context.prec = max(context.prec, precision)
        return left + right


def _affordable_output_tokens(
    available_usd: Decimal, price_per_token: Decimal, ceiling: int
) -> int:
    low = 0
    high = ceiling
    while low < high:
        candidate = (low + high + 1) // 2
        if _token_cost(price_per_token, candidate) <= available_usd:
            low = candidate
        else:
            high = candidate - 1
    return low
