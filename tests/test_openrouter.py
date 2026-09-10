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


def successful_response(**overrides: object) -> dict[str, object]:
    root_keys = {
        "id",
        "model",
        "status",
        "output",
        "error",
        "incomplete_details",
        "usage",
        "created_at",
    }
    root_overrides = {name: value for name, value in overrides.items() if name in root_keys}
    metadata_overrides = {name: value for name, value in overrides.items() if name not in root_keys}
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
    response = {
        "id": "gen-12345678",
        "model": MODEL,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Recovered service health."}],
            }
        ],
        "openrouter_metadata": metadata,
    }
    response.update(root_overrides)
    return response


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

    assert result.model == MODEL
    assert result.text == "Recovered service health."
    assert result.provider == PROVIDER
    assert result.response_id.startswith("resp_")
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
async def test_create_normalizes_openrouter_usage_and_discards_raw_body() -> None:
    body = successful_response(
        created_at=1_789_000_000,
        usage={
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
            "cost": "0.0012300",
            "raw_sensitive_provider_detail": SECRET,
        },
    )
    raw = json.dumps(body, separators=(",", ":")).replace('"cost":"0.0012300"', '"cost":0.0012300')

    adapter, client = provider(
        httpx.MockTransport(lambda _request: httpx.Response(200, content=raw.encode()))
    )
    try:
        result = await adapter.create(REQUEST)
    finally:
        await client.aclose()

    assert result.consumption is not None
    assert result.consumption.availability == "complete"
    assert result.consumption.input_tokens == 11
    assert result.consumption.output_tokens == 7
    assert result.consumption.total_tokens == 18
    assert result.consumption.billed_usd == "0.0012300"
    assert result.consumption.currency == "USD"
    assert result.consumption.precision == "exact"
    assert result.consumption.pricing_context.price_version.startswith("openrouter:")
    assert SECRET not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("usage", "availability"),
    [
        (None, "absent"),
        ({"input_tokens": 11, "cost": "0.001"}, "partial"),
        ({"input_tokens": "11", "output_tokens": "7"}, "unavailable"),
        ({"input_tokens": 11, "output_tokens": 7, "total_tokens": 17}, "partial"),
    ],
)
async def test_create_makes_missing_or_invalid_usage_explicit(
    usage: object, availability: str
) -> None:
    body = successful_response(usage=usage)
    adapter, client = provider(httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))
    try:
        result = await adapter.create(REQUEST)
    finally:
        await client.aclose()

    assert result.consumption is not None
    assert result.consumption.availability == availability
    assert result.consumption.total_tokens is None or (
        result.consumption.total_tokens
        == result.consumption.input_tokens + result.consumption.output_tokens
    )
    assert result.consumption.billed_usd is None or result.consumption.billed_usd == "0.001"


@pytest.mark.asyncio
@pytest.mark.parametrize("cost", ("1e1000000000", "1e-1000000000"))
async def test_create_rejects_extreme_cost_exponents_without_expanding_them(cost: str) -> None:
    body = successful_response(
        created_at=1_789_000_000,
        usage={
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
            "cost": cost,
        },
    )
    raw = json.dumps(body, separators=(",", ":"))
    raw = raw.replace(f'"cost":"{cost}"', f'"cost":{cost}').encode()
    adapter, client = provider(
        httpx.MockTransport(lambda _request: httpx.Response(200, content=raw))
    )
    try:
        result = await adapter.create(REQUEST)
    finally:
        await client.aclose()

    assert result.consumption is not None
    assert result.consumption.availability == "partial"
    assert result.consumption.billed_usd is None


@pytest.mark.asyncio
async def test_provider_failure_without_evidence_is_explicitly_unavailable() -> None:
    adapter, client = provider(
        httpx.MockTransport(
            lambda _request: httpx.Response(
                503,
                json={"error": {"message": f"upstream body {SECRET}"}},
            )
        )
    )
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(REQUEST)
    finally:
        await client.aclose()

    assert captured.value.consumption is not None
    assert captured.value.consumption.availability == "unavailable"
    assert SECRET not in repr(captured.value)


def catalog(
    selected_model: str,
    *,
    model: str = MODEL,
    provider: str = "OpenAI",
    tag: str = PROVIDER,
) -> dict[str, object]:
    return {
        "data": {
            "id": model,
            "endpoints": [
                {
                    "model_id": model,
                    "provider_name": provider,
                    "tag": tag,
                    "name": f"{provider} | {selected_model}",
                }
            ],
        }
    }


