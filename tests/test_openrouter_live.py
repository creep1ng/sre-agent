"""One-request live gateway smoke; ordinary test and CI runs skip it."""

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from sre_agent.release import CONTRACT_VERSION

RELEASE = Path(__file__).parents[1] / "schemas/releases" / CONTRACT_VERSION
RESPONSE_SCHEMA = f"urn:sre-agent:schema:responses-response:{CONTRACT_VERSION}"


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").casefold() in {"1", "true", "yes"}


def _contract_validator() -> Draft202012Validator:
    """Check the live payload against the contract release the gateway runs.

    Asserting a literal shape here let this smoke drift: the published contract
    gained consumption evidence and the expectation stayed behind, unnoticed
    because the smoke never runs in CI. The release is now the expectation.
    """

    documents: list[dict[str, Any]] = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((RELEASE / "json-schema").rglob("*.schema.json"))
    ]
    registry = Registry().with_resources(
        (document["$id"], Resource.from_contents(document)) for document in documents
    )
    return Draft202012Validator(
        registry.contents(RESPONSE_SCHEMA), registry=registry, format_checker=FormatChecker()
    )


@pytest.mark.skipif(
    not _enabled("RUN_OPENROUTER_LIVE_SMOKE"),
    reason="set RUN_OPENROUTER_LIVE_SMOKE=1 to enable one live provider request",
)
def test_openrouter_gateway_live_smoke() -> None:
    if not _enabled("OPENROUTER_API_CONFIGURED"):
        pytest.skip("OPENROUTER_API_KEY is not configured for the API service")
    if not _enabled("AUDIT_HMAC_CONFIGURED"):
        pytest.skip("AUDIT_HMAC_KEY is not configured for the API service")

    api_url = os.environ["OPENROUTER_LIVE_API_URL"].rstrip("/")
    api_key = os.environ["INCIDENT_HARNESS_API_KEY"]
    model = os.environ["TRIAGE_AGENT_MODEL"]
    provider = os.environ["TRIAGE_AGENT_PROVIDER"]
    response = httpx.post(
        f"{api_url}/v1/responses",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "triage-agent", "input": "Reply with one short health status."},
        timeout=125,
    )

    assert response.status_code == 200
    payload = response.json()
    _contract_validator().validate(payload)
    assert payload["id"].startswith("resp_")
    assert payload["object"] == "response" and payload["status"] == "completed"
    assert payload["model"] == model
    UUID(payload["request_id"])

    metadata = payload["metadata"]
    assert metadata["requested_model_alias"] == "triage-agent"
    assert metadata["router"] == "openrouter"
    assert metadata["inference_provider"] == provider

    consumption = metadata["consumption"]
    assert consumption["availability"] == "complete"
    assert consumption["source"] == "openrouter"
    assert consumption["input_tokens"] > 0 and consumption["output_tokens"] > 0
    assert consumption["total_tokens"] == consumption["input_tokens"] + consumption["output_tokens"]
    assert consumption["currency"] == "USD"
    assert consumption["pricing_context"]["price_version"].startswith("openrouter:")

    content = payload["output"][0]["content"][0]
    assert content["type"] == "output_text"
    assert isinstance(content["text"], str) and 0 < len(content["text"]) <= 65_536
    if api_key in response.text:
        pytest.fail("normalized response leaked the client credential", pytrace=False)
