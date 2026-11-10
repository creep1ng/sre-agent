"""Offline controlled demonstration of monthly affordability."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sre_agent.gateway.consumption_affordability import (
    AffordabilityDenied,
    calculate_affordability,
)
from sre_agent.gateway.endpoint_catalog import EndpointCatalogSnapshot, EndpointMetadata

now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
endpoint = EndpointMetadata(
    model="openai/gpt-4o-mini",
    provider="OpenAI",
    max_prompt_tokens=10,
    max_completion_tokens=100,
    valid_until=now + timedelta(seconds=60),
    prompt_price=Decimal("0.05"),
    completion_price=Decimal("0.10"),
    request_price=Decimal("0.20"),
)


def outcome(selected: EndpointMetadata, monthly_remaining: Decimal | None) -> dict[str, object]:
    snapshot = EndpointCatalogSnapshot(
        model=selected.model,
        endpoints=(selected,),
        observed_at=now,
        valid_until=now + timedelta(seconds=60),
    )
    try:
        result = calculate_affordability(
            snapshot,
            provider="OpenAI",
            incident_tokens_remaining=None,
            monthly_usd_remaining=monthly_remaining,
            now=now,
        )
        return {
            "decision": "allow",
            "max_output_tokens": result.max_output_tokens,
            "conservative_input_cost_usd": (
                str(result.conservative_input_cost_usd)
                if result.conservative_input_cost_usd is not None
                else None
            ),
            "request_fee_usd": (
                str(result.request_fee_usd) if result.request_fee_usd is not None else None
            ),
        }
    except AffordabilityDenied as exc:
        return {"decision": "deny", "reason": str(exc)}


free = replace(
    endpoint,
    prompt_price=Decimal("0"),
    completion_price=Decimal("0"),
    request_price=Decimal("0"),
)
unknown = replace(endpoint, prompt_price=None)
unpriced = replace(endpoint, prompt_price=None, completion_price=None, request_price=None)
print(
    json.dumps(
        {
            "evidence": "local Docker, offline synthetic snapshot; no provider or admission call",
            "known_prices_monthly_exact_1_usd": outcome(endpoint, Decimal("1.00")),
            "provably_free_monthly_zero": outcome(free, Decimal("0")),
            "unknown_prompt_price_monthly_zero": outcome(unknown, Decimal("0")),
            "monthly_unset_unpriced": outcome(unpriced, None),
        },
        indent=2,
        sort_keys=True,
    )
)
