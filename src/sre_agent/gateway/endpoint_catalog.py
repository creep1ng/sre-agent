"""Safely retrieve and select OpenRouter endpoint capability metadata."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx

MAX_ENDPOINT_TOKENS = 9_223_372_036_854_775_807


class EndpointCatalogUnavailable(Exception):
    """The endpoint catalog could not provide fresh, unambiguous metadata."""

    def __init__(self) -> None:
        super().__init__("openrouter_endpoint_catalog_unavailable")


@dataclass(frozen=True, slots=True)
class EndpointMetadata:
    model: str
    provider: str
    max_prompt_tokens: int
    max_completion_tokens: int
    valid_until: datetime
    prompt_price: Decimal | None
    completion_price: Decimal | None
    request_price: Decimal | None


@dataclass(frozen=True, slots=True)
class EndpointCatalogSnapshot:
    model: str
    endpoints: tuple[EndpointMetadata, ...]
    observed_at: datetime
    valid_until: datetime

    def select(self, provider: str, *, now: datetime) -> EndpointMetadata:
        if (
            not _aware(now)
            or not _aware(self.observed_at)
            or not _aware(self.valid_until)
            or not self.observed_at <= now < self.valid_until
            or not isinstance(provider, str)
            or not provider.strip()
        ):
            raise EndpointCatalogUnavailable
        matches = [
            endpoint
            for endpoint in self.endpoints
            if endpoint.provider.casefold() == provider.casefold()
        ]
        if len(matches) != 1:
            raise EndpointCatalogUnavailable
        return matches[0]


class OpenRouterEndpointCatalog:
    """Fetch uncached endpoint metadata using a separate management credential."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        management_key: str,
        clock=lambda: datetime.now(UTC),
        freshness_seconds: int = 60,
    ) -> None:
        if not isinstance(management_key, str) or not management_key.strip():
            raise ValueError("OpenRouter management key is required")
        if type(freshness_seconds) is not int or freshness_seconds <= 0:
            raise ValueError("catalog freshness must be positive")
        self._client = client
        self._management_key = management_key
        self._clock = clock
        self._freshness = timedelta(seconds=freshness_seconds)

    async def fetch(self, model: str) -> EndpointCatalogSnapshot:
        if not isinstance(model, str) or not model or model.strip() != model:
            raise EndpointCatalogUnavailable
        observed_at = self._clock()
        if not _aware(observed_at):
            raise EndpointCatalogUnavailable
        # OpenRouter addresses a model as `/models/{author}/{slug}/endpoints`; an
        # escaped `/` (%2F) or a bare alias answers 404.
        segments = model.split("/")
        if len(segments) != 2 or any(part in {"", ".", ".."} for part in segments):
            raise EndpointCatalogUnavailable
        try:
            response = await self._client.get(
                f"/api/v1/models/{'/'.join(quote(part, safe='') for part in segments)}/endpoints",
                headers={"Authorization": f"Bearer {self._management_key}"},
            )
            if not response.is_success:
                raise EndpointCatalogUnavailable
            body = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            raise EndpointCatalogUnavailable from None

        data = body.get("data") if isinstance(body, Mapping) else None
        if not isinstance(data, Mapping) or data.get("id") != model:
            raise EndpointCatalogUnavailable
        raw_endpoints = data.get("endpoints")
        if not isinstance(raw_endpoints, list) or not raw_endpoints:
            raise EndpointCatalogUnavailable

        try:
            valid_until = observed_at + self._freshness
            endpoints = tuple(
                _endpoint_metadata(endpoint, model, valid_until) for endpoint in raw_endpoints
            )
        except (TypeError, ValueError):
            raise EndpointCatalogUnavailable from None
        return EndpointCatalogSnapshot(
            model=model,
            endpoints=endpoints,
            observed_at=observed_at,
            valid_until=valid_until,
        )


def _endpoint_metadata(raw: object, model: str, valid_until: datetime) -> EndpointMetadata:
    if not isinstance(raw, Mapping):
        raise ValueError
    provider = raw.get("provider_name")
    # OpenRouter reports `max_prompt_tokens: null` for most endpoints. Neither the
    # prompt nor the completion can exceed the context window, so the context length
    # is the conservative bound for a missing cap.
    context_length = raw.get("context_length")
    prompt_tokens = raw.get("max_prompt_tokens")
    if prompt_tokens is None:
        prompt_tokens = context_length
    completion_tokens = raw.get("max_completion_tokens")
    if completion_tokens is None:
        completion_tokens = context_length
    if (
        not isinstance(provider, str)
        or not provider.strip()
        or type(prompt_tokens) is not int
        or not 0 < prompt_tokens <= MAX_ENDPOINT_TOKENS
        or type(completion_tokens) is not int
        or not 0 < completion_tokens <= MAX_ENDPOINT_TOKENS
    ):
        raise ValueError
    pricing = raw.get("pricing", {})
    if not isinstance(pricing, Mapping):
        raise ValueError
    return EndpointMetadata(
        model=model,
        provider=provider,
        max_prompt_tokens=prompt_tokens,
        max_completion_tokens=completion_tokens,
        valid_until=valid_until,
        prompt_price=_price(pricing.get("prompt")),
        completion_price=_price(pricing.get("completion")),
        # A null or absent per-request fee means the endpoint charges none; prompt and
        # completion prices stay required, so their absence still fails closed.
        request_price=_price(pricing.get("request")) or Decimal(0),
    )


def _price(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError
    try:
        price = Decimal(value)
    except InvalidOperation:
        raise ValueError from None
    if not price.is_finite() or price < 0:
        raise ValueError
    return price


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )
