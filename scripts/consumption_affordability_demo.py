"""Offline controlled demonstration of the endpoint/incident calculator."""

import json
from datetime import UTC, datetime, timedelta

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
    prompt_price=None,
    completion_price=None,
    request_price=None,
)
snapshot = EndpointCatalogSnapshot(
    model=endpoint.model,
    endpoints=(endpoint,),
    observed_at=now,
    valid_until=now + timedelta(seconds=60),
)


def outcome(incident_tokens_remaining: int | None) -> dict[str, object]:
    try:
        result = calculate_affordability(
            snapshot,
            provider="OpenAI",
            incident_tokens_remaining=incident_tokens_remaining,
            now=now,
        )
        return {
            "decision": "allow",
            "max_output_tokens": result.max_output_tokens,
            "conservative_input_tokens": result.conservative_input_tokens,
        }
    except AffordabilityDenied as exc:
        return {"decision": "deny", "reason": str(exc)}


print(
    json.dumps(
        {
            "evidence": (
                "local Docker, offline synthetic catalog snapshot; "
                "not live provider or admission proof"
            ),
            "endpoint_max_output_tokens": endpoint.max_completion_tokens,
            "endpoint_max_prompt_tokens": endpoint.max_prompt_tokens,
            "incident_exact_equality_remaining_12": outcome(12),
            "incident_input_only_remaining_10": outcome(10),
            "incident_zero_remaining": outcome(0),
            "incident_unset": outcome(None),
        },
        indent=2,
        sort_keys=True,
    )
)
