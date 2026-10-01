"""Calculate a conservative incident-token output ceiling before provider work."""

from dataclasses import dataclass
from datetime import datetime

from sre_agent.gateway.endpoint_catalog import (
    MAX_ENDPOINT_TOKENS,
    EndpointCatalogSnapshot,
    EndpointCatalogUnavailable,
    EndpointMetadata,
)


class AffordabilityDenied(Exception):
    """Fresh endpoint capacity or incident-token balance cannot justify a request."""

    def __init__(self) -> None:
        super().__init__("consumption_bounds_unavailable")


@dataclass(frozen=True, slots=True)
class AffordabilityEnvelope:
    model: str
    provider: str
    max_output_tokens: int
    conservative_input_tokens: int


def calculate_affordability(
    snapshot: EndpointCatalogSnapshot,
    *,
    provider: str,
    incident_tokens_remaining: int | None,
    now: datetime,
) -> AffordabilityEnvelope:
    """Use only an explicit, unique provider and the catalog's maximum prompt capacity."""
    try:
        endpoint = snapshot.select(provider, now=now)
    except (AttributeError, TypeError, ValueError, EndpointCatalogUnavailable):
        raise AffordabilityDenied from None
    _validate_endpoint(snapshot, endpoint, now)
    if incident_tokens_remaining is not None and (
        type(incident_tokens_remaining) is not int
        or not 0 <= incident_tokens_remaining <= MAX_ENDPOINT_TOKENS
    ):
        raise AffordabilityDenied

    output_ceiling = endpoint.max_completion_tokens
    if incident_tokens_remaining is not None:
        output_ceiling = min(
            output_ceiling,
            incident_tokens_remaining - endpoint.max_prompt_tokens,
        )
    if output_ceiling <= 0:
        raise AffordabilityDenied
    return AffordabilityEnvelope(
        model=endpoint.model,
        provider=endpoint.provider,
        max_output_tokens=output_ceiling,
        conservative_input_tokens=endpoint.max_prompt_tokens,
    )


def _validate_endpoint(
    snapshot: EndpointCatalogSnapshot,
    endpoint: EndpointMetadata,
    now: datetime,
) -> None:
    if (
        not isinstance(snapshot, EndpointCatalogSnapshot)
        or not isinstance(endpoint, EndpointMetadata)
        or not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
        or endpoint.model != snapshot.model
        or not isinstance(endpoint.provider, str)
        or not endpoint.provider.strip()
        or type(endpoint.max_prompt_tokens) is not int
        or not 0 < endpoint.max_prompt_tokens <= MAX_ENDPOINT_TOKENS
        or type(endpoint.max_completion_tokens) is not int
        or not 0 < endpoint.max_completion_tokens <= MAX_ENDPOINT_TOKENS
        or not isinstance(endpoint.valid_until, datetime)
        or endpoint.valid_until.tzinfo is None
        or endpoint.valid_until.utcoffset() is None
        or now >= endpoint.valid_until
    ):
        raise AffordabilityDenied
