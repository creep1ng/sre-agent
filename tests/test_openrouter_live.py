"""One-request live gateway smoke; ordinary test and CI runs skip it."""

import os
from uuid import UUID

import httpx
import pytest


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").casefold() in {"1", "true", "yes"}


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
    assert set(payload) == {"id", "object", "status", "model", "output", "request_id", "metadata"}
    assert payload["id"].startswith("resp_")
    assert payload["object"] == "response" and payload["status"] == "completed"
    assert payload["model"] == model
    UUID(payload["request_id"])
    assert payload["metadata"] == {
        "requested_model_alias": "triage-agent",
        "router": "openrouter",
        "inference_provider": provider,
    }
    content = payload["output"][0]["content"][0]
    assert content["type"] == "output_text"
    assert isinstance(content["text"], str) and 0 < len(content["text"]) <= 65_536
    if api_key in response.text:
        pytest.fail("normalized response leaked the client credential", pytrace=False)
