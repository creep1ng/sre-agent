"""Bounded investigator loop (issue #185, ADR-007).

A stateless reducer: it reads the request, talks to the gateway and the evidence provider
through their ports and returns a validated result. It never writes incident state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from secrets import token_hex

from sre_agent.investigator.contract import (
    CollectedEvidence,
    InvalidOutput,
    InvestigationRequest,
    InvestigationResult,
    Limits,
    Outcome,
    RequestHuman,
    Status,
    ToolInvocation,
    Turn,
    UseTool,
    parse_action,
    task_id_for,
    unknown_references,
)
from sre_agent.investigator.ports import (
    EvidenceProvider,
    EvidenceUnavailable,
    Gateway,
    GatewayError,
    GatewayReply,
)
from sre_agent.investigator.prompt import assemble

MAX_INPUT = 65_536
MAX_OUTPUT = 65_536


def _new_id(prefix: str) -> str:
    return f"{prefix}_{token_hex(8)}"


def _now() -> datetime:
    return datetime.now(UTC)


async def investigate(
    request: InvestigationRequest,
    gateway: Gateway,
    provider: EvidenceProvider,
    limits: Limits | None = None,
    new_id: Callable[[str], str] = _new_id,
    clock: Callable[[], datetime] = _now,
) -> InvestigationResult:
    limits = limits or Limits()
    turns: list[Turn] = []
    evidence: list[CollectedEvidence] = []
    feedback: str | None = None

    def finish(
        status: Status, outcome: Outcome | None = None, detail: str | None = None
    ) -> InvestigationResult:
        return InvestigationResult(
            incident_id=request.incident_id,
            run_id=request.run_id,
            status=status,
            outcome=outcome,
            detail=detail[:500] if detail else None,
            evidence=evidence,
            turns=turns,
        )

    while len(turns) < limits.max_steps:
        turn_id = new_id("turn")
        prompt = assemble(request, evidence, turns, limits.max_steps - len(turns), feedback)
        if len(prompt) > MAX_INPUT:
            return finish("needs_human", detail="assembled input exceeds the gateway limit")
        try:
            reply = await _respond(gateway, request, prompt, task_id_for(turn_id), limits)
        except GatewayError as error:
            if error.kind == "denied":
                return finish("denied", detail=str(error))
            if error.kind == "transient":
                return finish("upstream_unavailable", detail=str(error))
            return finish("needs_human", detail=str(error))
        turn = Turn(
            turn_id=turn_id,
            task_id=task_id_for(turn_id),
            sequence=len(turns),
            assembled_input=prompt,
            model_output=reply.text if len(reply.text) <= MAX_OUTPUT else None,
            request_id=reply.request_id,
            occurred_at=clock(),
        )
        try:
            if len(reply.text) > MAX_OUTPUT:
                raise InvalidOutput("output exceeds the 65536-character limit")
            action = parse_action(reply.text)
            unknown = unknown_references(action, request, {item.evidence_id for item in evidence})
            if unknown:
                raise InvalidOutput("unknown references: " + ", ".join(unknown))
        except InvalidOutput as error:
            turns.append(turn)
            if feedback is not None:
                return finish("invalid_output", detail=str(error))
            feedback = str(error)
            continue
        feedback = None
        if not isinstance(action, UseTool):
            turns.append(turn)
            if isinstance(action, RequestHuman):
                return finish("needs_human", outcome=action)
            return finish("completed", outcome=action)
        if not request.authorizes_tool(action.tool):
            turns.append(turn)
            return finish("denied", detail=f"tool not authorized: {action.tool}")
        try:
            result = await asyncio.wait_for(
                provider.collect(action.tool, action.arguments), limits.tool_timeout_seconds
            )
        except (EvidenceUnavailable, TimeoutError):
            turns.append(turn)
            return finish("upstream_unavailable", detail=f"tool failed: {action.tool}")
        evidence.append(
            CollectedEvidence(
                evidence_id=new_id("ev"),
                source=result.source,
                tool=action.tool,
                datasource_uid=result.datasource_uid,
                query=result.query,
                time_window=result.time_window,
                summary=result.summary[:8000],
                collected_at=clock(),
                request_id=reply.request_id,
            )
        )
        invocation = ToolInvocation(
            tool=action.tool, arguments=action.arguments, result_summary=result.summary[:8000]
        )
        turns.append(turn.model_copy(update={"tool_invocation": invocation}))
    return finish("max_steps", detail=f"step budget of {limits.max_steps} exhausted")


async def _respond(
    gateway: Gateway, request: InvestigationRequest, prompt: str, task_id: str, limits: Limits
) -> GatewayReply:
    """One turn's gateway call; a transient failure repeats the same turn."""
    for attempt in range(limits.transient_retries + 1):
        try:
            return await asyncio.wait_for(
                gateway.respond(
                    input=prompt,
                    incident_id=request.incident_id,
                    run_id=request.run_id,
                    task_id=task_id,
                ),
                limits.gateway_timeout_seconds,
            )
        except (GatewayError, TimeoutError) as raised:
            error = raised if isinstance(raised, GatewayError) else GatewayError("transient")
            if error.kind != "transient" or attempt == limits.transient_retries:
                raise error from None
    raise AssertionError("unreachable")
