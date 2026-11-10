"""The vocabulary in `sre_agent.vocabulary` and its copies in the workflow and agent schemas."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from sre_agent.vocabulary import (
    AGENT_OBJECTIVES,
    IDENTIFIER_PATTERN,
    RUN_OBJECTIVE_TRANSITIONS,
    TRIAGE_TRANSITIONS,
    AgentObjective,
    HarnessStatus,
    IncidentState,
    RunCommand,
    RunObjective,
    RunStatus,
    TransitionId,
    TriageStatus,
)

ROOT = Path(__file__).parents[1]
SCHEMAS = ROOT / "agent" / "schemas"

# Patterns in agent/ that start like the identifier and are other formats on purpose.
DISTINCT_PATTERNS = {
    "^[a-z][a-z0-9_]{2,63}$": "run-event reason_code",
    "^[a-z][a-z0-9_]{1,63}$": "action-catalog reason_code",
    "^[a-z][a-z0-9_]{0,63}$": "action-catalog parameter name",
    "^[a-z][a-z0-9.-]{0,62}$": "action-catalog service and operation name",
}


def load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def schema(name: str) -> Any:
    return load(SCHEMAS / f"{name}.schema.yaml")


def values(enum: list[Any]) -> set[str]:
    return {value for value in enum if value is not None}


@pytest.fixture(scope="module")
def workflow() -> Any:
    return load(ROOT / "agent" / "workflows" / "incident-response.yaml")


def test_workflow_transitions_are_the_vocabulary(workflow: Any) -> None:
    declared = [transition["id"] for transition in workflow["transitions"]]
    assert set(declared) - set(TransitionId) == set(), "only in the workflow"
    assert set(TransitionId) - set(declared) == set(), "only in the vocabulary"


def test_workflow_and_schema_states_are_the_vocabulary(workflow: Any) -> None:
    assert set(workflow["states"]) == set(IncidentState)
    copies = {
        "incident-state": schema("incident-state")["properties"]["state"]["enum"],
        "incident-detail": schema("incident-detail")["properties"]["state"]["enum"],
        "incident-list": schema("incident-list")["$defs"]["item"]["properties"]["state"]["enum"],
        "run-state": schema("run-state")["properties"]["current_state"]["enum"],
    }
    for name, enum in copies.items():
        assert values(enum) == set(IncidentState), name


def test_workflow_objectives_are_the_ones_the_code_dispatches(workflow: Any) -> None:
    declared = {
        state: definition["agent_objective"]
        for state, definition in workflow["states"].items()
        if definition.get("allows_agentic_step")
    }
    assert declared == AGENT_OBJECTIVES
    for state, definition in workflow["states"].items():
        assert ("agent_objective" in definition) == bool(definition.get("allows_agentic_step")), (
            state
        )
    assert set(AGENT_OBJECTIVES.values()) == set(AgentObjective)


def test_run_commands_are_the_vocabulary() -> None:
    current = schema("run-command-2.1.0")["properties"]["command"]["enum"]
    assert set(current) == set(RunCommand)
    assert set(schema("run-command")["properties"]["command"]["enum"]) <= set(RunCommand)


def test_run_statuses_are_the_vocabulary() -> None:
    copies = {
        "run-state": schema("run-state")["properties"]["status"]["enum"],
        "incident-snapshot": schema("incident-snapshot")["properties"]["run"]["properties"][
            "status"
        ]["enum"],
        "incident-list": schema("incident-list")["$defs"]["item"]["properties"]["latest_run"][
            "anyOf"
        ][1]["properties"]["status"]["enum"],
        "incident-detail": schema("incident-detail")["properties"]["runs"]["items"]["properties"][
            "status"
        ]["enum"],
    }
    for name, enum in copies.items():
        assert values(enum) == set(RunStatus), name


def test_run_objectives_open_a_declared_transition() -> None:
    assert set(schema("run-start-request")["properties"]["objective"]["enum"]) == set(RunObjective)
    assert set(RUN_OBJECTIVE_TRANSITIONS) == set(RunObjective)
    assert set(RUN_OBJECTIVE_TRANSITIONS.values()) <= set(TransitionId)


def test_a_run_ends_with_any_harness_status_but_a_pre_dispatch_rejection() -> None:
    enum = schema("run-state")["properties"]["terminated_reason"]["enum"]
    assert values(enum) == set(HarnessStatus) - {HarnessStatus.PRE_DISPATCH_REJECTED}


def test_triage_statuses_and_transitions_are_the_vocabulary() -> None:
    assert set(schema("triage-state")["properties"]["status"]["enum"]) == set(TriageStatus)
    enum = schema("triage-context")["properties"]["allowed_actions"]["items"]["enum"]
    assert enum == list(TRIAGE_TRANSITIONS)


def patterns(node: Any) -> list[str]:
    if isinstance(node, dict):
        found = [node["pattern"]] if isinstance(node.get("pattern"), str) else []
        return found + [item for value in node.values() for item in patterns(value)]
    if isinstance(node, list):
        return [item for value in node for item in patterns(value)]
    return []


def test_identifier_copies_in_agent_contracts_are_the_vocabulary_pattern() -> None:
    files = sorted((ROOT / "agent").glob("**/*.yaml"))
    found = [
        (path.relative_to(ROOT), pattern)
        for path in files
        for pattern in patterns(load(path))
        if pattern.startswith("^[a-z][a-z0-9")
    ]
    assert any(pattern == IDENTIFIER_PATTERN for _, pattern in found)
    drifted = [
        (str(path), pattern)
        for path, pattern in found
        if pattern != IDENTIFIER_PATTERN and pattern not in DISTINCT_PATTERNS
    ]
    assert drifted == []
