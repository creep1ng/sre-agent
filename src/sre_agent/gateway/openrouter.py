"""Direct async OpenRouter Responses adapter with closed routing evidence."""

from collections.abc import Mapping
from re import fullmatch
from typing import Any
from uuid import uuid4

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
        if response.status_code == 404 and _error_envelope(response):
            # A documented OpenRouter 404 can mean that provider selection
            # produced no eligible endpoint. It is a routing availability
            # failure, not malformed provider output (issue #204).
            raise ProviderFailure("unavailable", retry_after=retry_after)
        if not response.is_success:
            raise ProviderFailure("invalid_response")

        try:
            body = response.json()
        except ValueError:
            raise ProviderFailure("invalid_response") from None
        if not isinstance(body, Mapping):
            raise ProviderFailure("invalid_response")
        if (
            not _generation_id(body.get("id"))
            or body.get("model") != request.model
            or body.get("error") is not None
            or body.get("incomplete_details") is not None
        ):
            raise ProviderFailure("invalid_response")
        selected_model = _selected_model(body.get("openrouter_metadata"), request)
        if selected_model != request.model and not await self._catalog_confirms_selected_model(
            selected_model, request
        ):
            raise ProviderFailure("evidence_invalid")
        try:
            return ProviderResult(
                # OpenRouter Responses uses generation IDs (for example,
                # ``gen-...``). Keep the public contract independent of that
                # vendor identifier and never use an upstream value as ours.
                response_id=f"resp_{uuid4().hex}",
                model=body.get("model"),
                text=_completed_output_text(body),
                provider=request.provider,
            )
        except ValidationError:
            raise ProviderFailure("invalid_response") from None

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
    text = [
        content.get("text")
        for item in body["output"]
        if (
            isinstance(item, Mapping)
            and item.get("type") == "message"
            and item.get("role") == "assistant"
            and item.get("status") == "completed"
            and isinstance(item.get("content"), list)
        )
        for content in item["content"]
        if (
            isinstance(content, Mapping)
            and content.get("type") == "output_text"
            and isinstance(content.get("text"), str)
        )
    ]
    if not text:
        raise ProviderFailure("invalid_response")
    return "\n".join(text)


def _generation_id(value: Any) -> bool:
    return isinstance(value, str) and fullmatch(r"gen-[A-Za-z0-9_-]{8,128}", value) is not None


def _error_envelope(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, Mapping) and isinstance(body.get("error"), Mapping)


def _retry_after(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    seconds = int(value)
    return seconds if 1 <= seconds <= 999_999 else None
