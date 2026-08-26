"""Direct async OpenRouter Responses adapter with closed routing evidence."""

from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError

from sre_agent.gateway.providers import ProviderFailure, ProviderRequest, ProviderResult


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
            raise ProviderFailure("timeout") from None
        except httpx.TransportError:
            raise ProviderFailure("unavailable") from None

        retry_after = _retry_after(response.headers.get("Retry-After"))
        if response.status_code in {408, 504}:
            raise ProviderFailure("timeout", retry_after=retry_after)
        if response.status_code in {429, 500, 502, 503, 529}:
            raise ProviderFailure("unavailable", retry_after=retry_after)
        if not response.is_success:
            raise ProviderFailure("invalid_response")

        try:
            body = response.json()
        except ValueError:
            raise ProviderFailure("invalid_response") from None
        if not isinstance(body, Mapping):
            raise ProviderFailure("invalid_response")
        provider = _selected_provider(body.get("openrouter_metadata"), request)
        try:
            return ProviderResult(
                response_id=body.get("id"),
                model=body.get("model"),
                text=body.get("output_text"),
                provider=provider,
            )
        except ValidationError:
            raise ProviderFailure("invalid_response") from None


def _selected_provider(metadata: Any, request: ProviderRequest) -> str:
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
        and _matches(attempts[0], request)
        and attempts[0].get("status") == 200
    )
    if not (
        metadata.get("requested") == request.model
        and metadata.get("strategy") == "direct"
        and metadata.get("attempt") == 1
        and _matches(evidence, request)
        and valid_attempts
    ):
        raise ProviderFailure("evidence_invalid")
    return request.provider


def _matches(evidence: Any, request: ProviderRequest) -> bool:
    return (
        isinstance(evidence, Mapping)
        and evidence.get("model") == request.model
        and isinstance(evidence.get("provider"), str)
        and evidence["provider"].casefold() == request.provider.casefold()
    )


def _retry_after(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    seconds = int(value)
    return seconds if 1 <= seconds <= 999_999 else None
