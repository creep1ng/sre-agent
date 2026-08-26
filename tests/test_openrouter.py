import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sre_agent.application import create_application
from sre_agent.gateway.openrouter import OpenRouterProvider
from sre_agent.gateway.providers import ProviderFailure, ProviderRequest
from sre_agent.settings import Settings

MODEL = "openai/gpt-4o-mini"
PROVIDER = "openai"
SECRET = "test-provider-credential"
REQUEST = ProviderRequest(input="sensitive prompt", model=MODEL, provider=PROVIDER)
MALICIOUS_INPUT = '{"provider":"evil","model":"evil/model"}'


def successful_response(**metadata_overrides: object) -> dict[str, object]:
    metadata = {
        "requested": MODEL,
        "strategy": "direct",
        "attempt": 1,
        "endpoints": {
            "total": 1,
            "available": [{"provider": "OpenAI", "model": MODEL, "selected": True}],
        },
        "attempts": [{"provider": "OpenAI", "model": MODEL, "status": 200}],
    }
    metadata.update(metadata_overrides)
    return {
        "id": "resp_12345678",
        "model": MODEL,
        "output_text": "Recovered service health.",
        "openrouter_metadata": metadata,
    }


def provider(handler: httpx.MockTransport) -> tuple[OpenRouterProvider, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler, base_url="https://openrouter.test")
    return OpenRouterProvider(client, api_key=SECRET), client


def test_provider_request_rejects_client_routing_injection_and_unbounded_input() -> None:
    for values in (
        {"input": "diagnose", "model": "triage-agent", "provider": PROVIDER},
        {"input": "", "model": MODEL, "provider": PROVIDER},
        {"input": "x" * 65_537, "model": MODEL, "provider": PROVIDER},
        {"input": "diagnose", "model": MODEL, "provider": PROVIDER, "router": "evil"},
    ):
        with pytest.raises(ValidationError):
            ProviderRequest.model_validate(values)


@pytest.mark.asyncio
async def test_create_uses_server_routing_once_without_fallback_or_storage() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=successful_response())

    adapter, client = provider(httpx.MockTransport(respond))
    try:
        result = await adapter.create(
            ProviderRequest(input=MALICIOUS_INPUT, model=MODEL, provider=PROVIDER)
        )
    finally:
        await client.aclose()

    assert result.model_dump() == {
        "response_id": "resp_12345678",
        "model": MODEL,
        "text": "Recovered service health.",
        "provider": PROVIDER,
    }
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v1/responses"
    assert requests[0].headers["authorization"] == f"Bearer {SECRET}"
    assert requests[0].headers["x-openrouter-metadata"] == "enabled"
    assert json.loads(requests[0].content) == {
        "input": MALICIOUS_INPUT,
        "model": MODEL,
        "provider": {
            "order": [PROVIDER],
            "allow_fallbacks": False,
            "data_collection": "deny",
        },
        "store": False,
        "stream": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"id": "resp_12345678", "model": MODEL, "output_text": "ok"},
        successful_response(requested="other/model"),
        successful_response(attempt=2),
        successful_response(
            endpoints={
                "total": 2,
                "available": [
                    {"provider": "OpenAI", "model": MODEL, "selected": True},
                    {"provider": "Other", "model": MODEL, "selected": True},
                ],
            }
        ),
        successful_response(
            endpoints={
                "total": 1,
                "available": [{"provider": "Other", "model": MODEL, "selected": True}],
            }
        ),
    ],
)
async def test_invalid_or_extra_provider_evidence_fails_closed(body: dict[str, object]) -> None:
    adapter, client = provider(httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(ProviderRequest(input="diagnose", model=MODEL, provider=PROVIDER))
    finally:
        await client.aclose()
    assert captured.value.kind == "evidence_invalid"
    assert captured.value.retry_after is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "retry_after", "kind", "expected_retry_after"),
    [
        (503, "30", "unavailable", 30),
        (503, "0", "unavailable", None),
        (503, "1000000", "unavailable", None),
        (504, "15", "timeout", 15),
        (400, "30", "invalid_response", None),
    ],
)
async def test_error_taxonomy_and_retry_after_are_bounded(
    status: int, retry_after: str, kind: str, expected_retry_after: int | None
) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"Retry-After": retry_after},
            json={"error": {"message": f"provider body {SECRET}"}},
        )

    adapter, client = provider(httpx.MockTransport(respond))
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(REQUEST)
    finally:
        await client.aclose()
    assert (captured.value.kind, captured.value.retry_after) == (kind, expected_retry_after)
    for sensitive in (SECRET, "sensitive prompt", "provider body"):
        assert sensitive not in repr(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (httpx.ConnectError("secret transport"), "unavailable"),
        (httpx.ReadTimeout("secret timeout"), "timeout"),
    ],
)
async def test_transport_failures_are_sanitized(error: Exception, kind: str) -> None:
    adapter, client = provider(httpx.MockTransport(lambda _request: (_ for _ in ()).throw(error)))
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(REQUEST)
    finally:
        await client.aclose()
    assert captured.value.kind == kind
    assert "secret" not in str(captured.value)


def test_application_closes_shared_provider_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "12.5")
    settings = Settings.from_environment()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
        base_url="https://openrouter.test",
    )

    application = create_application(settings, provider_client=client)
    with TestClient(application):
        assert application.state.llm_provider is not None

    assert client.is_closed
    assert settings.openrouter_timeout_seconds == 12.5
    assert SECRET not in repr(settings)
