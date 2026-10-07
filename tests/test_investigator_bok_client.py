"""The investigator's HTTP adapter for BoK search (issue #34).

`GatewayClient.search` posts to `/v1/bok/collections/{collection_id}/versions/{version}/search`.
Written from what it could get wrong: send another secret or a body the producer rejects, lose
the producer's reason for a 503, take a body outside the contract or a network failure for one.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any

import httpx
import pytest
from test_investigator_bok import fragment
from test_investigator_client import ENVIRONMENT

from sre_agent.investigator.client import GatewayClient, GatewaySettings
from sre_agent.investigator.ports import BoKFragment, GatewayError

FRAGMENT = asdict(fragment()) | {"score": 0.1}


def search(handler: Any) -> list[BoKFragment]:
    settings = GatewaySettings.from_environment(ENVIRONMENT)
    client = GatewayClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return asyncio.run(client.search("demo-incident-response", "1.0.0", "severity impact", 5))


def test_the_client_searches_the_exact_version_with_the_principal_key_only() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": [FRAGMENT]})

    found = search(handler)

    assert str(seen[0].url) == (
        "http://api:8000/v1/bok/collections/demo-incident-response/versions/1.0.0/search"
    )
    assert json.loads(seen[0].content) == {"query": "severity impact", "limit": 5}
    assert seen[0].headers["Authorization"] == "Bearer sre_test_gateway_key"
    assert "sk-or-provider-secret" not in json.dumps(dict(seen[0].headers))
    assert found == [fragment()]


@pytest.mark.parametrize(
    ("status", "served", "kind", "code"),
    [
        (401, {"error": {"code": "authentication_failed"}}, "denied", None),
        (403, {"error": {"code": "resource_unavailable"}}, "denied", None),
        (503, {"error": {"code": "index_unavailable"}}, "transient", "index_unavailable"),
        (503, {"error": {"code": "storage_unavailable"}}, "transient", "storage_unavailable"),
        (503, {"error": {"code": "audit_unavailable"}}, "transient", "audit_unavailable"),
        (503, {"error": {"code": "Storage down, see the logs"}}, "transient", None),
        (502, "bad gateway", "transient", None),
        (422, {"error": {"code": "contract_validation_failed"}}, "rejected", None),
        (404, {"detail": "Not Found"}, "rejected", None),
        (200, {"results": "not a list"}, "rejected", None),
        (None, httpx.ConnectError, "transient", "network"),
        (None, httpx.ReadTimeout, "transient", "timeout"),
    ],
    ids=(
        "unauthenticated forbidden not-ready storage-down audit-down odd-code bad-gateway "
        "invalid no-route malformed unreachable timeout"
    ).split(),
)
def test_the_client_tells_each_answer_apart(
    status: int | None, served: Any, kind: str, code: str | None
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if status is None:
            raise served("gateway down", request=request)
        return httpx.Response(status, json=served)

    with pytest.raises(GatewayError) as raised:
        search(handler)
    assert (raised.value.kind, raised.value.code) == (kind, code)
