"""Loader and immutable view of the supported incident workflow contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_WORKFLOWS = {"incident-response": "1.0.0"}


class UnsupportedWorkflowError(ValueError):
    """The requested workflow identity or version is not executable by this runtime."""


class InvalidWorkflowError(ValueError):
    """The workflow does not contain the minimum runtime contract."""


@dataclass(frozen=True, slots=True)
class Transition:
    transition_id: str
    source: str
    target: str
    actors: frozenset[str]
    requires_approval: bool
    decision_point: str | None
    outcomes: tuple[str, ...]
    records_decision: bool
    records_approval: bool


@dataclass(frozen=True, slots=True)
class IncidentWorkflow:
    workflow_id: str
    version: str
    initial_state: str
    terminal_states: frozenset[str]
    states: frozenset[str]
    transitions: Mapping[str, Transition]

    def transition(self, transition_id: str) -> Transition:
        try:
            return self.transitions[transition_id]
        except KeyError as error:
            raise InvalidWorkflowError(f"unknown transition '{transition_id}'") from error

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        *,
        supported: Mapping[str, str] = SUPPORTED_WORKFLOWS,
    ) -> IncidentWorkflow:
        workflow_id = str(document.get("workflow_id", ""))
        version = str(document.get("workflow_version", ""))
        if supported.get(workflow_id) != version:
            raise UnsupportedWorkflowError(
                f"unsupported workflow '{workflow_id}' version '{version}'"
            )

        raw_states = document.get("states")
        raw_transitions = document.get("transitions")
        if not isinstance(raw_states, Mapping) or not isinstance(raw_transitions, list):
            raise InvalidWorkflowError("workflow must declare states and transitions")
        states = frozenset(str(name) for name in raw_states)
        initial_state = str(document.get("initial_state", ""))
        terminal_states = frozenset(str(name) for name in document.get("terminal_states", ()))
        if initial_state not in states or not terminal_states <= states:
            raise InvalidWorkflowError("workflow initial or terminal state is undeclared")

        transitions: dict[str, Transition] = {}
        for raw in raw_transitions:
            if not isinstance(raw, Mapping):
                raise InvalidWorkflowError("workflow transition must be an object")
            transition_id = str(raw.get("id", ""))
            source, target = str(raw.get("from", "")), str(raw.get("to", ""))
            actors = frozenset(str(actor) for actor in raw.get("actor", ()))
            if not transition_id or transition_id in transitions:
                raise InvalidWorkflowError(f"duplicate or empty transition '{transition_id}'")
            if source not in states or target not in states or not actors:
                raise InvalidWorkflowError(f"transition '{transition_id}' is incomplete")
            raw_outcomes = raw.get("on_outcome", ())
            outcomes = (
                tuple(str(outcome) for outcome in raw_outcomes)
                if isinstance(raw_outcomes, list)
                else ((str(raw_outcomes),) if raw_outcomes else ())
            )
            transitions[transition_id] = Transition(
                transition_id=transition_id,
                source=source,
                target=target,
                actors=actors,
                requires_approval=bool(raw.get("requires_approval", False)),
                decision_point=(str(raw["decision_point"]) if raw.get("decision_point") else None),
                outcomes=outcomes,
                records_decision=bool(raw.get("records_decision", False)),
                records_approval=bool(raw.get("records_approval", False)),
            )
        return cls(
            workflow_id=workflow_id,
            version=version,
            initial_state=initial_state,
            terminal_states=terminal_states,
            states=states,
            transitions=transitions,
        )


def load_incident_workflow(path: str | Path) -> IncidentWorkflow:
    """Load the executable contract from its explicitly selected YAML artifact."""
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise InvalidWorkflowError("workflow document must be an object")
    return IncidentWorkflow.from_document(document)
