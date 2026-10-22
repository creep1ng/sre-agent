"""The investigator's log query reaches the field the OTel logs index uses (issue #716).

Failure modes, written before the change:
- the model writes `service.name:checkout`, which the index does not have, and gets 0 documents;
- a query that already uses `resource.service.name` is prefixed a second time;
- a hyphenated service (`frontend-proxy`) is split by the query parser and matches nothing;
- a query without the service field (or with `service.namespace`) is rewritten anyway;
- the recorded evidence names a query other than the one actually sent;
- an index without matching documents is reported as a failure instead of an empty result.
"""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from sre_agent.investigator.client import GatewaySettings, MCPGatewayClient

ARGUMENTS = {
    "datasource_uid": "webstore-logs",
    "index": "otel-logs-*",
    "start_time": "now-15m",
    "end_time": "now",
    "limit": 20,
}


async def _collect(query: str, total: int = 1) -> tuple[str, object]:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content)["query"])
        documents = [{"body": "payment failed"}] * total
        return httpx.Response(
            200,
            json={"total": total, "documents": documents, "warnings": []},
            headers={"X-Request-ID": str(uuid4())},
        )

    settings = GatewaySettings(
        base_url="http://gateway", api_key="sre_test_key", model_alias="triage-agent"
    )
    client = MCPGatewayClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await client.collect("query_elasticsearch", ARGUMENTS | {"query": query})
    assert result.query == sent[0], "the evidence must name the query that was sent"
    return sent[0], result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("written", "sent"),
    [
        ("service.name:checkout", "resource.service.name:checkout"),
        ('service.name:"payment" AND fail', 'resource.service.name:"payment" AND fail'),
        ('resource.service.name:"checkout"', 'resource.service.name:"checkout"'),
        ("service.name:frontend-proxy", 'resource.service.name:"frontend-proxy"'),
        ("resource.service.name:frontend-proxy", 'resource.service.name:"frontend-proxy"'),
        ("body:*checkout* AND error", "body:*checkout* AND error"),
        ("service.namespace:webstore", "service.namespace:webstore"),
    ],
)
async def test_the_log_query_uses_the_index_service_field(written: str, sent: str) -> None:
    assert (await _collect(written))[0] == sent


@pytest.mark.asyncio
async def test_an_index_without_documents_is_an_empty_result_not_a_failure() -> None:
    _, result = await _collect("service.name:checkout", total=0)
    assert json.loads(result.summary)["total"] == 0
