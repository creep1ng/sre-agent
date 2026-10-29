"""Closed, safe causes for an investigation that did not start or did not finish.

Only these codes travel to the timeline and run summary. Provider bodies, MCP
payloads, prompts and raw diagnostics stay in bounded receipt metadata and are
never projected.
"""

from __future__ import annotations

RUN_START_NOT_AUTHORIZED = "run_start_not_authorized"

PROJECTED_REASON_CODES = frozenset({RUN_START_NOT_AUTHORIZED})
