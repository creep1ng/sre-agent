"""Characterize the current provider evidence policy at the native boundary."""

from decimal import Decimal

import httpx
import pytest

from sre_agent import _core
from sre_agent.gateway.openrouter import OpenRouterProvider
from sre_agent.gateway.providers import ProviderFailure, ProviderRequest

MODEL = "openai/gpt-4o-mini"
REQUEST = ProviderRequest(input="diagnose", model=MODEL, provider="strasse")


class TrackedProvider(str):
    calls = 0

    def casefold(self) -> str:
        type(self).calls += 1
        return super().casefold()


def body() -> dict[str, object]:
    return {
        "id": "gen-12345678",
        "model": MODEL,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "ok"}],
            }
        ],
        "openrouter_metadata": {
            "requested": MODEL,
            "strategy": "direct",
            "attempt": 1,
            "endpoints": {"available": [{"selected": True, "provider": "Straße", "model": MODEL}]},
            "attempts": [{"provider": "Straße", "model": MODEL, "status": 200}],
        },
        "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    }


def test_native_evidence_symbols_and_staged_result() -> None:
    assert _core.inspect_provider_response(body(), MODEL, "strasse") == ("accept", None)
    assert _core.confirm_provider_catalog(None, "canonical", MODEL, "strasse") is False


def test_invalid_body_does_not_casefold_unreachable_metadata() -> None:
    payload = body()
    payload["id"] = "invalid"
    metadata = payload["openrouter_metadata"]
    assert isinstance(metadata, dict)
    available = metadata["endpoints"]["available"]
    available[0]["provider"] = TrackedProvider("Straße")
    metadata["attempts"][0]["provider"] = TrackedProvider("Straße")
    TrackedProvider.calls = 0
    assert _core.inspect_provider_response(payload, MODEL, "strasse") == (
        "reject",
        "invalid_response",
    )
    assert TrackedProvider.calls == 0


def test_unselected_endpoints_do_not_casefold_provider_names() -> None:
    payload = body()
    metadata = payload["openrouter_metadata"]
    assert isinstance(metadata, dict)
    metadata["attempts"] = None
    available = metadata["endpoints"]["available"]
    available[:0] = [
        {"selected": False, "provider": TrackedProvider("irrelevant"), "model": MODEL}
        for _ in range(20)
    ]
    available[-1]["provider"] = TrackedProvider("Straße")
    TrackedProvider.calls = 0
    assert _core.inspect_provider_response(payload, MODEL, "strasse") == ("accept", None)
    assert TrackedProvider.calls == 1


def test_catalog_rejects_invalid_id_without_casefolding_endpoints() -> None:
    payload = {
        "data": {
            "id": "wrong",
            "endpoints": [
                {
                    "model_id": MODEL,
                    "provider_name": TrackedProvider("Straße"),
                    "tag": "strasse/fp4",
                    "name": "Straße | canonical",
                }
                for _ in range(20)
            ],
        }
    }
    TrackedProvider.calls = 0
    assert _core.confirm_provider_catalog(payload, "canonical", MODEL, "strasse") is False
    assert TrackedProvider.calls == 0


def test_catalog_casefolds_only_matching_model_id_candidates() -> None:
    payload = {
        "data": {
            "id": MODEL,
            "endpoints": [
                {
                    "model_id": "other",
                    "provider_name": TrackedProvider("irrelevant"),
                    "tag": "strasse/fp4",
                    "name": "irrelevant | canonical",
                },
                {
                    "model_id": MODEL,
                    "provider_name": TrackedProvider("Straße"),
                    "tag": "strasse/fp4",
                    "name": "Straße | canonical",
                },
            ],
        }
    }
    TrackedProvider.calls = 0
    assert _core.confirm_provider_catalog(payload, "canonical", MODEL, "strasse") is True
    assert TrackedProvider.calls == 1


@pytest.mark.parametrize(
    ("attempt", "accepted"),
    [
        (Decimal("1.000"), True),
        (Decimal("1.0000000000000000001"), False),
        (Decimal("1E+1000000"), False),
        (False, False),
    ],
)
def test_native_numeric_facts_do_not_round(attempt: object, accepted: bool) -> None:
    payload = body()
    metadata = payload["openrouter_metadata"]
    assert isinstance(metadata, dict)
    metadata["attempt"] = attempt
    stage, _ = _core.inspect_provider_response(payload, MODEL, "strasse")
    assert (stage == "accept") is accepted


