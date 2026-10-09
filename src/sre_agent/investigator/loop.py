"""Bounded investigator loop (issue #185, ADR-007).

A stateless reducer: it reads the request, talks to the gateway and the evidence provider
through their ports and returns a validated result. It never writes incident state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from secrets import token_hex
from typing import TypeVar
from uuid import UUID

from sre_agent.investigator.contract import (
    CollectedEvidence,
    FailureDiagnostic,
    InvalidOutput,
    InvestigationRequest,
    InvestigationResult,
    Limits,
    Outcome,
    PinnedSkill,
    RequestHuman,
    SkillPin,
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
    ResolvedSkill,
    SkillSource,
)
from sre_agent.investigator.prompt import assemble

MAX_INPUT = 65_536
MAX_OUTPUT = 65_536
T = TypeVar("T")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{token_hex(8)}"


def _now() -> datetime:
    return datetime.now(UTC)


def _digests(skill: ResolvedSkill) -> list[tuple[str, str]]:
    return [(item.ref, item.content_sha256) for item in (skill, *skill.dependencies)]


async def _resolve(
    source: SkillSource, pins: Sequence[SkillPin], first: Sequence[ResolvedSkill] = ()
) -> list[ResolvedSkill]:
    """Resolve each exact pinned Skill; failure details never contain its content."""
    resolved: list[ResolvedSkill] = []
    for index, pin in enumerate(pins):
        ref = f"{pin.skill_id}@{pin.version}"
        try:
            skill = await source.resolve(pin.skill_id, pin.version)
        except GatewayError as error:
            reason = {"denied": "unavailable", "transient": "unreachable"}.get(error.kind)
            detail = f"skill {reason or 'rejected'}: {ref}"
            raise GatewayError(
                error.kind, error.status, detail, request_id=error.request_id
            ) from None
        if pin.content_sha256 not in (None, skill.content_sha256) or (
            first and _digests(skill) != _digests(first[index])
        ):
            raise GatewayError("rejected", detail=f"skill content changed: {ref}")
        resolved.append(skill)
    return resolved


def _pinned(skill: ResolvedSkill) -> PinnedSkill:
    return PinnedSkill(
        skill_id=skill.skill_id,
        version=skill.version,
        content_sha256=skill.content_sha256,
        dependencies=[
            SkillPin(
                skill_id=item.skill_id,
                version=item.version,
                content_sha256=item.content_sha256,
            )
            for item in skill.dependencies
        ],
        request_id=skill.request_id,
    )


async def investigate(
    request: InvestigationRequest,
    gateway: Gateway,
    provider: EvidenceProvider,
    limits: Limits | None = None,
    new_id: Callable[[str], str] = _new_id,
    clock: Callable[[], datetime] = _now,
    skills: SkillSource | None = None,
) -> InvestigationResult:
    limits = limits or Limits()
    turns: list[Turn] = []
    evidence: list[CollectedEvidence] = []
    request_ids: list[UUID] = []
    mcp_request_ids: list[UUID] = []
    feedback: str | None = None
    loaded: list[ResolvedSkill] = []
    if request.skills and skills is None:
        raise ValueError("a request that pins Skills needs a Skill source")

    def record_skill_ids(resolved: Sequence[ResolvedSkill]) -> None:
        for skill in resolved:
            if skill.request_id not in request_ids:
                request_ids.append(skill.request_id)
            for dependency in skill.dependencies:
                if dependency.request_id not in request_ids:
                    request_ids.append(dependency.request_id)

    def finish(
        status: Status,
        outcome: Outcome | None = None,
        detail: str | None = None,
        failure_diagnostic: FailureDiagnostic | None = None,
    ) -> InvestigationResult:
        return InvestigationResult(
            incident_id=request.incident_id,
            run_id=request.run_id,
            status=status,
            outcome=outcome,
            detail=detail[:500] if detail else None,
            evidence=evidence,
            turns=turns,
            skills=[_pinned(skill) for skill in loaded],
            request_ids=request_ids,
            mcp_request_ids=mcp_request_ids,
            remaining_step_budget=max(0, limits.max_steps - len(turns)),
            failure_diagnostic=failure_diagnostic,
        )

    async def revalidate() -> None:
        if skills is not None and loaded:
            resolved = await _attempts(lambda: _resolve(skills, request.skills, loaded), limits)
            record_skill_ids(resolved)

    if skills is not None and request.skills:
        try:
            loaded = await _attempts(lambda: _resolve(skills, request.skills), limits)
            record_skill_ids(loaded)
        except GatewayError as error:
            if error.request_id is not None and error.request_id not in request_ids:
                request_ids.append(error.request_id)
            diagnostic = None
            if error.kind in {"denied", "transient"}:
                diagnostic = FailureDiagnostic(
                    stage="gateway_transport",
                    kind=error.kind,
                    http_status=error.status,
                    request_id=error.request_id,
                )
            status: Status = (
                "denied"
                if error.kind == "denied"
                else "upstream_unavailable"
                if error.kind == "transient"
                else "needs_human"
            )
            return finish(status, detail=str(error), failure_diagnostic=diagnostic)

    while len(turns) < limits.max_steps:
        turn_id = new_id("turn")
        prompt = assemble(request, evidence, turns, limits.max_steps - len(turns), feedback, loaded)
        if len(prompt) > MAX_INPUT:
            return finish("needs_human", detail="assembled input exceeds the gateway limit")
        try:
            reply = await _respond(
                gateway, request, prompt, task_id_for(turn_id), limits, revalidate
            )
        except GatewayError as error:
            if error.request_id is not None and error.request_id not in request_ids:
                request_ids.append(error.request_id)
            if error.kind == "denied":
                failure_diagnostic = None
                if error.status is None or error.status >= 500:
                    failure_diagnostic = FailureDiagnostic(
                        stage="gateway_transport",
                        kind=error.kind,
                        http_status=error.status,
                        request_id=error.request_id,
                    )
                return finish("denied", detail=str(error), failure_diagnostic=failure_diagnostic)
            if error.kind == "transient":
                failure_diagnostic = None
                if error.status is None or error.status >= 500:
                    failure_diagnostic = FailureDiagnostic(
                        stage="gateway_transport",
                        kind=error.kind,
                        http_status=error.status,
                        request_id=error.request_id,
                    )
                return finish(
                    "upstream_unavailable",
                    detail=str(error),
                    failure_diagnostic=failure_diagnostic,
                )
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
        request_ids.append(reply.request_id)
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
        except (EvidenceUnavailable, TimeoutError) as error:
            turns.append(turn)
            if isinstance(error, EvidenceUnavailable) and error.request_id is not None:
                request_ids.append(error.request_id)
                mcp_request_ids.append(error.request_id)
            status: Status = (
                "denied"
                if isinstance(error, EvidenceUnavailable) and error.kind == "denied"
                else "pre_dispatch_rejected"
                if isinstance(error, EvidenceUnavailable)
                and error.kind == "rejected"
                and error.status == 422
                else "upstream_unavailable"
            )
            failure_diagnostic = None
            if (
                isinstance(error, EvidenceUnavailable)
                and error.kind == "transient"
                and error.status is not None
                and error.status >= 500
            ):
                failure_diagnostic = FailureDiagnostic(
                    stage="gateway_transport",
                    kind=error.kind,
                    http_status=error.status,
                    request_id=error.request_id,
                )
            elif (
                isinstance(error, EvidenceUnavailable)
                and error.kind == "rejected"
                and error.status == 200
            ):
                failure_diagnostic = FailureDiagnostic(
                    stage="mcp_response_validation",
                    kind=error.kind,
                    http_status=error.status,
                    request_id=error.request_id,
                )
            return finish(
                status,
                detail=f"tool failed: {action.tool}",
                failure_diagnostic=failure_diagnostic,
            )
        if result.request_id is not None:
            request_ids.append(result.request_id)
            mcp_request_ids.append(result.request_id)
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
                request_id=result.request_id,
            )
        )
        invocation = ToolInvocation(
            tool=action.tool, arguments=action.arguments, result_summary=result.summary[:8000]
        )
        turns.append(turn.model_copy(update={"tool_invocation": invocation}))
    return finish("max_steps", detail=f"step budget of {limits.max_steps} exhausted")


async def _respond(
    gateway: Gateway,
    request: InvestigationRequest,
    prompt: str,
    task_id: str,
    limits: Limits,
    revalidate: Callable[[], Awaitable[None]],
) -> GatewayReply:
    """Make one model request; a timeout or 5xx may follow an accepted request."""
    try:
        await revalidate()
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
        raise error from None


async def _attempts(call: Callable[[], Awaitable[T]], limits: Limits) -> T:
    """Retry only idempotent, read-only Skill resolution requests."""
    for attempt in range(limits.transient_retries + 1):
        try:
            return await asyncio.wait_for(call(), limits.gateway_timeout_seconds)
        except (GatewayError, TimeoutError) as raised:
            error = raised if isinstance(raised, GatewayError) else GatewayError("transient")
            if error.kind != "transient" or attempt == limits.transient_retries:
                raise error from None
    raise AssertionError("unreachable")
