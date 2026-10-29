"""Closed, safe causes for an investigation that did not start or did not finish.

Only these codes travel to the timeline and run summary. Provider bodies, MCP
payloads, prompts and raw diagnostics stay in bounded receipt metadata and are
never projected.
"""

from __future__ import annotations

RUN_START_NOT_AUTHORIZED = "run_start_not_authorized"

# The cause of each dispatch ending the dispatcher records, as the operator reads it (#705).
DISPATCH_CAUSES = {
    "harness_not_configured": "the investigator gateway is not configured.",
    "harness_identity_unavailable": "the investigator's agent identity is inactive or missing; "
    "reactivate it in Principals or ask an administrator.",
    "mcp_discovery_denied": "the agent identity has no grant to discover the MCP tools.",
    "mcp_discovery_rejected": "the MCP server is not configured or rejected tool discovery.",
    "mcp_discovery_transient": "the MCP server did not answer tool discovery.",
    "governed_call_denied": "a governed call of the agent was denied.",
    "investigation_mcp_contract_rejected": "an MCP call did not match the tool contract.",
    "investigation_upstream_unavailable": "the model provider was unavailable.",
    "investigation_tool_unavailable": "an MCP tool failed or did not answer in time.",
    "tool_timeout": "an MCP tool did not answer within the investigator's tool timeout.",
    "investigation_max_steps": "the agent used its whole step budget.",
    "investigation_invalid_output": "the model returned output the harness cannot use.",
    "investigation_no_measured_evidence": "no cited evidence had measured data.",
    "investigator_failed": "the investigator failed unexpectedly.",
    "result_persistence_uncertain": "the result could not be confirmed as saved.",
    "stale_incident_snapshot": "the incident changed while the agent investigated.",
    "producer_interrupted": "the previous dispatch was interrupted.",
    # Recorded by triage when the declarant may declare but not start runs (#704).
    RUN_START_NOT_AUTHORIZED: "the declarant lacks the run.start grant; "
    "an administrator must grant it, then a new run may retry.",
}

PROJECTED_REASON_CODES = frozenset(DISPATCH_CAUSES)