@pytest.mark.parametrize(
    "catalog_body",
    [
        None,
        {"data": []},
        {"data": {"id": MODEL, "endpoints": {}}},
        {"data": {"id": MODEL, "endpoints": [None]}},
        {"data": {"id": MODEL, "endpoints": [{"provider_name": "Straße"}]}},
    ],
)
def test_native_catalog_rejects_malformed_mapping_and_list_edges(catalog_body: object) -> None:
    assert _core.confirm_provider_catalog(catalog_body, "canonical", MODEL, "strasse") is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "expected_kind", "gets"),
    [
        (lambda b: b["openrouter_metadata"].update(attempt=True), None, 0),
        (lambda b: b["openrouter_metadata"].update(attempt=1.0), None, 0),
        (
            lambda b: b["openrouter_metadata"]["endpoints"].update(
                available=[{"selected": 1, "provider": "Straße", "model": MODEL}]
            ),
            "evidence_invalid",
            0,
        ),
        (
            lambda b: b["openrouter_metadata"].update(
                attempts=[{"provider": "Straße", "model": MODEL, "status": 200.0}]
            ),
            None,
            0,
        ),
        (
            lambda b: b["openrouter_metadata"].update(
                attempts=[{"provider": "Straße", "model": MODEL, "status": True}]
            ),
            "evidence_invalid",
            0,
        ),
        (lambda b: b.update(error={"message": "secret"}), "invalid_response", 0),
        (lambda b: b.update(incomplete_details={"reason": "length"}), "invalid_response", 0),
        (lambda b: b.update(id="resp_12345678"), "invalid_response", 0),
        (lambda b: b["openrouter_metadata"].update(endpoints=[]), "evidence_invalid", 0),
        (lambda b: b["openrouter_metadata"].update(attempts={}), "evidence_invalid", 0),
        (
            lambda b: b["openrouter_metadata"]["endpoints"].update(
                available=[{"selected": True, "provider": "Other", "model": MODEL}]
            ),
            "evidence_invalid",
            0,
        ),
    ],
)
async def test_current_inline_evidence_parity(mutate, expected_kind, gets) -> None:  # type: ignore[no-untyped-def]
    payload = body()
    mutate(payload)
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://test")
    try:
        adapter = OpenRouterProvider(client, api_key="synthetic")
        if expected_kind is None:
            result = await adapter.create(REQUEST)
            assert result.text == "ok"
        else:
            with pytest.raises(ProviderFailure) as captured:
                await adapter.create(REQUEST)
            assert captured.value.kind == expected_kind
            assert captured.value.consumption is not None
            assert captured.value.consumption.availability == "partial"
    finally:
        await client.aclose()
    assert calls == ["POST"] + ["GET"] * gets


@pytest.mark.asyncio
@pytest.mark.parametrize("tag", ["strasse/fp4", "Straße/fp4", "strasseX/fp4"])
async def test_catalog_tag_stays_case_sensitive_and_gets_once(tag: str) -> None:
    payload = body()
    metadata = payload["openrouter_metadata"]
    assert isinstance(metadata, dict)
    endpoints = metadata["endpoints"]
    assert isinstance(endpoints, dict)
    selected = endpoints["available"]
    assert isinstance(selected, list)
    selected[0]["model"] = "canonical"
    metadata["attempts"][0]["model"] = "canonical"
    catalog = {
        "data": {
            "id": MODEL,
            "endpoints": [
                {
                    "model_id": MODEL,
                    "provider_name": "Straße",
                    "tag": tag,
                    "name": "Straße | canonical",
                }
            ],
        }
    }
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json=payload if request.method == "POST" else catalog)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://test")
    try:
        adapter = OpenRouterProvider(client, api_key="synthetic")
        if tag == "strasse/fp4":
            assert (await adapter.create(REQUEST)).text == "ok"
        else:
            with pytest.raises(ProviderFailure) as captured:
                await adapter.create(REQUEST)
            assert captured.value.kind == "evidence_invalid"
    finally:
        await client.aclose()
    assert calls == ["POST", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("catalog_valid", "kind"),
    [(True, "invalid_response"), (False, "evidence_invalid")],
)
async def test_catalog_decision_precedes_output_text_and_preserves_consumption(
    catalog_valid: bool, kind: str
) -> None:
    payload = body()
    payload["output"] = []
    metadata = payload["openrouter_metadata"]
    assert isinstance(metadata, dict)
    endpoints = metadata["endpoints"]
    assert isinstance(endpoints, dict)
    selected = endpoints["available"]
    assert isinstance(selected, list)
    selected[0]["model"] = "canonical"
    metadata["attempts"][0]["model"] = "canonical"
    catalog = {
        "data": {
            "id": MODEL,
            "endpoints": [
                {
                    "model_id": MODEL,
                    "provider_name": "Straße",
                    "tag": "strasse/fp4",
                    "name": "Straße | canonical" if catalog_valid else "wrong",
                }
            ],
        }
    }
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json=payload if request.method == "POST" else catalog)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="https://test")
    try:
        with pytest.raises(ProviderFailure) as captured:
            await OpenRouterProvider(client, api_key="synthetic").create(REQUEST)
    finally:
        await client.aclose()
    assert captured.value.kind == kind
    assert captured.value.consumption is not None
    assert captured.value.consumption.availability == "partial"
    assert calls == ["POST", "GET"]
