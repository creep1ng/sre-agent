"""BoK in the investigator loop (issue #34): exact authorized versions, provenance, no cache.

Written from what the loop could get wrong: search a collection or version the run does not
authorize, lose where a fragment came from, put two versions under one citation, take an empty
search for a failure or a failure for an empty one, answer from fixtures instead, or keep using
content after a revocation. The BoK source here is a fake; the HTTP adapter has its own tests.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from test_investigator_loop import STATE, Provider, ScriptedGateway, hypothesis, ids

from sre_agent.investigator.contract import InvestigationRequest, InvestigationResult, Limits
from sre_agent.investigator.loop import investigate
from sre_agent.investigator.ports import BoKFragment, GatewayError

EVIDENCE_SCHEMA = Path(__file__).parents[1] / "agent/schemas/incident-state.schema.yaml"
RESPONSE = "demo-incident-response@1.0.0"
OPERATIONS = "demo-platform-operations@1.0.0"
LOCATOR = (
    "/v1/bok/collections/demo-incident-response/versions/1.0.0/chunks/incident-triage/severity/0"
)
CONCLUDE = '{"action": "conclude", "summary": "No guidance applies.", "supporting_evidence": []}'
UNAVAILABLE, FAILED = f"bok collection unavailable: {RESPONSE}", f"bok search failed: {RESPONSE}"
REJECTED = f"bok answer rejected: {RESPONSE}"
NOT_READY = GatewayError("transient", 503, code="index_unavailable")
DOWN = GatewayError("transient", 503, code="storage_unavailable")


def search(collection: str = RESPONSE, query: str = "severity impact") -> str:
    return json.dumps({"action": "search_bok", "collection": collection, "query": query})


def fragment(collection: str = RESPONSE, chunk_index: int = 0) -> BoKFragment:
    collection_id, version = collection.split("@")
    return BoKFragment(
        collection_id, version, "incident-triage", "severity", chunk_index, "Incident triage",
        "synthetic://incident-response/triage",
        "Assign severity from customer impact, scope, and active risk.",
    )  # fmt: skip


class BoK:
    """Answers each search in order, the last answer repeating; a number is seconds of silence."""

    def __init__(self, *answers: list[BoKFragment] | GatewayError | float) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str, str, int]] = []

    async def search(
        self, collection_id: str, version: str, query: str, limit: int
    ) -> list[BoKFragment]:
        self.calls.append((collection_id, version, query, limit))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, float):
            await asyncio.sleep(answer)
            return []
        if isinstance(answer, GatewayError):
            raise answer
        return answer


def allowed(collection: str = RESPONSE, action: str | None = "bok.search") -> dict[str, Any]:
    """A capability of the run, not a gateway grant: the gateway still decides."""
    return {"resource_type": "bok_collection", "resource_id": collection, "action": action}


def request_for(*capabilities: dict[str, Any]) -> InvestigationRequest:
    state = yaml.safe_load(STATE.read_text(encoding="utf-8"))
    return InvestigationRequest.model_validate(
        {
            "incident_id": state["incident_id"],
            "run_id": "run_a1b2c3d4e5",
            "objective": "investigate",
            "context": state,
            "authorized_capabilities": [*state["authorized_capabilities"], *capabilities],
        }
    )


def run(
    gateway: ScriptedGateway,
    bok: BoK | None,
    *capabilities: dict[str, Any],
    provider: Provider | None = None,
    limits: Limits | None = None,
) -> InvestigationResult:
    request, evidence = request_for(*capabilities), provider or Provider()
    return asyncio.run(investigate(request, gateway, evidence, limits or Limits(), ids(), bok=bok))


def state_of(call: dict[str, str]) -> dict[str, Any]:
    line = next(line for line in call["input"].splitlines() if line.startswith("State: "))
    return json.loads(line.removeprefix("State: "))


def test_a_fragment_becomes_citable_evidence_that_keeps_its_provenance() -> None:
    gateway, bok = ScriptedGateway(search(), hypothesis("ev_00000000")), BoK([fragment()])
    result = run(gateway, bok, allowed())

    assert result.status == "completed"
    assert bok.calls == [("demo-incident-response", "1.0.0", "severity impact", 5)]
    [item] = result.evidence
    # Collection and version, then the locator that reads exactly this chunk again.
    assert (item.evidence_id, item.source, item.tool, item.datasource_uid, item.query) == (
        "ev_00000000", "bok", "bok.search", RESPONSE, LOCATOR,
    )  # fmt: skip
    assert item.summary == (
        "Incident triage (synthetic://incident-response/triage): "
        "Assign severity from customer impact, scope, and active risk."
    )
    schema = yaml.safe_load(EVIDENCE_SCHEMA.read_text(encoding="utf-8"))["$defs"]["evidence"]
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        item.model_dump(mode="json")
    )
    # The next model call reads the fragment as data, with where it can be read again.
    [seen] = state_of(gateway.calls[1])["collected_evidence"]
    assert (seen["query"], seen["summary"]) == (item.query, item.summary)


@pytest.mark.parametrize(
    ("authorized", "asked"),
    [
        ([allowed()], OPERATIONS),
        ([allowed()], "demo-incident-response@2.0.0"),
        ([allowed(), allowed(OPERATIONS, "bok.read")], OPERATIONS),
    ],
    ids=["other-collection", "other-version", "other-action"],
)
def test_only_an_authorized_exact_version_is_searched(
    authorized: list[dict[str, Any]], asked: str
) -> None:
    gateway, bok, provider = ScriptedGateway(search(asked)), BoK([fragment()]), Provider()
    result = run(gateway, bok, *authorized, provider=provider)

    assert (result.status, result.detail) == ("denied", f"bok collection not authorized: {asked}")
    assert (bok.calls, provider.calls, result.evidence, gateway.replies) == ([], [], [], [])


def test_an_empty_search_is_an_answer_and_the_run_goes_on() -> None:
    gateway, bok = ScriptedGateway(search(), CONCLUDE), BoK([])
    result = run(gateway, bok, allowed())

    assert (result.status, result.evidence) == ("completed", [])
    [call] = state_of(gateway.calls[1])["tool_calls"]
    assert (call["tool"], call["result"]) == ("bok.search", "no results")


@pytest.mark.parametrize(
    ("failure", "status", "detail", "calls"),
    [
        (GatewayError("denied", 403), "denied", UNAVAILABLE, 1),
        (NOT_READY, "upstream_unavailable", f"{FAILED} (index_unavailable)", 2),
        (DOWN, "upstream_unavailable", f"{FAILED} (storage_unavailable)", 2),
        (GatewayError("rejected", 422), "needs_human", REJECTED, 1),
    ],
    ids=["denied", "collection-not-ready", "storage-down", "unexpected-answer"],
)
def test_each_failure_is_told_apart_and_never_answered_from_fixtures(
    failure: GatewayError, status: str, detail: str, calls: int
) -> None:
    gateway, bok, provider = ScriptedGateway(search()), BoK(failure), Provider()
    result = run(gateway, bok, allowed(), provider=provider)

    assert (result.status, result.detail, len(bok.calls)) == (status, detail, calls)
    assert (result.evidence, provider.calls, gateway.replies) == ([], [], [])


def test_a_search_that_does_not_answer_in_time_is_a_bounded_failure() -> None:
    gateway, bok = ScriptedGateway(search()), BoK(1.0)
    result = run(gateway, bok, allowed(), limits=Limits(gateway_timeout_seconds=0.05))

    assert (result.status, len(bok.calls), result.evidence) == ("upstream_unavailable", 2, [])
    assert result.detail == f"{FAILED} (timeout)"


@pytest.mark.parametrize(
    "answer",
    [
        [fragment("demo-incident-response@2.0.0")],
        [fragment(OPERATIONS)],
        [fragment(chunk_index=index) for index in range(6)],
        [replace(fragment(), document_id="../admin")],
        [replace(fragment(), section_id="Severity/0")],
        [fragment(chunk_index=1_000_001)],
    ],
    ids=(
        "other-version other-collection more-than-asked unsafe-document unsafe-section "
        "index-out-of-range"
    ).split(),
)
def test_an_answer_outside_the_search_is_never_cited(answer: list[BoKFragment]) -> None:
    gateway, bok = ScriptedGateway(search(), hypothesis("ev_00000000")), BoK(answer)
    result = run(gateway, bok, allowed())

    assert (result.status, result.detail) == ("needs_human", REJECTED)
    assert result.evidence == [] and len(gateway.replies) == 1


def test_a_revocation_stops_the_next_search_without_serving_a_stored_answer() -> None:
    gateway = ScriptedGateway(search(), search())
    bok = BoK([fragment()], GatewayError("denied", 403))
    result = run(gateway, bok, allowed())

    assert (result.status, result.detail, len(bok.calls)) == ("denied", UNAVAILABLE, 2)
    assert [item.evidence_id for item in result.evidence] == ["ev_00000000"]


def test_a_citation_of_a_fragment_the_run_never_received_is_invalid() -> None:
    cite = hypothesis("ev_00000000")
    result = run(ScriptedGateway(search(), cite, cite), BoK([]), allowed())

    assert result.status == "invalid_output"
    assert result.detail == "unknown references: ev_00000000"


@pytest.mark.parametrize("query", ["", "x" * 301], ids=["empty", "over-300"])
def test_a_query_outside_the_producer_bounds_never_leaves_the_harness(query: str) -> None:
    bok = BoK([fragment()])
    result = run(ScriptedGateway(search(query=query), search(query=query)), bok, allowed())

    assert (result.status, bok.calls) == ("invalid_output", [])


def test_the_model_is_offered_only_the_authorized_collections() -> None:
    offered, plain = ScriptedGateway(search()), ScriptedGateway(search(), search())
    others = allowed("demo-unversioned"), allowed("demo-other@1.0.0", "bok.read")
    run(offered, BoK(GatewayError("denied", 403)), allowed(), allowed(OPERATIONS, None), *others)
    result = run(plain, None)

    assert state_of(offered.calls[0])["authorized_bok_collections"] == [RESPONSE, OPERATIONS]
    assert "search_bok" in offered.calls[0]["input"]
    # Without collections the action is never offered, so asking for it is invalid output.
    assert ("search_bok" in plain.calls[0]["input"], result.status) == (False, "invalid_output")
    with pytest.raises(ValueError, match="BoK source"):
        run(ScriptedGateway(CONCLUDE), None, allowed())
