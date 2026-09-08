from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from sre_agent.incident.persistence import (
    IncidentIdempotencyConflictError,
    IncidentRecord,
    IncidentStaleWriteError,
    ReplayRecord,
    RunEvent,
    RunRecord,
    SnapshotRecord,
    TransitionResult,
)
from sre_agent.incident.runtime import (
    ActorReference,
    ApprovalRequiredError,
    IncidentCommand,
    IncidentRuntime,
    InvalidTransitionError,
    PreconditionFailedError,
)
from sre_agent.incident.workflow import (
    IncidentWorkflow,
    UnsupportedWorkflowError,
    load_incident_workflow,
)

WORKFLOW_PATH = Path(__file__).parents[1] / "agent/workflows/incident-response.yaml"
STATE_SCHEMA_PATH = Path(__file__).parents[1] / "agent/schemas/incident-state.schema.yaml"
INITIAL_STATE_PATH = (
    Path(__file__).parents[1] / "agent/fixtures/incidents/otel-payment-failure/initial-state.yaml"
)
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


class MemoryStore:
    def __init__(
        self,
        state: str = "active",
        *,
        state_document: dict[str, object] | None = None,
        **incident_fields: object,
    ) -> None:
        incident_state = state_document or {
            "workflow_id": "incident-response",
            "workflow_version": "1.0.0",
            "state": state,
            "severity": "sev2",
            "hypotheses": [],
            "evidence": [],
            "mitigation_strategy": None,
            "postmortem": None,
            **incident_fields,
        }
        incident_state.update(incident_fields)
        run_state = {
            "workflow_version": "1.0.0",
            "current_state": state,
            "status": "running",
            "pending_command": None,
        }
        self.incident = IncidentRecord("inc_test", incident_state, 0, NOW, NOW)
        self.run = RunRecord("run_test", "inc_test", run_state, 0, NOW, NOW)
        self.events: list[RunEvent] = []
        self.snapshot: SnapshotRecord | None = None
        self.commands: dict[tuple[str, str], tuple[str, TransitionResult]] = {}
        self.decisions = []
        self.command_locks: dict[tuple[str, str], asyncio.Lock] = {}


class MemoryRepository:
    def __init__(self, store: MemoryStore, kind: str) -> None:
        self.store, self.kind = store, kind

    async def get(self, identifier: str):
        record = self.store.incident if self.kind == "incident" else self.store.run
        identifiers = {record.incident_id, getattr(record, "run_id", None)}
        return record if identifier in identifiers else None

    async def latest(self, run_id: str):
        return self.store.snapshot if run_id == self.store.run.run_id else None

    async def list_after(self, run_id: str, *, sequence: int = -1, limit: int = 1000):
        return tuple(event for event in self.store.events if event.sequence > sequence)[:limit]


class MemoryUnitOfWork:
    def __init__(self, store: MemoryStore, *, concurrent: bool = False) -> None:
        self.store = store
        self.incidents = MemoryRepository(store, "incident")
        self.runs = MemoryRepository(store, "run")
        self.events = MemoryRepository(store, "events")
        self.snapshots = MemoryRepository(store, "snapshots")
        self.text_context = MemoryRepository(store, "context")
        self.concurrent = concurrent
        self.acquired_lock: asyncio.Lock | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if self.acquired_lock is not None:
            self.acquired_lock.release()
        return None

    async def lock_command(self, incident_id, command_id):
        lock = self.store.command_locks.setdefault((incident_id, command_id), asyncio.Lock())
        await lock.acquire()
        self.acquired_lock = lock

    async def get_transition(self, incident_id, command_id, payload_sha256):
        retained = self.store.commands.get((incident_id, command_id))
        if retained is None:
            return None
        retained_hash, result = retained
        if retained_hash != payload_sha256:
            raise IncidentIdempotencyConflictError(command_id)
        return replace(result, replayed=True)

    async def persist_transition(self, **values):
        if self.concurrent:
            await asyncio.sleep(0)
        if values["expected_incident_version"] != self.store.incident.version:
            raise IncidentStaleWriteError(values["incident_id"])
        if values["expected_run_version"] != self.store.run.version:
            raise IncidentStaleWriteError(values["run_id"])
        sequence = len(self.store.events)
        events = tuple(
            RunEvent(
                event.event_id,
                values["incident_id"],
                values["run_id"],
                sequence + offset,
                event.kind,
                event.payload,
                event.occurred_at,
                event.turn_id,
            )
            for offset, event in enumerate(values["events"])
        )
        self.store.events.extend(events)
        self.store.incident = replace(
            self.store.incident,
            state=values["incident_state"],
            version=self.store.incident.version + 1,
            updated_at=NOW,
        )
        self.store.run = replace(
            self.store.run,
            state=values["run_state"],
            version=self.store.run.version + 1,
            updated_at=NOW,
        )
        snapshot = None
        draft = values["snapshot"]
        if draft is not None:
            snapshot = SnapshotRecord(
                draft.snapshot_id,
                values["incident_id"],
                values["run_id"],
                self.store.run.version,
                events[-1].sequence,
                draft.incident_state,
                draft.run_state,
                draft.created_at,
            )
            self.store.snapshot = snapshot
        self.store.decisions.append(values["decision"])
        result = TransitionResult(self.store.incident, self.store.run, events, snapshot)
        self.store.commands[(values["incident_id"], values["command_id"])] = (
            values["payload_sha256"],
            result,
        )
        return result

    async def load_replay(self, run_id: str):
        snapshot = self.store.snapshot
        after = snapshot.event_sequence if snapshot else -1
        events = tuple(event for event in self.store.events if event.sequence > after)
        return ReplayRecord(self.store.incident, self.store.run, snapshot, events)


