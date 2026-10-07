"""The investigator's HTTP adapter for Skill resolution (issue #32).

`GatewayClient.resolve` reads `GET /v1/skills/{skill_id}/{version}/resolve` with its own
models. Written from what it could get wrong: send a secret other than the principal key,
tell the producer's single 404 apart, or accept a body that is not the version it asked for
with exactly the dependencies that version pins.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from test_investigator_client import ENVIRONMENT

from sre_agent.investigator.client import GatewayClient, GatewaySettings
from sre_agent.investigator.ports import GatewayError, ResolvedSkill

PIN = {"skill_id": "incident-triage", "version": "1.0.0"}


def record(name: str, digest: str, dependencies: list[dict[str, str]]) -> dict[str, Any]:
    manifest = {"display_name": name, "instructions": "x", "dependencies": dependencies}
    return {"skill_id": name, "version": "1.0.0", "content_sha256": digest, "manifest": manifest}


ROOT = record("postmortem-writer", "e" * 64, [PIN])
DEPENDENCY = record("incident-triage", "a" * 64, [])
NESTED = record("incident-triage", "a" * 64, [{"skill_id": "nested-rule", "version": "1.0.0"}])


def body(root: dict[str, Any] = ROOT, *dependencies: dict[str, Any]) -> dict[str, Any]:
    served = list(dependencies) if dependencies else [DEPENDENCY]
    return {"skill": root, "dependencies": served, "request_id": str(uuid4())}


def resolve(handler: Any) -> ResolvedSkill:
    settings = GatewaySettings.from_environment(ENVIRONMENT)
    client = GatewayClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return asyncio.run(client.resolve("postmortem-writer", "1.0.0"))


def test_the_client_resolves_the_exact_version_with_the_principal_key_only() -> None:
    seen: list[httpx.Request] = []
    served = body()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=served)

    resolved = resolve(handler)

    assert str(seen[0].url) == "http://api:8000/v1/skills/postmortem-writer/1.0.0/resolve"
    assert seen[0].headers["Authorization"] == "Bearer sre_test_gateway_key"
    assert "sk-or-provider-secret" not in json.dumps(dict(seen[0].headers))
    assert (resolved.ref, resolved.request_id) == (
        "postmortem-writer@1.0.0",
        UUID(served["request_id"]),
    )
    assert [(item.ref, item.content_sha256) for item in resolved.dependencies] == [
        ("incident-triage@1.0.0", "a" * 64)
    ]


@pytest.mark.parametrize(
    ("status", "served", "kind"),
    [
        (404, {"error": {"code": "resource_not_found"}}, "denied"),
        (401, {"error": {"code": "authentication_failed"}}, "denied"),
        (403, {"error": {"code": "resource_unavailable"}}, "denied"),
        (503, {"error": {"code": "audit_unavailable"}}, "transient"),
        (422, {"error": {"code": "contract_validation_failed"}}, "rejected"),
        (200, {"skill": "not a record"}, "rejected"),
        (200, body({**ROOT, "version": "2.0.0"}), "rejected"),
        (200, body(ROOT, DEPENDENCY, DEPENDENCY), "rejected"),
        (200, body(ROOT, NESTED), "rejected"),
        (None, httpx.ConnectError, "transient"),
        (None, httpx.ReadTimeout, "transient"),
    ],
    ids=(
        "missing unauthenticated forbidden unavailable invalid malformed other-version "
        "extra-dependency nested-dependency unreachable timeout"
    ).split(),
)
def test_the_client_refuses_anything_but_the_version_and_dependencies_it_pinned(
    status: int | None, served: Any, kind: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if status is None:
            raise served("gateway down", request=request)
        return httpx.Response(status, json=served)

    with pytest.raises(GatewayError) as raised:
        resolve(handler)
    assert raised.value.kind == kind