@pytest.mark.asyncio
async def test_create_confirms_dated_selected_model_against_the_endpoint_catalog() -> None:
    selected_model = "z-ai/glm-5.3-flash-20260826"
    request = ProviderRequest(input="diagnose", model="z-ai/glm-5.3-flash", provider="relace")
    body = successful_response(
        requested=request.model,
        endpoints={
            "total": 1,
            "available": [{"provider": "Relace", "model": selected_model, "selected": True}],
        },
        attempts=[{"provider": "Relace", "model": selected_model, "status": 200}],
    ) | {"model": request.model}
    requests: list[httpx.Request] = []

    def respond(http_request: httpx.Request) -> httpx.Response:
        requests.append(http_request)
        if http_request.method == "POST":
            return httpx.Response(200, json=body)
        return httpx.Response(
            200,
            json=catalog(
                selected_model,
                model=request.model,
                provider="Relace",
                tag="relace/fp4",
            ),
        )

    adapter, client = provider(httpx.MockTransport(respond))
    try:
        result = await adapter.create(request)
    finally:
        await client.aclose()

    assert result.model == request.model and result.text == "Recovered service health."
    assert [item.url.path for item in requests] == [
        "/api/v1/responses",
        "/api/v1/models/z-ai/glm-5.3-flash/endpoints",
    ]
    assert requests[1].headers["authorization"] == f"Bearer {SECRET}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "catalog_body",
    [
        catalog(
            "z-ai/glm-5.3-flash-20260826",
            model="other/model",
            provider="Relace",
            tag="relace/fp4",
        ),
        catalog(
            "z-ai/glm-5.3-flash-20260826",
            model="z-ai/glm-5.3-flash",
            provider="Other",
            tag="other",
        ),
        catalog(
            "other-model",
            model="z-ai/glm-5.3-flash",
            provider="Relace",
            tag="relace/fp4",
        ),
        {
            "data": {
                "id": "z-ai/glm-5.3-flash",
                "endpoints": [
                    {
                        "model_id": "z-ai/glm-5.3-flash",
                        "provider_name": "Relace",
                        "tag": "relace/fp4",
                        "name": "Relace | z-ai/glm-5.3-flash-20260826",
                    },
                    {
                        "model_id": "z-ai/glm-5.3-flash",
                        "provider_name": "Relace",
                        "tag": "relace/fp4",
                        "name": "Relace | z-ai/glm-5.3-flash-20260826",
                    },
                ],
            }
        },
    ],
)
async def test_alias_drift_requires_one_unambiguous_catalog_identity(
    catalog_body: dict[str, object],
) -> None:
    selected_model = "z-ai/glm-5.3-flash-20260826"
    request = ProviderRequest(input="diagnose", model="z-ai/glm-5.3-flash", provider="relace")
    body = successful_response(
        requested=request.model,
        endpoints={
            "total": 1,
            "available": [{"provider": "Relace", "model": selected_model, "selected": True}],
        },
        attempts=[{"provider": "Relace", "model": selected_model, "status": 200}],
    ) | {"model": request.model}

    def respond(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=body if http_request.method == "POST" else catalog_body,
        )

    adapter, client = provider(httpx.MockTransport(respond))
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(request)
    finally:
        await client.aclose()
    assert captured.value.kind == "evidence_invalid"


@pytest.mark.asyncio
async def test_alias_drift_fails_closed_when_the_catalog_is_unavailable() -> None:
    selected_model = "z-ai/glm-5.3-flash-20260826"
    request = ProviderRequest(input="diagnose", model="z-ai/glm-5.3-flash", provider="relace")
    body = successful_response(
        requested=request.model,
        endpoints={
            "total": 1,
            "available": [{"provider": "Relace", "model": selected_model, "selected": True}],
        },
        attempts=[{"provider": "Relace", "model": selected_model, "status": 200}],
    ) | {"model": request.model}

    def respond(http_request: httpx.Request) -> httpx.Response:
        if http_request.method == "POST":
            return httpx.Response(200, json=body)
        return httpx.Response(503)

    adapter, client = provider(httpx.MockTransport(respond))
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(request)
    finally:
        await client.aclose()
    assert captured.value.kind == "evidence_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "kind"),
    [
        ({"id": "resp_12345678", "model": MODEL, "output_text": "ok"}, "invalid_response"),
        (successful_response(requested="other/model"), "evidence_invalid"),
        (successful_response(attempt=2), "evidence_invalid"),
        (
            successful_response(
                endpoints={
                    "total": 2,
                    "available": [
                        {"provider": "OpenAI", "model": MODEL, "selected": True},
                        {"provider": "Other", "model": MODEL, "selected": True},
                    ],
                }
            ),
            "evidence_invalid",
        ),
        (
            successful_response(
                endpoints={
                    "total": 1,
                    "available": [{"provider": "Other", "model": MODEL, "selected": True}],
                }
            ),
            "evidence_invalid",
        ),
    ],
)
async def test_invalid_or_extra_provider_evidence_fails_closed(
    body: dict[str, object], kind: str
) -> None:
    adapter, client = provider(httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(ProviderRequest(input="diagnose", model=MODEL, provider=PROVIDER))
    finally:
        await client.aclose()
    assert captured.value.kind == kind
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
        (404, "30", "unavailable", 30),
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
    "body",
    [
        successful_response(status="in_progress"),
        successful_response(error={"message": "unexpected"}),
        successful_response(incomplete_details={"reason": "length"}),
        successful_response(output=[]),
        successful_response(
            output=[
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "in_progress",
                    "content": [{"type": "output_text", "text": "partial"}],
                }
            ]
        ),
        successful_response(model="other/model"),
        successful_response(
            attempts=[{"provider": "OpenAI", "model": "other/model", "status": 200}]
        ),
    ],
)
async def test_incomplete_or_contradictory_completed_responses_fail_closed(
    body: dict[str, object],
) -> None:
    adapter, client = provider(httpx.MockTransport(lambda _request: httpx.Response(200, json=body)))
    try:
        with pytest.raises(ProviderFailure) as captured:
            await adapter.create(REQUEST)
    finally:
        await client.aclose()
    assert captured.value.kind in {"invalid_response", "evidence_invalid"}


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
