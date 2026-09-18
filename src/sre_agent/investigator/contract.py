"""Input and output contract of the investigator harness (issue #185, ADR-007).

The harness reads a declared projection of the incident state and returns a validated
result. It never writes incident state: the incident runtime decides what to apply.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

EvidenceId = Annotated[str, Field(pattern=r"^ev_[a-z0-9_-]{1,60}$")]
HypothesisId = Annotated[str, Field(pattern=r"^hyp_[a-z0-9_-]{1,60}$")]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Step = Annotated[str, Field(min_length=1, max_length=1000)]
Level = Literal["low", "medium", "high"]
Objective = Literal["triage", "investigate", "mitigate", "postmortem"]
Status = Literal[
    "completed", "needs_human", "denied", "max_steps", "invalid_output", "upstream_unavailable"
]
_TURN = re.compile(r"^turn_[a-z0-9]{8,32}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Projection(BaseModel):
    """Reads the declared fields of an incident-state document and ignores the rest."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Capability(_Strict):
    resource_type: Literal["llm_model", "mcp_server", "mcp_tool", "skill", "bok_collection"]
    resource_id: Name
    action: Annotated[str, Field(max_length=100)] | None = None


class AlertContext(_Projection):
    service: Name
    severity: Literal["sev1", "sev2", "sev3", "sev4"]
    summary: Annotated[str, Field(min_length=1, max_length=2000)]


class HypothesisContext(_Projection):
    hypothesis_id: HypothesisId
    statement: Text
    confidence: Level
    status: Literal["open", "supported", "refuted", "superseded"]
    supporting_evidence: list[EvidenceId] = Field(default_factory=list)


class EvidenceContext(_Projection):
    evidence_id: EvidenceId
    source: Name
    tool: Annotated[str, Field(max_length=200)] | None = None
    query: Annotated[str, Field(max_length=4000)] | None = None
    time_window: Annotated[str, Field(max_length=200)] | None = None
    summary: Annotated[str, Field(min_length=1, max_length=8000)]


class IncidentContext(_Projection):
    state: Literal["triage", "investigating", "mitigating", "verifying", "postmortem"]
    alert: AlertContext
    hypotheses: list[HypothesisContext] = Field(default_factory=list)
    evidence: list[EvidenceContext] = Field(default_factory=list)


class InvestigationRequest(_Strict):
    incident_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")]
    run_id: Annotated[str, Field(pattern=r"^run_[a-z0-9]{8,32}$")]
    objective: Objective
    context: IncidentContext
    authorized_capabilities: list[Capability] = Field(default_factory=list)

    def authorizes_tool(self, tool: str) -> bool:
        return any(
            item.resource_type == "mcp_tool"
            and item.resource_id == tool
            and item.action in (None, "invoke")
            for item in self.authorized_capabilities
        )


class UseTool(_Strict):
    action: Literal["use_tool"]
    tool: Name
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ProposeHypothesis(_Strict):
    action: Literal["propose_hypothesis"]
    statement: Text
    confidence: Level
    supporting_evidence: Annotated[list[EvidenceId], Field(min_length=1)]


class ProposeMitigation(_Strict):
    action: Literal["propose_mitigation"]
    description: Text
    steps: Annotated[list[Step], Field(min_length=1)]
    risk: Level
    verification_check: Annotated[str, Field(min_length=1, max_length=2000)]
    based_on_hypothesis: HypothesisId | None = None


class RequestHuman(_Strict):
    action: Literal["request_human"]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class Conclude(_Strict):
    action: Literal["conclude"]
    summary: Text
    supporting_evidence: list[EvidenceId] = Field(default_factory=list)


Outcome = ProposeHypothesis | ProposeMitigation | RequestHuman | Conclude
Action = UseTool | Outcome


def task_id_for(turn_id: str) -> str:
    """Gateway task_id of a turn, as agent/api/correlation-mapping.v1.yaml derives it."""
    if not _TURN.fullmatch(turn_id):
        raise ValueError("turn_id must match ^turn_[a-z0-9]{8,32}$")
    return "task_" + turn_id.removeprefix("turn_")


class ToolInvocation(_Strict):
    tool: Name
    arguments: dict[str, JsonValue]
    result_summary: Annotated[str, Field(max_length=8000)] | None = None


class Turn(_Strict):
    """One model call, shaped like a run-context turn."""

    turn_id: Annotated[str, Field(pattern=_TURN.pattern)]
    task_id: str
    sequence: Annotated[int, Field(ge=0)]
    assembled_input: Annotated[str, Field(max_length=65_536)] | None = None
    model_output: Annotated[str, Field(max_length=65_536)] | None = None
    tool_invocation: ToolInvocation | None = None
    request_id: UUID | None = None
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def _task_is_derived(self) -> Turn:
        if self.task_id != task_id_for(self.turn_id):
            raise ValueError("task_id must be derived from turn_id")
        return self


class CollectedEvidence(_Strict):
    """Evidence gathered during the run, shaped like an incident-state evidence item."""

    evidence_id: EvidenceId
    source: Name
    tool: Annotated[str, Field(max_length=200)] | None = None
    datasource_uid: Annotated[str, Field(max_length=200)] | None = None
    query: Annotated[str, Field(max_length=4000)] | None = None
    time_window: Annotated[str, Field(max_length=200)] | None = None
    summary: Annotated[str, Field(min_length=1, max_length=8000)]
    collected_at: AwareDatetime
    request_id: UUID | None = None
    trusted: Literal[False] = False


class InvestigationResult(_Strict):
    incident_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")]
    run_id: Annotated[str, Field(pattern=r"^run_[a-z0-9]{8,32}$")]
    status: Status
    outcome: Annotated[Outcome, Field(discriminator="action")] | None = None
    detail: Annotated[str, Field(max_length=500)] | None = None
    evidence: list[CollectedEvidence] = Field(default_factory=list)
    turns: list[Turn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _status_matches_outcome(self) -> InvestigationResult:
        final = self.outcome is not None and not isinstance(self.outcome, RequestHuman)
        if final != (self.status == "completed"):
            raise ValueError("only a completed result carries a final outcome, and it must")
        if isinstance(self.outcome, RequestHuman) and self.status != "needs_human":
            raise ValueError("a request for a human requires status needs_human")
        if [turn.sequence for turn in self.turns] != list(range(len(self.turns))):
            raise ValueError("turn sequences must run from 0 without gaps")
        return self


class Limits(_Strict):
    """Bounds set by the issue assignee (Definition of Ready); see the change design."""

    max_steps: Annotated[int, Field(ge=1, le=20)] = 6
    transient_retries: Annotated[int, Field(ge=0, le=3)] = 1
    gateway_timeout_seconds: Annotated[float, Field(gt=0, le=180)] = 45.0
    tool_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 10.0
