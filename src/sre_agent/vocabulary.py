"""The domain vocabulary, declared once: incident states, workflow transitions, run commands,
objectives, run and triage statuses and the identifier format.

`agent/workflows/incident-response.yaml` and `agent/schemas/` repeat these values for readers
that cannot import Python; `tests/test_domain_vocabulary.py` keeps every copy equal. The values
are the strings that travel through the API and are persisted, so they never change here alone.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated

from pydantic import Field

IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"
"""An incident, alert, principal, grant, credential or model alias identifier."""

Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]

_IDENTIFIER = re.compile(IDENTIFIER_PATTERN)


def is_identifier(value: str) -> bool:
    return _IDENTIFIER.fullmatch(value) is not None


class IncidentState(StrEnum):
    DETECTED = "detected"
    TRIAGE = "triage"
    DISMISSED = "dismissed"
    LINKED = "linked"
    ACTIVE = "active"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    POSTMORTEM = "postmortem"
    CLOSED = "closed"


class TransitionId(StrEnum):
    OPEN_TRIAGE = "open_triage"
    TRIAGE_DISMISS = "triage_dismiss"
    TRIAGE_LINK = "triage_link"
    TRIAGE_DECLARE = "triage_declare"
    START_INVESTIGATION = "start_investigation"
    CONTINUE_INVESTIGATION = "continue_investigation"
    PROPOSE_MITIGATION = "propose_mitigation"
    APPLY_MITIGATION = "apply_mitigation"
    REJECT_MITIGATION = "reject_mitigation"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_PASSED = "verification_passed"
    START_POSTMORTEM = "start_postmortem"
    CLOSE_INCIDENT = "close_incident"


class RunCommand(StrEnum):
    """What a person tells a run (`run-command`). Four share their name with a transition."""

    APPROVE_MITIGATION = "approve_mitigation"
    REJECT_MITIGATION = "reject_mitigation"
    REQUEST_CHANGES = "request_changes"
    PROPOSE_DISPOSITION = "propose_disposition"
    ESCALATE = "escalate"
    CANCEL_RUN = "cancel_run"
    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    CLOSE_INCIDENT = "close_incident"


class AgentObjective(StrEnum):
    """What the investigator is asked to do in one dispatch. Internal to the harness."""

    TRIAGE = "triage"
    INVESTIGATE = "investigate"
    MITIGATE = "mitigate"
    VERIFY = "verify"
    POSTMORTEM = "postmortem"


class RunObjective(StrEnum):
    """What a client asks a run for (`run-start-request`). Not an `AgentObjective`."""

    TRIAGE = "triage"
    INVESTIGATE = "investigate"
    MITIGATE = "mitigate"
    POSTMORTEM = "postmortem"


class RunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class HarnessStatus(StrEnum):
    """How one investigator dispatch ended. All but `pre_dispatch_rejected` can end a run."""

    COMPLETED = "completed"
    NEEDS_HUMAN = "needs_human"
    DENIED = "denied"
    MAX_STEPS = "max_steps"
    INVALID_OUTPUT = "invalid_output"
    PRE_DISPATCH_REJECTED = "pre_dispatch_rejected"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"


class TriageStatus(StrEnum):
    """The stored triage of an alert (`triage-state`), not the alert's own `triage_status`."""

    OPEN = "open"
    DISMISSED = "dismissed"
    LINKED = "linked"
    DECLARED = "declared"


# The objective the investigator works on in each state that allows an agentic step.
AGENT_OBJECTIVES: dict[str, AgentObjective] = {
    IncidentState.TRIAGE: AgentObjective.TRIAGE,
    IncidentState.INVESTIGATING: AgentObjective.INVESTIGATE,
    IncidentState.MITIGATING: AgentObjective.MITIGATE,
    IncidentState.VERIFYING: AgentObjective.VERIFY,
    IncidentState.POSTMORTEM: AgentObjective.POSTMORTEM,
}

# The transition that opens a run for each public objective.
RUN_OBJECTIVE_TRANSITIONS: dict[str, TransitionId] = {
    RunObjective.TRIAGE: TransitionId.OPEN_TRIAGE,
    RunObjective.INVESTIGATE: TransitionId.START_INVESTIGATION,
    RunObjective.MITIGATE: TransitionId.PROPOSE_MITIGATION,
    RunObjective.POSTMORTEM: TransitionId.START_POSTMORTEM,
}

TRIAGE_TRANSITIONS = (
    TransitionId.OPEN_TRIAGE,
    TransitionId.TRIAGE_DISMISS,
    TransitionId.TRIAGE_LINK,
    TransitionId.TRIAGE_DECLARE,
)

# States of a declared incident: the session started and incident_id is canonical.
DECLARED_STATES = frozenset(
    {
        IncidentState.ACTIVE,
        IncidentState.INVESTIGATING,
        IncidentState.MITIGATING,
        IncidentState.VERIFYING,
        IncidentState.RESOLVED,
        IncidentState.POSTMORTEM,
        IncidentState.CLOSED,
    }
)