@pytest.fixture
def workflow() -> IncidentWorkflow:
    return load_incident_workflow(WORKFLOW_PATH)


def runtime(workflow: IncidentWorkflow, store: MemoryStore, *, concurrent: bool = False):
    sequence = iter(range(100))
    return IncidentRuntime(
        workflow,
        lambda: MemoryUnitOfWork(store, concurrent=concurrent),
        clock=lambda: NOW,
        id_factory=lambda prefix: f"{prefix}_{next(sequence):08d}",
        snapshot_interval=10,
    )


def command(transition: str, command_id: str = "cmd_1", **values: object) -> IncidentCommand:
    return IncidentCommand(
        command_id=command_id,
        incident_id="inc_test",
        run_id="run_test",
        transition_id=transition,
        actor=str(values.pop("actor", "human")),
        actor_reference=values.pop("actor_reference", ActorReference("operator_one")),
        **values,
    )


def test_loader_rejects_an_unowned_workflow_version(workflow: IncidentWorkflow) -> None:
    document = {
        "workflow_id": workflow.workflow_id,
        "workflow_version": "2.0.0",
        "states": {"detected": {}},
        "initial_state": "detected",
        "terminal_states": [],
        "transitions": [],
    }
    with pytest.raises(UnsupportedWorkflowError):
        IncidentWorkflow.from_document(document)


@pytest.mark.asyncio
async def test_valid_command_atomically_records_explainable_decision_and_event(workflow) -> None:
    store = MemoryStore()
    result = await runtime(workflow, store).execute(
        command("start_investigation", actor="agent", actor_reference=None, turn_id="turn_12345678")
    )

    assert result.incident.state["state"] == "investigating"
    assert result.run.state["current_state"] == "investigating"
    assert [(event.sequence, event.kind) for event in result.events] == [(0, "state_change")]
    assert result.events[0].payload["workflow_version"] == "1.0.0"
    assert store.decisions[0].document["reason"] == (
        "accepted named transition active -> investigating"
    )
    assert store.snapshot is not None


@pytest.mark.asyncio
async def test_invalid_or_unapproved_command_has_no_effect(workflow) -> None:
    store = MemoryStore("mitigating", mitigation_strategy={"verification_check": "errors < 1%"})
    engine = runtime(workflow, store)

    with pytest.raises(ApprovalRequiredError):
        await engine.execute(command("apply_mitigation", outcome="approve"))
    assert store.incident.version == 0
    assert store.events == []
    assert store.decisions == []

    with pytest.raises(InvalidTransitionError):
        await engine.execute(command("open_triage", command_id="cmd_2"))
    assert store.incident.state["state"] == "mitigating"


@pytest.mark.asyncio
async def test_human_approval_is_attributed_and_repeating_command_is_idempotent(workflow) -> None:
    store = MemoryStore("mitigating", mitigation_strategy={"verification_check": "errors < 1%"})
    engine = runtime(workflow, store)
    approved = command("apply_mitigation", outcome="approve", approval=True)

    first = await engine.execute(approved)
    replayed = await engine.execute(approved)

    assert first.replayed is False and replayed.replayed is True
    assert store.incident.version == 1
    assert len(store.events) == len(store.decisions) == 1
    approval = store.decisions[0].document["approval"]
    assert approval["actor_reference"]["principal_id"] == "operator_one"


@pytest.mark.asyncio
async def test_replay_from_snapshot_plus_later_events_survives_runtime_restart(workflow) -> None:
    store = MemoryStore()
    first_runtime = runtime(workflow, store)
    await first_runtime.execute(command("start_investigation", actor="agent", actor_reference=None))
    await first_runtime.execute(
        command(
            "continue_investigation",
            "cmd_2",
            actor="agent",
            actor_reference=None,
            outcome="continue_investigation",
            inputs={"remaining_step_budget": 2},
        )
    )

    restarted_runtime = runtime(workflow, store)
    reconstructed = await restarted_runtime.reconstruct("inc_test", "run_test")

    assert store.snapshot is not None and store.snapshot.event_sequence == 0
    assert reconstructed.incident_state == store.incident.state
    assert reconstructed.run_state == store.run.state


@pytest.mark.asyncio
async def test_replay_rejects_content_from_an_obsolete_watermark(workflow) -> None:
    store = MemoryStore()
    engine = runtime(workflow, store)
    await engine.execute(command("start_investigation", actor="system", actor_reference=None))
    assert store.snapshot is not None
    store.run = replace(store.run, version=store.run.version + 1)
    store.incident = replace(store.incident, version=store.incident.version + 1)

    with pytest.raises(IncidentStaleWriteError, match="replay watermark changed"):
        await engine.reconstruct("inc_test", "run_test")


