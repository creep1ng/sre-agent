"""Persistence ports for the authoritative incident runtime store.

The runtime owns transition rules.  These types deliberately carry opaque JSON
documents so the PostgreSQL adapter can persist newer workflow payloads without
reimplementing or weakening those rules.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

JsonDocument = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    incident_id: str
    state: JsonDocument
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    incident_id: str
    state: JsonDocument
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EventDraft:
    event_id: str
    kind: str
    payload: JsonDocument
    occurred_at: datetime
    turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunEvent:
    event_id: str
    incident_id: str
    run_id: str
    sequence: int
    kind: str
    payload: JsonDocument
    occurred_at: datetime
    turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionDraft:
    decision_id: str
    document: JsonDocument
    decided_at: datetime
    run_id: str | None = None
    turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotDraft:
    snapshot_id: str
    incident_state: JsonDocument
    run_state: JsonDocument
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    snapshot_id: str
    incident_id: str
    run_id: str
    version: int
    event_sequence: int
    incident_state: JsonDocument
    run_state: JsonDocument
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TextContextRecord:
    turn_id: str
    incident_id: str
    run_id: str
    sequence: int
    content: JsonDocument
    occurred_at: datetime
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    incident: IncidentRecord
    run: RunRecord
    snapshot: SnapshotRecord | None
    events: tuple[RunEvent, ...]


@dataclass(frozen=True, slots=True)
class TransitionResult:
    incident: IncidentRecord
    run: RunRecord
    events: tuple[RunEvent, ...]
    snapshot: SnapshotRecord | None
    replayed: bool = False


class IncidentRepository(Protocol):
    async def get(self, incident_id: str) -> IncidentRecord | None: ...

    async def add(
        self, incident_id: str, state: JsonDocument, *, now: datetime
    ) -> IncidentRecord: ...


class RunRepository(Protocol):
    async def get(self, run_id: str) -> RunRecord | None: ...

    async def add(
        self, run_id: str, incident_id: str, state: JsonDocument, *, now: datetime
    ) -> RunRecord: ...


class EventRepository(Protocol):
    async def list_after(
        self, run_id: str, *, sequence: int = -1, limit: int = 1000
    ) -> tuple[RunEvent, ...]: ...


class SnapshotRepository(Protocol):
    async def latest(self, run_id: str) -> SnapshotRecord | None: ...


class TextContextRepository(Protocol):
    async def get(self, turn_id: str) -> TextContextRecord | None: ...

    async def list(self, run_id: str) -> tuple[TextContextRecord, ...]: ...

    async def append(self, context: TextContextRecord) -> None: ...


class IncidentUnitOfWork(Protocol):
    incidents: IncidentRepository
    runs: RunRepository
    events: EventRepository
    snapshots: SnapshotRepository
    text_context: TextContextRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    async def get_transition(
        self, incident_id: str, command_id: str, payload_sha256: str
    ) -> TransitionResult | None: ...

    async def lock_command(self, incident_id: str, command_id: str) -> None: ...

    async def persist_transition(
        self,
        *,
        command_id: str,
        payload_sha256: str,
        incident_id: str,
        run_id: str,
        expected_incident_version: int,
        expected_run_version: int,
        incident_state: JsonDocument,
        run_state: JsonDocument,
        decision: DecisionDraft,
        events: Sequence[EventDraft],
        snapshot: SnapshotDraft | None = None,
    ) -> TransitionResult: ...

    async def load_replay(self, run_id: str) -> ReplayRecord: ...


class IncidentStaleWriteError(RuntimeError):
    """An expected aggregate version no longer matches authoritative state."""


class IncidentIdempotencyConflictError(RuntimeError):
    """A retained command identifier was reused with different input."""
