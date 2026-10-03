"""Skills in the investigator loop (issue #32): pinned for the run, revalidated before every use.

Written from what the loop could get wrong: send the model a Skill the gateway refused, keep
using one after its grant is revoked, resume with other content than the run recorded, or lose
or repeat a dependency. The Skill source here is a fake; the HTTP adapter has its own tests.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError
from test_investigator_loop import HYPOTHESIS, STATE, TOOL, Provider, ScriptedGateway, ids

from sre_agent.investigator.contract import InvestigationRequest, InvestigationResult, Limits
from sre_agent.investigator.loop import investigate
from sre_agent.investigator.ports import GatewayError, ResolvedSkill

PIN = {"skill_id": "incident-triage", "version": "1.0.0"}
UNAVAILABLE = "skill unavailable: incident-triage@1.0.0"


def skill(name: str, digest: str = "a", *dependencies: ResolvedSkill) -> ResolvedSkill:
    instructions = f"{name}-instructions"
    return ResolvedSkill(
        name, "1.0.0", digest * 64, name.title(), instructions, dependencies, uuid4()
    )


TRIAGE = skill("incident-triage")
DENIED, TRANSIENT = GatewayError("denied", 404), GatewayError("transient", 503)


class Skills:
    """Answers each resolution in order; the last answer repeats."""

    def __init__(self, *answers: ResolvedSkill | GatewayError) -> None:
        self.answers = list(answers)
        self.calls: list[str] = []

    async def resolve(self, skill_id: str, version: str) -> ResolvedSkill:
        self.calls.append(f"{skill_id}@{version}")
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, GatewayError):
            raise answer
        return answer


def request_for(pins: list[dict[str, Any]]) -> InvestigationRequest:
    state = yaml.safe_load(STATE.read_text(encoding="utf-8"))
    return InvestigationRequest.model_validate(
        {
            "incident_id": state["incident_id"],
            "run_id": "run_a1b2c3d4e5",
            "objective": "investigate",
            "context": state,
            "authorized_capabilities": state["authorized_capabilities"],
            "skills": pins,
        }
    )


def run(
    gateway: ScriptedGateway, skills: Skills, pins: list[dict[str, Any]]
) -> InvestigationResult:
    request = request_for(pins)
    return asyncio.run(investigate(request, gateway, Provider(), Limits(), ids(), skills=skills))


def test_a_pinned_skill_reaches_every_model_call_and_is_recorded() -> None:
    gateway, source = ScriptedGateway(TOOL, HYPOTHESIS), Skills(TRIAGE)
    result = run(gateway, source, [PIN])

    assert result.status == "completed"
    assert all("incident-triage-instructions" in call["input"] for call in gateway.calls)
    # One resolution to pin the version, then one before each of the two model calls.
    assert source.calls == ["incident-triage@1.0.0"] * 3
    assert [pin.model_dump() for pin in result.skills] == [
        {**PIN, "content_sha256": "a" * 64, "dependencies": [], "request_id": TRIAGE.request_id}
    ]


@pytest.mark.parametrize(
    ("answers", "pin", "status", "detail"),
    [
        ([DENIED], PIN, "denied", UNAVAILABLE),
        ([GatewayError("denied", 401)], PIN, "denied", UNAVAILABLE),
        ([TRANSIENT], PIN, "upstream_unavailable", "skill unreachable: incident-triage@1.0.0"),
        (
            [GatewayError("rejected", 200)],
            PIN,
            "needs_human",
            "skill rejected: incident-triage@1.0.0",
        ),
        (
            [TRIAGE],
            {**PIN, "content_sha256": "b" * 64},
            "needs_human",
            "skill content changed: incident-triage@1.0.0",
        ),
    ],
    ids=["missing", "unauthenticated", "unreachable", "malformed", "other-digest"],
)
def test_a_skill_that_cannot_be_used_never_reaches_the_model(
    answers: list[Any], pin: dict[str, Any], status: str, detail: str
) -> None:
    gateway = ScriptedGateway(HYPOTHESIS)
    result = run(gateway, Skills(*answers), [pin])

    assert (result.status, result.detail) == (status, detail)
    assert (gateway.calls, result.turns, result.skills) == ([], [], [])


@pytest.mark.parametrize(
    ("third", "status"),
    [(DENIED, "denied"), (skill("incident-triage", "c"), "needs_human")],
    ids=["revoked", "content-changed"],
)
def test_a_skill_that_stops_being_usable_stops_the_next_model_call(
    third: ResolvedSkill | GatewayError, status: str
) -> None:
    gateway = ScriptedGateway(TOOL, HYPOTHESIS)
    result = run(gateway, Skills(TRIAGE, TRIAGE, third), [PIN])

    assert (result.status, len(gateway.calls), len(result.turns)) == (status, 1, 1)
    # The record still says which version the run used before it stopped.
    assert [pin.content_sha256 for pin in result.skills] == ["a" * 64]


def test_a_transient_revalidation_is_retried_with_its_model_call() -> None:
    gateway, source = ScriptedGateway(HYPOTHESIS), Skills(TRIAGE, TRANSIENT, TRIAGE)
    result = run(gateway, source, [PIN])

    assert (result.status, len(gateway.calls), len(source.calls)) == ("completed", 1, 3)


def test_resuming_asks_only_for_the_recorded_version_and_digest() -> None:
    gateway, source = ScriptedGateway(HYPOTHESIS), Skills(TRIAGE)
    result = run(gateway, source, [{**PIN, "content_sha256": "a" * 64}])

    assert result.status == "completed" and set(source.calls) == {"incident-triage@1.0.0"}


def test_dependencies_are_recorded_and_given_to_the_model_once() -> None:
    shared = skill("evidence-rules", "d")
    first, second = skill("incident-triage", "a", shared), skill("postmortem-writer", "e", shared)
    gateway = ScriptedGateway(HYPOTHESIS)
    pins = [PIN, {"skill_id": "postmortem-writer", "version": "1.0.0"}]
    result = run(gateway, Skills(first, second, first, second), pins)

    prompt = gateway.calls[0]["input"]
    assert prompt.count("evidence-rules-instructions") == 1
    assert prompt.index("postmortem-writer-instructions") < prompt.index("State: ")
    digests = [[item.content_sha256 for item in pin.dependencies] for pin in result.skills]
    assert digests == [["d" * 64], ["d" * 64]]


def test_a_run_pins_one_version_of_each_skill() -> None:
    with pytest.raises(ValidationError, match="one version of each Skill"):
        run(ScriptedGateway(), Skills(TRIAGE), [PIN, {**PIN, "version": "2.0.0"}])
