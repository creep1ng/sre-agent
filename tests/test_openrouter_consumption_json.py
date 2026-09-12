from decimal import Decimal

import httpx

from sre_agent.gateway.openrouter import _json_body


def test_json_body_preserves_raw_provider_cost_precision() -> None:
    response = httpx.Response(
        200,
        content=b'{"usage":{"cost":0.0012300},"created_at":1789000000}',
    )

    body = _json_body(response)

    assert body["usage"]["cost"] == Decimal("0.0012300")
    assert format(body["usage"]["cost"], "f") == "0.0012300"
