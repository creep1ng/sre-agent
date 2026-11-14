"""Every governed operation goes through the gate (`sre_agent.gate`).

Two walks: the operations that document `x-governed-scope` in `openapi.json` must be registered
with the same scope, and every non-control `/v1/` route of the application must be registered,
or exempt for a named reason, and must reach `Gate.run` when called. A route that keeps its
registration but answers by hand fails the second walk.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.gate.pipeline import Gate, governed_operations
from sre_agent.settings import Settings

# The control plane's routes move to the gate with its own refactor (#1022).
CONTROL_PACKAGE = "sre_agent.control."
EXEMPT = {
    # It authenticates the caller and names it; no scope is asked of it.
    ("GET", "/v1/whoami"): "identity only",
    # Grafana authenticates with the intake secret, not with a principal's key.
    ("POST", "/v1/alert-intake/grafana"): "webhook secret",
}
# Gateway operations not moved yet; each layer of #1021 empties its part of this set.
NOT_YET_MIGRATED: set[tuple[str, str]] = {
    ("GET", "/v1/audit-events"),
    ("GET", "/v1/audit-events/{id}"),
    ("GET", "/v1/mcp/discovery"),
    ("POST", "/v1/mcp/tools/{tool_id}"),
}
# Path values and bodies that reach each handler; the probe carries no valid credential.
PATH_VALUES = {"version": "1.0.0", "chunk_index": "0", "tool_id": "query_prometheus",
               "id": "00000000-0000-4000-8000-000000001021"}  # fmt: skip
BODIES = {"/v1/bok/collections/{collection_id}/versions/{version}/search": {"query": "gate"}}


def _application() -> Any:
    # Every optional router mounted: a provider, an MCP client, the audit key and intake.
    return create_application(
        Settings(
            "postgresql://gate:gate@127.0.0.1:1/gate",
            audit_hmac_key="gate-audit-key",
            alert_intake_secret="gate-intake-secret-" + "s" * 16,
        ),
        llm_provider=MagicMock(),
        mcp_client=MagicMock(),
    )


def _gateway_operations(application: Any) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in application.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/v1/")
        and not route.endpoint.__module__.startswith(CONTROL_PACKAGE)
        for method in route.methods
    }


def test_every_documented_governed_scope_is_registered_in_the_gate() -> None:
    application = _application()
    document = application.openapi()
    gateway = _gateway_operations(application)
    registered = governed_operations()
    outside = []
    for path, item in document["paths"].items():
        for method, operation in item.items():
            key = (method.upper(), path)
            if "x-governed-scope" not in operation or key not in gateway:
                continue
            if key in NOT_YET_MIGRATED:
                continue
            declaration = registered.get(key)
            if declaration is None:
                outside.append(key)
                continue
            assert declaration.openapi_extra["x-governed-scope"] == operation["x-governed-scope"]
    assert outside == [], f"governed operations outside the gate: {outside}"


def test_every_gateway_route_is_registered_and_answers_through_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    operations = _gateway_operations(application) - set(EXEMPT)
    registered = set(governed_operations())
    assert not NOT_YET_MIGRATED & registered, "a migrated operation is still listed as pending"
    unregistered = sorted(operations - registered - NOT_YET_MIGRATED)
    assert unregistered == [], f"governed operations outside the gate: {unregistered}"
    # The operations each probe takes into the gate, recorded for that probe alone.
    reached: list[tuple[str, str]] = []
    run = Gate.run

    def observed(gate: Gate[Any], operation: Any, *args: Any, **options: Any) -> Any:
        reached.append((operation.method, operation.path))
        return run(gate, operation, *args, **options)

    monkeypatch.setattr(Gate, "run", observed)
    by_hand = []
    with TestClient(application, raise_server_exceptions=False) as client:
        for method, path in sorted(operations & registered):
            url = path
            for name in [part[1:-1] for part in path.split("/") if part.startswith("{")]:
                url = url.replace("{" + name + "}", PATH_VALUES.get(name, "gate-probe"))
            body = BODIES.get(path, {}) if method in {"POST", "PUT"} else None
            reached.clear()
            client.request(method, url, json=body, headers={"Authorization": "Basic gate"})
            if (method, path) not in reached:
                by_hand.append((method, path))
    assert by_hand == [], f"registered operations answered without the gate: {by_hand}"
