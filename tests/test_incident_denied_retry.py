"""A denied run announces no command the API defers, and a retry is accepted (#788)."""

from __future__ import annotations

import httpx
from test_incident_investigator_http import (
    ADMIN_KEY,
    BLOCKED,
    HUMAN_KEY,
    ScriptedLLM,
    ScriptedMCP,
    _add_incident,
    _application,
    _free_port,
    _grant_run_access,
    _serve,
    _start,
    migrated_database,  # noqa: F401 -- a fresh synthetic DB with no agent MCP grant yet
)


def test_a_denied_run_announces_no_deferred_command_and_a_retry_after_the_grant_advances() -> None:
    """Issue #788: the denied run offers an action the API accepts, a retry on the incident."""
    incident_id = "inc-investigator-denied-retry"
    _add_incident(incident_id)
    _grant_run_access()
    port = _free_port()
    app = _application(f"http://127.0.0.1:{port}", llm=ScriptedLLM(), mcp=ScriptedMCP())
    human = {"Authorization": f"Bearer {HUMAN_KEY}"}
    with _serve(app, port) as base_url, httpx.Client(base_url=base_url, timeout=15) as client:
        # This module's database starts without agent MCP grants: discovery is denied.
        denied = _start(client, incident_id, "investigation-denied-retry-first")
        escalate = client.post(
            f"/v1/incidents/{incident_id}/runs/{denied.json()['run_id']}/commands",
            headers=human | {"Idempotency-Key": "command-escalate-denied-retry"},
            json={
                "command": "escalate",
                "actor": "human",
                "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"},
            },
        )
        for grant_id, action, resource_type, resource_id in (
            ("grant-agent-mcp-discovery-retry", "mcp.discovery", "mcp_server", "grafana-mcp"),
            ("grant-agent-mcp-prometheus-retry", "mcp.invoke", "mcp_tool", "query_prometheus"),
        ):
            granted = client.post(
                "/v1/grants",
                headers={
                    "Authorization": f"Bearer {ADMIN_KEY}",
                    "Idempotency-Key": f"issue-788-create-{grant_id}",
                },
                json={
                    "grant_id": grant_id,
                    "principal_id": "incident-harness",
                    "action": action,
                    "resource": {"resource_type": resource_type, "resource_id": resource_id},
                    "effect": "allow",
                },
            )
            assert granted.status_code == 201, granted.text
        retry = _start(client, incident_id, "investigation-denied-retry-second")

    assert denied.status_code == 201
    assert {key: denied.json()[key] for key in BLOCKED} == BLOCKED
    # escalate stays deferred by this workflow version, and no run announces it any more.
    assert escalate.status_code == 409 and denied.json()["pending_command"] is None
    assert retry.status_code == 201, retry.text
    assert (retry.json()["current_state"], retry.json()["pending_command"]) == (
        "mitigating",
        "approve_mitigation",
    )
