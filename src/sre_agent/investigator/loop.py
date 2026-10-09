"""Bounded investigator loop (issue #185, ADR-007).

A stateless reducer: it reads the request, talks to the gateway and the evidence provider
through their ports and returns a validated result. It never writes incident state.

Skills (issue #32): the request pins exact versions, resolved through the gateway before
the first model call and again before every one, retries included, with no cache. A version
that is unavailable, or whose digest is not the one the run recorded, ends the run before
the model sees anything from it.

BoK (issue #34): the model searches only the exact collection versions the run authorizes,
always through the gateway and with no cache. Each fragment becomes evidence whose `query` is
the locator that reads it again; an empty search is an answer, and a failure ends the run
without fixtures.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from functools import partial
from secrets import token_hex
from typing import TypeVar

from sre_agent.investigator.contract import (
    CollectedEvidence,
    InvalidOutput,
    InvestigationRequest,
    InvestigationResult,
    Limits,
    Outcome,
    PinnedSkill,
    RequestHuman,
    SearchBoK,
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
    BoKFragment,
    BoKSource,
    EvidenceProvider,
    EvidenceUnavailable,
    Gateway,
    GatewayError,
    GatewayReply,
    ResolvedSkill,
    SkillSource,
)
from sre_agent.investigator.prompt import assemble

T = TypeVar("T")

MAX_INPUT = 65_536
MAX_OUTPUT = 65_536
BOK_RESULTS = 5
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{token_hex(8)}"


def _now() -> datetime:
    return datetime.now(UTC)


def _digests(skill: ResolvedSkill) -> list[tuple[str, str]]:
    return [(item.ref, item.content_sha256) for item in (skill, *skill.dependencies)]


async def _resolve(
    source: SkillSource, pins: Sequence[SkillPin], first: Sequence[ResolvedSkill] = ()
) -> list[ResolvedSkill]:
    """Resolve every pinned version now; the detail names a version, never its content."""
    resolved: list[ResolvedSkill] = []
    for index, pin in enumerate(pins):
        ref = f"{pin.skill_id}@{pin.version}"
        try:
            skill = await source.resolve(pin.skill_id, pin.version)
        except GatewayError as error:
            reason = {"denied": "unavailable", "transient": "unreachable"}.get(error.kind)
            detail = f"skill {reason or 'rejected'}: {ref}"
            raise GatewayError(error.kind, error.status, detail) from None
        if pin.content_sha256 not in (None, skill.content_sha256) or (
            first and _digests(skill) != _digests(first[index])
        ):
            raise GatewayError("rejected", detail=f"skill content changed: {ref}")
        resolved.append(skill)
    return resolved


async def _search(source: BoKSource, ask: SearchBoK) -> list[BoKFragment]:
    """Fragments of exactly the version asked for, with a locator inside #332's contract and
    never more than asked; anything else is `rejected`, so no citation mixes versions."""
    collection_id, version = ask.collection.split("@")
    found = await source.search(collection_id, version, ask.query, BOK_RESULTS)
    if len(found) > BOK_RESULTS or any(
        (item.collection_id, item.version) != (collection_id, version)
        or not (_ID.fullmatch(item.document_id) and _ID.fullmatch(item.section_id))
        or not 0 <= item.chunk_index <= 1_000_000
        for item in found
    ):
        raise GatewayError("rejected")
    return found


def _locator(item: BoKFragment) -> str:
    """The producer's read of exactly this chunk (#332)."""
    return (
        f"/v1/bok/collections/{item.collection_id}/versions/{item.version}/chunks/"
        f"{item.document_id}/{item.section_id}/{item.chunk_index}"
    )


def _bok_failure(error: GatewayError, collection: str) -> GatewayError:
    """Named after the collection version, never after its content."""
    if error.kind == "denied":
        detail = f"bok collection unavailable: {collection}"
    elif error.kind == "transient":
        detail = f"bok search failed: {collection} ({error.code or error.status or 'network'})"
    else:
        detail = f"bok answer rejected: {collection}"
    return GatewayError(error.kind, error.status, detail)