@pytest.mark.asyncio
async def test_failed_verification_returns_to_investigation(workflow) -> None:
    store = MemoryStore(
        "verifying",
        evidence=[{"evidence_id": "ev_error_rate"}],
        mitigation_strategy={"verification_check": "errors < 1%"},
    )
    result = await runtime(workflow, store).execute(
        command("verification_failed", outcome="not_stable")
    )
    assert result.incident.state["state"] == "investigating"


@pytest.mark.asyncio
async def test_close_incident_requires_postmortem_even_with_human_approval(workflow) -> None:
    store = MemoryStore("postmortem")
    engine = runtime(workflow, store)
    with pytest.raises(PreconditionFailedError):
        await engine.execute(command("close_incident", approval=True))

    store.incident = replace(
        store.incident,
        state=store.incident.state | {"postmortem": {"id": "pm_1"}},
    )
    result = await engine.execute(command("close_incident", approval=True, command_id="cmd_2"))
    assert result.incident.state["state"] == "closed"
    assert result.run.state["status"] == "completed"


@pytest.mark.asyncio
async def test_close_candidate_cannot_erase_postmortem_after_guard_check(workflow) -> None:
    state = yaml.safe_load(INITIAL_STATE_PATH.read_text())
    state.update(
        state="postmortem",
        incident_id="inc_test",
        severity="sev2",
        postmortem={
            "postmortem_id": "pm_runtime_review",
            "summary": "Payment failures were mitigated.",
            "status": "declared",
            "created_by": "human",
            "created_at": NOW.isoformat(),
        },
    )
    store = MemoryStore("postmortem", state_document=state)

    with pytest.raises(PreconditionFailedError):
        await runtime(workflow, store).execute(
            command(
                "close_incident",
                approval=True,
                inputs={"incident_patch": {"postmortem": None}},
            )
        )

    assert store.incident.state["state"] == "postmortem"
    assert store.incident.state["postmortem"] is not None
    assert store.events == []


@pytest.mark.asyncio
async def test_declaration_from_contract_fixture_emits_schema_valid_identity(workflow) -> None:
    state = yaml.safe_load(INITIAL_STATE_PATH.read_text())
    state["state"] = "triage"
    store = MemoryStore("triage", state_document=state)

    result = await runtime(workflow, store).execute(
        command("triage_declare", outcome="declare", inputs={"severity": "sev2"})
    )

    schema = yaml.safe_load(STATE_SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert result.incident.state["incident_id"] == "inc_test"
    assert result.incident.state["state"] == "active"
    assert result.incident.state["alert"]["status"] == "triaged"
    assert list(validator.iter_errors(result.incident.state)) == []


@pytest.mark.asyncio
async def test_human_approval_updates_schema_valid_mitigation_status(workflow) -> None:
    state = yaml.safe_load(INITIAL_STATE_PATH.read_text())
    state.update(
        state="mitigating",
        incident_id="inc_test",
        severity="sev2",
        mitigation_strategy={
            "mitigation_id": "mit_runtime_review",
            "description": "Disable the payment failure flag.",
            "steps": ["Ask the operator to disable paymentFailure."],
            "risk": "low",
            "verification_check": "Payment error rate remains below one percent.",
            "approval_status": "pending",
            "execution_mode": "human",
            "created_by": "agent",
            "created_at": NOW.isoformat(),
        },
    )
    store = MemoryStore("mitigating", state_document=state)

    result = await runtime(workflow, store).execute(
        command("apply_mitigation", outcome="approve", approval=True)
    )

    schema = yaml.safe_load(STATE_SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert result.incident.state["mitigation_strategy"]["approval_status"] == "approved"
    assert list(validator.iter_errors(result.incident.state)) == []


@pytest.mark.asyncio
async def test_concurrent_stale_command_cannot_overwrite_progress(workflow) -> None:
    store = MemoryStore()
    engine = runtime(workflow, store, concurrent=True)
    results = await asyncio.gather(
        engine.execute(
            command("start_investigation", "cmd_a", actor="system", actor_reference=None)
        ),
        engine.execute(
            command("start_investigation", "cmd_b", actor="system", actor_reference=None)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, IncidentStaleWriteError) for result in results) == 1
    assert store.incident.version == 1
    assert len(store.events) == 1


@pytest.mark.asyncio
async def test_concurrent_exact_duplicate_waits_then_replays_committed_result(workflow) -> None:
    store = MemoryStore()
    engine = runtime(workflow, store, concurrent=True)
    duplicate = command("start_investigation", "cmd_same", actor="system", actor_reference=None)

    first, second = await asyncio.gather(engine.execute(duplicate), engine.execute(duplicate))

    assert {first.replayed, second.replayed} == {False, True}
    assert first.incident == second.incident
    assert first.events == second.events
    assert store.incident.version == 1
    assert len(store.events) == len(store.decisions) == 1
