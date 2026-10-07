"""HTTP contract tests for separately authenticated endpoint metadata retrieval."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gateway.endpoint_catalog import (
    EndpointCatalogSnapshot,
    EndpointCatalogUnavailable,
    OpenRouterEndpointCatalog,
)
from sre_agent.settings import Settings

MODEL = "openai/gpt-4o-mini"
PROVIDER_KEY = "provider-key-not-management-key"
MANAGEMENT_KEY = "management-key-separate-from-provider-key"
NOW = datetime(2026, 9, 28, tzinfo=UTC)


def _body(endpoints: list[dict[str, Any]] | None = None, *, model: str = MODEL) -> dict[str, Any]:
    return {
        "data": {
            "id": model,
            "endpoints": endpoints
            if endpoints is not None
            else [
                {
                    "provider_name": "OpenAI",
                    "max_prompt_tokens": 128_000,
                    "max_completion_tokens": 16_384,
                    "pricing": {
                        "prompt": "0.00000015",
                        "completion": "0.0000006",
                        "request": "0",
                    },
                },
                {
                    "provider_name": "Anthropic",
                    "max_prompt_tokens": 200_000,
                    "max_completion_tokens": 8_192,
                    "pricing": {},
                },
            ],
        }
    }


def _catalog(
    handler: Callable[[httpx.Request], httpx.Response], *, freshness_seconds: int = 60
) -> tuple[OpenRouterEndpointCatalog, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        base_url="https://openrouter.test",
        transport=httpx.MockTransport(handler),
    )
    return (
        OpenRouterEndpointCatalog(
            client,
            management_key=MANAGEMENT_KEY,
            clock=lambda: NOW,
            freshness_seconds=freshness_seconds,
        ),
        client,
    )


def test_settings_keep_provider_and_management_keys_independent_and_secret() -> None:
    settings = Settings.from_environment(
        {
            "DATABASE_URL": "postgresql://unused",
            "OPENROUTER_API_KEY": PROVIDER_KEY,
            "OPENROUTER_MANAGEMENT_API_KEY": MANAGEMENT_KEY,
        }
    )
    assert settings.openrouter_api_key == PROVIDER_KEY
    assert settings.openrouter_management_key == MANAGEMENT_KEY
    assert PROVIDER_KEY not in repr(settings)
    assert MANAGEMENT_KEY not in repr(settings)

    provider_only = Settings.from_environment(
        {"DATABASE_URL": "postgresql://unused", "OPENROUTER_API_KEY": PROVIDER_KEY}
    )
    assert provider_only.openrouter_management_key is None
    application = create_application(settings)
    assert isinstance(application.state.endpoint_catalog, OpenRouterEndpointCatalog)
    with TestClient(application):
        pass


@pytest.mark.asyncio
async def test_catalog_retrieves_and_selects_unique_provider_with_management_key() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_body())

    catalog, client = _catalog(respond)
    try:
        snapshot = await catalog.fetch(MODEL)
        selected = snapshot.select("openai", now=NOW)
    finally:
        await client.aclose()

    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.raw_path == b"/api/v1/models/openai%2Fgpt-4o-mini/endpoints"
    assert seen[0].headers["Authorization"] == f"Bearer {MANAGEMENT_KEY}"
    assert selected.model == MODEL
    assert selected.provider == "OpenAI"
    assert selected.max_prompt_tokens == 128_000
    assert selected.max_completion_tokens == 16_384
    assert selected.prompt_price == Decimal("0.00000015")
    assert selected.completion_price == Decimal("0.0000006")
    assert selected.request_price == Decimal("0")
    assert selected.valid_until == NOW + timedelta(seconds=60)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"data": {"id": "other/model", "endpoints": []}}),
        httpx.Response(200, json={"data": {"id": MODEL}}),
        httpx.Response(200, json={"data": {"id": MODEL, "endpoints": [None]}}),
        httpx.Response(
            200,
            json=_body(
                [
                    {
                        "provider_name": "OpenAI",
                        "max_prompt_tokens": True,
                        "max_completion_tokens": 12,
                    }
                ]
            ),
        ),
        httpx.Response(200, json=_body([{"provider_name": "OpenAI"}])),
    ],
)
async def test_catalog_rejects_unavailable_or_malformed_results(
    response: httpx.Response,
) -> None:
    catalog, client = _catalog(lambda _request: response)
    try:
        with pytest.raises(EndpointCatalogUnavailable):
            await catalog.fetch(MODEL)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_catalog_rejects_transport_failure_without_leaking_transport_detail() -> None:
    catalog, client = _catalog(
        lambda _request: (_ for _ in ()).throw(httpx.ConnectError(MANAGEMENT_KEY))
    )
    try:
        with pytest.raises(EndpointCatalogUnavailable) as captured:
            await catalog.fetch(MODEL)
    finally:
        await client.aclose()
    assert MANAGEMENT_KEY not in str(captured.value)


@pytest.mark.asyncio
async def test_catalog_selection_fails_closed_on_missing_or_ambiguous_provider() -> None:
    duplicate = _body(
        [
            {
                "provider_name": "OpenAI",
                "max_prompt_tokens": 10,
                "max_completion_tokens": 5,
            },
            {
                "provider_name": "openai",
                "max_prompt_tokens": 20,
                "max_completion_tokens": 10,
            },
        ]
    )
    catalog, client = _catalog(lambda _request: httpx.Response(200, json=duplicate))
    try:
        snapshot = await catalog.fetch(MODEL)
        with pytest.raises(EndpointCatalogUnavailable):
            snapshot.select("openai", now=NOW)
        with pytest.raises(EndpointCatalogUnavailable):
            snapshot.select("anthropic", now=NOW)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_catalog_selection_rejects_expired_snapshot() -> None:
    catalog, client = _catalog(lambda _request: httpx.Response(200, json=_body()))
    try:
        snapshot: EndpointCatalogSnapshot = await catalog.fetch(MODEL)
    finally:
        await client.aclose()
    with pytest.raises(EndpointCatalogUnavailable):
        snapshot.select("openai", now=NOW + timedelta(seconds=60))