def _pinned(skill: ResolvedSkill) -> PinnedSkill:
    return PinnedSkill(
        skill_id=skill.skill_id,
        version=skill.version,
        content_sha256=skill.content_sha256,
        dependencies=[
            SkillPin(
                skill_id=item.skill_id, version=item.version, content_sha256=item.content_sha256
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
    bok: BoKSource | None = None,
) -> InvestigationResult:
    limits = limits or Limits()
    turns: list[Turn] = []
    evidence: list[CollectedEvidence] = []
    feedback: str | None = None
    loaded: list[ResolvedSkill] = []
    if request.skills and skills is None:
        raise ValueError("a request that pins Skills needs a Skill source")
    if request.bok_collections() and bok is None:
        raise ValueError("a request that authorizes BoK collections needs a BoK source")

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
            skills=[_pinned(skill) for skill in loaded],
        )

    def failed(error: GatewayError) -> InvestigationResult:
        if error.kind == "denied":
            return finish("denied", detail=str(error))
        if error.kind == "transient":
            return finish("upstream_unavailable", detail=str(error))
        return finish("needs_human", detail=str(error))

    async def revalidate() -> None:
        if skills is not None and loaded:
            await _resolve(skills, request.skills, loaded)

    if skills is not None and request.skills:
        source = skills
        try:
            loaded = await _attempts(lambda: _resolve(source, request.skills), limits)
        except GatewayError as error:
            return failed(error)

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
            return failed(error)
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
            if isinstance(action, SearchBoK) and not request.bok_collections():
                raise InvalidOutput("search_bok is not offered in this run")
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
        if isinstance(action, SearchBoK):
            ask = action
            if bok is None or ask.collection not in request.bok_collections():
                turns.append(turn)
                return finish("denied", detail=f"bok collection not authorized: {ask.collection}")
            try:
                found = await _attempts(partial(_search, bok, ask), limits)
            except GatewayError as error:
                turns.append(turn)
                return failed(_bok_failure(error, ask.collection))
            collected = [
                CollectedEvidence(
                    evidence_id=new_id("ev"),
                    source="bok",
                    tool="bok.search",
                    datasource_uid=ask.collection,
                    query=_locator(item),
                    summary=f"{item.title} ({item.source_ref}): {item.content}"[:8000],
                    collected_at=clock(),
                    request_id=reply.request_id,
                )
                for item in found
            ]
            evidence.extend(collected)
            invocation = ToolInvocation(
                tool="bok.search",
                arguments={"collection": ask.collection, "query": ask.query},
                result_summary=", ".join(item.evidence_id for item in collected) or "no results",
            )
            turns.append(turn.model_copy(update={"tool_invocation": invocation}))
            continue
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


async def _attempts(call: Callable[[], Awaitable[T]], limits: Limits) -> T:
    """One bounded gateway exchange; a transient failure repeats it once."""
    for attempt in range(limits.transient_retries + 1):
        try:
            return await asyncio.wait_for(call(), limits.gateway_timeout_seconds)
        except (GatewayError, TimeoutError) as raised:
            timeout = GatewayError("transient", code="timeout")
            error = raised if isinstance(raised, GatewayError) else timeout
            if error.kind != "transient" or attempt == limits.transient_retries:
                raise error from None
    raise AssertionError("unreachable")


async def _respond(
    gateway: Gateway,
    request: InvestigationRequest,
    prompt: str,
    task_id: str,
    limits: Limits,
    revalidate: Callable[[], Awaitable[None]],
) -> GatewayReply:
    """One turn's gateway call, its pinned Skills revalidated first; a transient failure
    repeats the same turn, revalidation included."""

    async def call() -> GatewayReply:
        await revalidate()
        return await gateway.respond(
            input=prompt, incident_id=request.incident_id, run_id=request.run_id, task_id=task_id
        )

    return await _attempts(call, limits)
