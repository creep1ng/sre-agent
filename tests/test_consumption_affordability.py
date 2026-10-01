"""Pure incident-token cap contracts; failure modes precede implementation."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from sre_agent.gateway.consumption_affordability import (
    AffordabilityDenied,
    calculate_affordability,
)
from sre_agent.gateway.endpoint_catalog import EndpointCatalogSnapshot, EndpointMetadata

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def endpoint(**changes: object) -> EndpointMetadata:
    return replace(
        EndpointMetadata(
            model="openai/gpt-4o-mini",
            provider="OpenAI",
            max_prompt_tokens=10,
            max_completion_tokens=100,
            valid_until=NOW + timedelta(seconds=60),
            prompt_price=None,
            completion_price=None,
            request_price=None,
        ),
        **changes,
    )


def snapshot(*endpoints: EndpointMetadata) -> EndpointCatalogSnapshot:
    return EndpointCatalogSnapshot(
        model="openai/gpt-4o-mini",
        endpoints=endpoints,
        observed_at=NOW,
        valid_until=NOW + timedelta(seconds=60),
    )


def calculate(
    selected: EndpointCatalogSnapshot,
    *,
    incident_remaining: int | None = None,
    provider: str = "OpenAI",
    now: datetime = NOW,
):
    return calculate_affordability(
        selected,
        provider=provider,
        incident_tokens_remaining=incident_remaining,
        now=now,
    )


@pytest.mark.parametrize(
    ("incident_remaining", "endpoint_limit", "expected"),
    [
        (12, 100, 2),
        (100, 2, 2),
        (None, 100, 100),
        (100, 100, 90),
    ],
)
def test_output_cap_uses_tightest_endpoint_and_incident_ceilings(
    incident_remaining: int | None,
    endpoint_limit: int,
    expected: int,
) -> None:
    result = calculate(
        snapshot(endpoint(max_completion_tokens=endpoint_limit)),
        incident_remaining=incident_remaining,
    )
    assert result.max_output_tokens == expected
    assert result.conservative_input_tokens == 10
    assert result.model == "openai/gpt-4o-mini"
    assert result.provider == "OpenAI"


@pytest.mark.parametrize("remaining", [0, 10])
def test_zero_or_input_only_incident_balance_denies(remaining: int) -> None:
    with pytest.raises(AffordabilityDenied):
        calculate(snapshot(endpoint()), incident_remaining=remaining)


@pytest.mark.parametrize("remaining", [-1, True, "10", 9_223_372_036_854_775_808])
def test_invalid_incident_balance_denies(remaining: object) -> None:
    with pytest.raises(AffordabilityDenied):
        calculate(snapshot(endpoint()), incident_remaining=remaining)


@pytest.mark.parametrize(
    ("field", "invalid_capacity"),
    [
        ("max_prompt_tokens", None),
        ("max_prompt_tokens", 0),
        ("max_prompt_tokens", -1),
        ("max_prompt_tokens", True),
        ("max_prompt_tokens", 9_223_372_036_854_775_808),
        ("max_prompt_tokens", "10"),
        ("max_completion_tokens", None),
        ("max_completion_tokens", 0),
        ("max_completion_tokens", -1),
        ("max_completion_tokens", True),
    ],
)
def test_invalid_or_missing_capacity_denies(field: str, invalid_capacity: object) -> None:
    with pytest.raises(AffordabilityDenied):
        calculate(snapshot(endpoint(**{field: invalid_capacity})))


def test_stale_ambiguous_missing_or_mismatched_endpoint_denies() -> None:
    fresh = endpoint()
    stale = EndpointCatalogSnapshot(
        model="openai/gpt-4o-mini",
        endpoints=(fresh,),
        observed_at=NOW - timedelta(minutes=2),
        valid_until=NOW - timedelta(minutes=1),
    )
    wrong_model = EndpointCatalogSnapshot(
        model="other/model",
        endpoints=(fresh,),
        observed_at=NOW,
        valid_until=NOW + timedelta(seconds=60),
    )
    for candidate, provider in (
        (stale, "OpenAI"),
        (snapshot(fresh, fresh), "OpenAI"),
        (snapshot(fresh), "Anthropic"),
        (wrong_model, "OpenAI"),
    ):
        with pytest.raises(AffordabilityDenied):
            calculate(candidate, provider=provider)


def test_naive_calculation_time_denies() -> None:
    with pytest.raises(AffordabilityDenied):
        calculate(snapshot(endpoint()), now=datetime(2026, 9, 28))
