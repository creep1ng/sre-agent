"""Minimal command runtime for the versioned incident-response workflow."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sre_agent.incident.persistence import (
    DecisionDraft,
    EventDraft,
    IncidentStaleWriteError,
    IncidentUnitOfWork,
    SnapshotDraft,
    TransitionResult,
)
from sre_agent.incident.workflow import IncidentWorkflow, InvalidWorkflowError, Transition


class IncidentRuntimeError(RuntimeError):
    """Base error for rejected incident commands."""


class IncidentNotFoundError(IncidentRuntimeError):
    pass


class RunNotFoundError(IncidentRuntimeError):
    pass


class InvalidTransitionError(IncidentRuntimeError):
    pass


class PreconditionFailedError(IncidentRuntimeError):
    pass


class ApprovalRequiredError(IncidentRuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActorReference:
    principal_id: str
    display_name: str | None = None
    reference_version: str = "1.0.0"


@dataclass(frozen=True, slots=True)
class IncidentCommand:
    command_id: str
    incident_id: str
    run_id: str
    transition_id: str
    actor: str
    actor_reference: ActorReference | None = None
    outcome: str | None = None
    approval: bool = False
    turn_id: str | None = None
    inputs: Mapping[str, Any] | None = None

    def payload_sha256(self) -> str:
        payload = asdict(self)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class IncidentView:
    incident_id: str
    run_id: str
    incident_state: Mapping[str, Any]
    run_state: Mapping[str, Any]
    incident_version: int
    run_version: int


UnitOfWorkFactory = Callable[[], IncidentUnitOfWork]
Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


def _default_id(prefix: str) -> str:
    from secrets import token_hex

    return f"{prefix}_{token_hex(8)}"


class IncidentRuntime:
    """Execute only named transitions from one pinned workflow version."""

    _DECLARED_STATES = frozenset(
        {"active", "investigating", "mitigating", "verifying", "resolved", "postmortem", "closed"}
    )
    _PATCHABLE_BY_TRANSITION = {
        "continue_investigation": frozenset({"impact", "hypotheses", "evidence"}),
        "propose_mitigation": frozenset({"mitigation_strategy"}),
        "verification_failed": frozenset({"evidence"}),
        "verification_passed": frozenset({"evidence"}),
        "start_postmortem": frozenset({"postmortem"}),
    }

    def __init__(
        self,
        workflow: IncidentWorkflow,
        unit_of_work: UnitOfWorkFactory,
        *,
        clock: Clock = lambda: datetime.now(UTC),
        id_factory: IdFactory = _default_id,
        snapshot_interval: int = 5,
    ) -> None:
        if snapshot_interval < 1:
            raise ValueError("snapshot_interval must be positive")
        self._workflow = workflow
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_factory = id_factory
        self._snapshot_interval = snapshot_interval

    async def current(self, incident_id: str, run_id: str) -> IncidentView:
        async with self._unit_of_work() as work:
            incident = await work.incidents.get(incident_id)
            if incident is None:
                raise IncidentNotFoundError(incident_id)
            run = await work.runs.get(run_id)
            if run is None or run.incident_id != incident_id:
                raise RunNotFoundError(run_id)
            self._assert_supported_state(incident.state, run.state)
            return IncidentView(
                incident_id=incident_id,
                run_id=run_id,
                incident_state=incident.state,
                run_state=run.state,
                incident_version=incident.version,
                run_version=run.version,
            )

    async def execute(self, command: IncidentCommand) -> TransitionResult:
        payload_hash = command.payload_sha256()
        async with self._unit_of_work() as work:
            await work.lock_command(command.incident_id, command.command_id)
            replayed = await work.get_transition(
                command.incident_id, command.command_id, payload_hash
            )
            if replayed is not None:
                return replayed

            incident = await work.incidents.get(command.incident_id)
            if incident is None:
                raise IncidentNotFoundError(command.incident_id)
            run = await work.runs.get(command.run_id)
            if run is None or run.incident_id != command.incident_id:
                raise RunNotFoundError(command.run_id)
            self._assert_supported_state(incident.state, run.state)

            try:
                transition = self._workflow.transition(command.transition_id)
            except InvalidWorkflowError as error:
                raise InvalidTransitionError(str(error)) from error
            self._validate(command, transition, incident.state)
            now = self._clock()
            incident_state, run_state = self._reduce(
                command, transition, incident.state, run.state, now
            )
            decision = DecisionDraft(
                decision_id=self._id_factory("dec"),
                document=self._decision_document(command, transition, now),
                decided_at=now,
                run_id=command.run_id,
                turn_id=command.turn_id,
            )
            event = EventDraft(
                event_id=self._id_factory("evt"),
                kind="state_change",
                payload={
                    "workflow_id": self._workflow.workflow_id,
                    "workflow_version": self._workflow.version,
                    "transition_id": transition.transition_id,
                    "from": transition.source,
                    "to": transition.target,
                    "incident_state": incident_state,
                    "run_state": run_state,
                    "decision_id": decision.decision_id,
                },
                occurred_at=now,
                turn_id=command.turn_id,
            )
            next_version = run.version + 1
            latest_snapshot = await work.snapshots.latest(command.run_id)
            snapshot = None
            if latest_snapshot is None or next_version % self._snapshot_interval == 0:
                snapshot = SnapshotDraft(
                    snapshot_id=self._id_factory("snap"),
                    incident_state=incident_state,
                    run_state=run_state,
                    created_at=now,
                )
            return await work.persist_transition(
                command_id=command.command_id,
                payload_sha256=payload_hash,
                incident_id=command.incident_id,
                run_id=command.run_id,
                expected_incident_version=incident.version,
                expected_run_version=run.version,
                incident_state=incident_state,
                run_state=run_state,
                decision=decision,
                events=(event,),
                snapshot=snapshot,
            )

    async def reconstruct(self, incident_id: str, run_id: str) -> IncidentView:
        async with self._unit_of_work() as work:
            replay = await work.load_replay(run_id)
            if replay.snapshot is None:
                raise IncidentRuntimeError("replay requires an initial snapshot")
            if replay.snapshot.incident_id != incident_id or replay.snapshot.run_id != run_id:
                raise IncidentRuntimeError("snapshot aggregate identity does not match replay")
            incident_state = dict(replay.snapshot.incident_state)
            run_state = dict(replay.snapshot.run_state)
            replayed_transitions = 0
            for event in replay.events:
                if event.kind != "state_change":
                    continue
                event_incident = event.payload.get("incident_state")
                event_run = event.payload.get("run_state")
                if not isinstance(event_incident, Mapping) or not isinstance(event_run, Mapping):
                    raise IncidentRuntimeError(f"event '{event.event_id}' cannot be replayed")
                incident_state = dict(event_incident)
                run_state = dict(event_run)
                replayed_transitions += 1
            self._assert_supported_state(incident_state, run_state)
            if replay.incident.incident_id != incident_id or replay.run.incident_id != incident_id:
                raise IncidentNotFoundError(incident_id)
            replayed_version = replay.snapshot.version + replayed_transitions
            if (
                replay.incident.version != replayed_version
                or replay.run.version != replayed_version
                or replay.incident.state != incident_state
                or replay.run.state != run_state
            ):
                raise IncidentStaleWriteError(
                    f"replay watermark changed while reconstructing {incident_id}/{run_id}"
                )
            return IncidentView(
                incident_id=incident_id,
                run_id=run_id,
                incident_state=incident_state,
                run_state=run_state,
                incident_version=replay.incident.version,
                run_version=replay.run.version,
            )

    def _assert_supported_state(
        self, incident_state: Mapping[str, Any], run_state: Mapping[str, Any]
    ) -> None:
        identity = (incident_state.get("workflow_id"), incident_state.get("workflow_version"))
        if identity != (self._workflow.workflow_id, self._workflow.version):
            raise InvalidTransitionError("stored incident uses an unsupported workflow version")
        if run_state.get("workflow_version") != self._workflow.version:
            raise InvalidTransitionError("stored run uses an unsupported workflow version")
        incident_name, run_name = incident_state.get("state"), run_state.get("current_state")
        if incident_name not in self._workflow.states or incident_name != run_name:
            raise InvalidTransitionError("incident and run states are not aligned")

    def _validate(
        self,
        command: IncidentCommand,
        transition: Transition,
        state: Mapping[str, Any],
    ) -> None:
        if state.get("state") != transition.source:
            raise InvalidTransitionError(
                f"transition '{transition.transition_id}' requires state '{transition.source}'"
            )
        if command.actor not in transition.actors:
            raise InvalidTransitionError(
                f"actor '{command.actor}' cannot execute '{transition.transition_id}'"
            )
        if command.actor == "human" and command.actor_reference is None:
            raise PreconditionFailedError("human commands require an actor reference")
        if command.actor_reference is not None and (
            command.actor_reference.reference_version != "1.0.0"
            or re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", command.actor_reference.principal_id) is None
        ):
            raise PreconditionFailedError("actor reference is invalid")
        if transition.requires_approval and (command.actor != "human" or not command.approval):
            raise ApprovalRequiredError(transition.transition_id)
        if transition.outcomes:
            if command.outcome is None and len(transition.outcomes) == 1:
                pass
            elif command.outcome not in transition.outcomes:
                raise PreconditionFailedError(
                    f"transition '{transition.transition_id}' requires outcome "
                    f"{list(transition.outcomes)}"
                )
        self._validate_named_preconditions(command, transition, state)

    def _validate_named_preconditions(
        self,
        command: IncidentCommand,
        transition: Transition,
        state: Mapping[str, Any],
    ) -> None:
        inputs = command.inputs or {}
        transition_id = transition.transition_id
        if transition_id == "triage_link" and not inputs.get("target_incident_id"):
            raise PreconditionFailedError("triage_link requires target_incident_id")
        if transition_id == "triage_declare" and not inputs.get("severity"):
            raise PreconditionFailedError("triage_declare requires severity")
        if transition_id == "continue_investigation" and inputs.get("remaining_step_budget", 0) < 1:
            raise PreconditionFailedError("continue_investigation requires remaining step budget")
        if transition_id == "propose_mitigation":
            hypotheses = state.get("hypotheses") or []
            evidence = state.get("evidence") or []
            if (
                not hypotheses
                or not evidence
                or not any(
                    item.get("supporting_evidence")
                    for item in hypotheses
                    if isinstance(item, Mapping)
                )
            ):
                raise PreconditionFailedError(
                    "propose_mitigation requires a hypothesis with supporting evidence"
                )
        if transition_id in {"apply_mitigation", "reject_mitigation"} and not state.get(
            "mitigation_strategy"
        ):
            raise PreconditionFailedError(f"{transition_id} requires mitigation_strategy")
        if transition_id in {"verification_failed", "verification_passed"} and not state.get(
            "evidence"
        ):
            raise PreconditionFailedError(f"{transition_id} requires verification evidence")
        if transition_id in {"verification_failed", "verification_passed"}:
            strategy = state.get("mitigation_strategy")
            if not isinstance(strategy, Mapping) or not strategy.get("verification_check"):
                raise PreconditionFailedError(
                    f"{transition_id} requires a mitigation verification check"
                )
        if transition_id == "close_incident" and not state.get("postmortem"):
            raise PreconditionFailedError("close_incident requires a postmortem")

    def _reduce(
        self,
        command: IncidentCommand,
        transition: Transition,
        old_incident: Mapping[str, Any],
        old_run: Mapping[str, Any],
        now: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        inputs = dict(command.inputs or {})
        incident = dict(old_incident)
        patch = inputs.get("incident_patch", {})
        allowed_patch = self._PATCHABLE_BY_TRANSITION.get(transition.transition_id, frozenset())
        if not isinstance(patch, Mapping) or not set(patch) <= allowed_patch:
            raise PreconditionFailedError("incident_patch contains unsupported fields")
        incident.update(patch)
        incident["state"] = transition.target
        incident["updated_at"] = now.isoformat()
        if transition.target in self._DECLARED_STATES:
            incident["incident_id"] = command.incident_id
            incident["linked_incident_id"] = None
        elif transition.target == "linked":
            incident["incident_id"] = None
        else:
            incident["incident_id"] = None
            incident["linked_incident_id"] = None
        if transition.transition_id == "triage_link":
            incident["linked_incident_id"] = inputs["target_incident_id"]
        if transition.transition_id == "triage_declare":
            incident["severity"] = inputs["severity"]
        if transition.transition_id in {
            "open_triage",
            "triage_dismiss",
            "triage_link",
            "triage_declare",
        }:
            alert = dict(incident.get("alert") or {})
            alert["status"] = {
                "triage_dismiss": "dismissed",
                "triage_link": "linked",
            }.get(transition.transition_id, "triaged")
            incident["alert"] = alert
        if transition.transition_id in {"apply_mitigation", "reject_mitigation"}:
            strategy = dict(incident["mitigation_strategy"])
            strategy["approval_status"] = {
                "approve": "approved",
                "reject": "rejected",
                "request_changes": "changes_requested",
            }[command.outcome or transition.outcomes[0]]
            incident["mitigation_strategy"] = strategy
        self._validate_result(transition, incident)

        run = dict(old_run)
        run["current_state"] = transition.target
        run["updated_at"] = now.isoformat()
        if transition.target in self._workflow.terminal_states:
            run.update(status="completed", pending_command=None, terminated_reason="completed")
        elif transition.target == "mitigating":
            run.update(status="awaiting_human", pending_command="approve_mitigation")
        else:
            run.update(status="running", pending_command=None, terminated_reason=None)
        return incident, run

    def _validate_result(self, transition: Transition, incident_state: Mapping[str, Any]) -> None:
        if transition.target in self._DECLARED_STATES:
            if not incident_state.get("incident_id") or not incident_state.get("severity"):
                raise PreconditionFailedError("declared incidents require identity and severity")
        elif incident_state.get("incident_id") is not None:
            raise PreconditionFailedError(
                "pre-declaration states cannot carry an incident identity"
            )
        if transition.target == "linked" and not incident_state.get("linked_incident_id"):
            raise PreconditionFailedError("linked incidents require a target incident identity")
        if transition.target == "closed" and not incident_state.get("postmortem"):
            raise PreconditionFailedError("closed incidents require a postmortem")

    def _decision_document(
        self, command: IncidentCommand, transition: Transition, now: datetime
    ) -> dict[str, Any]:
        outcome = command.outcome or (transition.outcomes[0] if transition.outcomes else None)
        actor_reference = asdict(command.actor_reference) if command.actor_reference else None
        return {
            "workflow_id": self._workflow.workflow_id,
            "workflow_version": self._workflow.version,
            "transition_id": transition.transition_id,
            "decision_point": transition.decision_point,
            "outcome": outcome,
            "actor": command.actor,
            "actor_reference": actor_reference,
            "approval": (
                {
                    "approved": True,
                    "actor_reference": actor_reference,
                    "recorded_at": now.isoformat(),
                }
                if command.approval
                else None
            ),
            "reason": f"accepted named transition {transition.source} -> {transition.target}",
            "decided_at": now.isoformat(),
        }
