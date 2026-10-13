"""Resolve the contract's human commands to named transitions (HT-INC-COMMANDS, issue #330).

The operations UI sends a command by name (`run-command:2.0.0`); the runtime of
#26 executes named transitions of the pinned workflow. This module is the only
place that knows which command means which transition, and it decides nothing
else: the state rule, the approval guard, the attribution rule and the unit of
work all stay in the runtime.

Two rules are load-bearing here. A command always carries the human who issued
it, because the question an audit of the incident asks is which person approved
the mitigation, and "a human" does not answer it. And only `approve_mitigation`
carries approval: the workflow marks `apply_mitigation` as `requires_approval`,
so nothing else can move a proposal into production, and no other command may
leave an approval record behind that never happened.

`escalate` and `cancel_run` are refused by name, not silently ignored. Neither
is a transition: the workflow states that escalation "never produces a state
change by itself", and cancelling ends the run without dispositioning the
incident. Both need a path that writes an event without moving the state
machine, which is the next sheet of this issue.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sre_agent.incident.runtime import ActorReference, IncidentCommand, InvalidTransitionError

# `reject_mitigation` and `request_changes` share one transition on purpose: the
# workflow declares a single edge back to investigating carrying two outcomes,
# and the outcome is what tells a reviewer "rejected" from "sent back for
# changes". Collapsing them would erase that distinction from the audit trail.
COMMAND_TRANSITIONS: Mapping[str, tuple[str, str]] = {
    "approve_mitigation": ("apply_mitigation", "approve"),
    "reject_mitigation": ("reject_mitigation", "reject"),
    "request_changes": ("reject_mitigation", "request_changes"),
}
DISPOSITION_TRANSITIONS: Mapping[str, str] = {
    "dismiss": "triage_dismiss",
    "link": "triage_link",
    "declare": "triage_declare",
}
APPROVING_COMMANDS = frozenset({"approve_mitigation"})
DEFERRED_COMMANDS = frozenset({"escalate", "cancel_run"})


@dataclass(frozen=True, slots=True)
class HumanCommand:
    """A command as the contract states it: named, human, always attributable."""

    command_id: str
    incident_id: str
    run_id: str
    command: str
    actor_reference: ActorReference
    disposition: str | None = None
    comment: str | None = None
    expected_incident_version: int | None = None
    turn_id: str | None = None
    inputs: Mapping[str, Any] | None = None


def resolve(request: HumanCommand) -> IncidentCommand:
    """Translate one human command into the transition the runtime can execute.

    Raises ``InvalidTransitionError`` when the command names no transition. The
    runtime still decides whether that transition is legal from the run's
    current state; this function only resolves the name.
    """

    if request.command in DEFERRED_COMMANDS:
        raise InvalidTransitionError(
            f"command '{request.command}' performs no state transition in this workflow version"
        )
    if request.command == "propose_disposition":
        transition_id = DISPOSITION_TRANSITIONS.get(request.disposition or "")
        if transition_id is None:
            raise InvalidTransitionError("propose_disposition requires a declared disposition")
        outcome: str = str(request.disposition)
    else:
        mapped = COMMAND_TRANSITIONS.get(request.command)
        if mapped is None:
            raise InvalidTransitionError(f"unknown command '{request.command}'")
        if request.disposition is not None:
            raise InvalidTransitionError(f"command '{request.command}' does not take a disposition")
        transition_id, outcome = mapped
    inputs = dict(request.inputs or {})
    if request.comment is not None:
        inputs["comment"] = request.comment
    return IncidentCommand(
        command_id=request.command_id,
        incident_id=request.incident_id,
        run_id=request.run_id,
        transition_id=transition_id,
        actor="human",
        actor_reference=request.actor_reference,
        outcome=outcome,
        approval=request.command in APPROVING_COMMANDS,
        expected_incident_version=request.expected_incident_version,
        turn_id=request.turn_id,
        inputs=inputs or None,
    )
