"""PostgreSQL adapter for authoritative incident and run persistence."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, Self, cast

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from sre_agent.incident.persistence import (
    DecisionDraft,
    DecisionRecord,
    EventDraft,
    IncidentIdempotencyConflictError,
    IncidentRecord,
    IncidentStaleWriteError,
    JsonDocument,
    ReplayRecord,
    RunEvent,
    RunRecord,
    SnapshotDraft,
    SnapshotRecord,
    TextContextRecord,
    TransitionResult,
)
from sre_agent.persistence.database import Database


def _document(value: JsonDocument) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _incident(row: Mapping[str, Any]) -> IncidentRecord:
    return IncidentRecord(
        incident_id=row["incident_id"],
        state=row["state"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _run(row: Mapping[str, Any]) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        incident_id=row["incident_id"],
        state=row["state"],
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _event(row: Mapping[str, Any]) -> RunEvent:
    return RunEvent(
        event_id=row["event_id"],
        incident_id=row["incident_id"],
        run_id=row["run_id"],
        sequence=row["sequence"],
        kind=row["kind"],
        payload=row["payload"],
        occurred_at=row["occurred_at"],
        turn_id=row["turn_id"],
    )


def _snapshot(row: Mapping[str, Any]) -> SnapshotRecord:
    return SnapshotRecord(
        snapshot_id=row["snapshot_id"],
        incident_id=row["incident_id"],
        run_id=row["run_id"],
        version=row["version"],
        event_sequence=row["event_sequence"],
        incident_state=row["incident_state"],
        run_state=row["run_state"],
        created_at=row["created_at"],
    )


def _context(row: Mapping[str, Any]) -> TextContextRecord:
    return TextContextRecord(
        turn_id=row["turn_id"],
        incident_id=row["incident_id"],
        run_id=row["run_id"],
        sequence=row["sequence"],
        content=row["content"],
        occurred_at=row["occurred_at"],
        task_id=row["task_id"],
    )


def _decision(row: Mapping[str, Any]) -> DecisionRecord:
    return DecisionRecord(
        decision_id=row["decision_id"],
        incident_id=row["incident_id"],
        run_id=row["run_id"],
        turn_id=row["turn_id"],
        document=row["document"],
        decided_at=row["decided_at"],
    )


class PostgresIncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, incident_id: str) -> IncidentRecord | None:
        row = (
            (
                await self._session.execute(
                    text("SELECT * FROM incident.incidents WHERE incident_id=:incident_id"),
                    {"incident_id": incident_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return _incident(row) if row else None

    async def add(self, incident_id: str, state: JsonDocument, *, now: datetime) -> IncidentRecord:
        row = (
            (
                await self._session.execute(
                    text("""INSERT INTO incident.incidents
                    (incident_id, state, version, created_at, updated_at)
                    VALUES (:incident_id, CAST(:state AS jsonb), 0, :now, :now)
                    RETURNING *"""),
                    {"incident_id": incident_id, "state": _document(state), "now": now},
                )
            )
            .mappings()
            .one()
        )
        return _incident(row)

    async def list_eligible(self, states: Sequence[str]) -> tuple[dict[str, str], ...]:
        rows = (
            (
                await self._session.execute(
                    text("""SELECT incident_id, state->>'state' AS state
                FROM incident.incidents
                WHERE state->>'state' = ANY(:states)
                ORDER BY incident_id ASC
                LIMIT 100""").bindparams(bindparam("states", type_=ARRAY(String()))),
                    {"states": list(states)},
                )
            )
            .mappings()
            .all()
        )
        return tuple({"incident_id": row["incident_id"], "state": row["state"]} for row in rows)


class PostgresRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, run_id: str) -> RunRecord | None:
        row = (
            (
                await self._session.execute(
                    text("SELECT * FROM incident.runs WHERE run_id=:run_id"), {"run_id": run_id}
                )
            )
            .mappings()
            .one_or_none()
        )
        return _run(row) if row else None

    async def get_for_incident(self, run_id: str, incident_id: str) -> RunRecord | None:
        row = (
            (
                await self._session.execute(
                    text(
                        "SELECT * FROM incident.runs "
                        "WHERE run_id=:run_id AND incident_id=:incident_id"
                    ),
                    {"run_id": run_id, "incident_id": incident_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return _run(cast(Mapping[str, Any], row)) if row else None

    async def add(
        self, run_id: str, incident_id: str, state: JsonDocument, *, now: datetime
    ) -> RunRecord:
        row = (
            (
                await self._session.execute(
                    text("""INSERT INTO incident.runs
                    (run_id, incident_id, state, version, created_at, updated_at)
                    VALUES (:run_id, :incident_id, CAST(:state AS jsonb), 0, :now, :now)
                    RETURNING *"""),
                    {
                        "run_id": run_id,
                        "incident_id": incident_id,
                        "state": _document(state),
                        "now": now,
                    },
                )
            )
            .mappings()
            .one()
        )
        return _run(row)

    async def list_ids(self, incident_id: str) -> tuple[str, ...]:
        rows = (
            (
                await self._session.execute(
                    text("""SELECT run_id FROM incident.runs
                    WHERE incident_id=:incident_id
                    ORDER BY created_at ASC, run_id ASC"""),
                    {"incident_id": incident_id},
                )
            )
            .mappings()
            .all()
        )
        return tuple(row["run_id"] for row in rows)


class PostgresEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_after(
        self, run_id: str, *, sequence: int = -1, limit: int = 1000
    ) -> tuple[RunEvent, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = (
            (
                await self._session.execute(
                    text("""SELECT * FROM incident.run_events
                    WHERE run_id=:run_id AND sequence>:sequence
                    ORDER BY sequence ASC, event_id ASC LIMIT :limit"""),
                    {"run_id": run_id, "sequence": sequence, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return tuple(_event(row) for row in rows)


class PostgresSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest(self, run_id: str) -> SnapshotRecord | None:
        row = (
            (
                await self._session.execute(
                    text("""SELECT * FROM incident.snapshots WHERE run_id=:run_id
                    ORDER BY event_sequence DESC, version DESC, snapshot_id DESC LIMIT 1"""),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return _snapshot(row) if row else None


class PostgresTextContextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, turn_id: str) -> TextContextRecord | None:
        row = (
            (
                await self._session.execute(
                    text("SELECT * FROM incident.text_context WHERE turn_id=:turn_id"),
                    {"turn_id": turn_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return _context(row) if row else None

    async def list(self, run_id: str) -> tuple[TextContextRecord, ...]:
        rows = (
            (
                await self._session.execute(
                    text("""SELECT * FROM incident.text_context WHERE run_id=:run_id
                    ORDER BY sequence ASC, turn_id ASC"""),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .all()
        )
        return tuple(_context(row) for row in rows)

    async def append(self, context: TextContextRecord) -> None:
        await self._session.execute(
            text("""INSERT INTO incident.text_context
                (turn_id, incident_id, run_id, task_id, sequence, content, occurred_at)
                VALUES (:turn_id, :incident_id, :run_id, :task_id, :sequence,
                        CAST(:content AS jsonb), :occurred_at)"""),
            {
                "turn_id": context.turn_id,
                "incident_id": context.incident_id,
                "run_id": context.run_id,
                "task_id": context.task_id,
                "sequence": context.sequence,
                "content": _document(context.content),
                "occurred_at": context.occurred_at,
            },
        )


class PostgresDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, decision_id: str) -> DecisionRecord | None:
        row = (
            (
                await self._session.execute(
                    text("SELECT * FROM incident.decisions WHERE decision_id=:decision_id"),
                    {"decision_id": decision_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return _decision(row) if row else None


class PostgresIncidentUnitOfWork:
    """One explicit SQL transaction spanning incident-owned repositories."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._session: AsyncSession | None = None
        self._transaction: Any = None
        self._dispatch_connection: AsyncConnection | None = None
        self._dispatch_lock_name_held: str | None = None

    async def __aenter__(self) -> Self:
        self._session = self._database.sessions()
        self._transaction = self._session.begin()
        await self._transaction.__aenter__()
        self.incidents = PostgresIncidentRepository(self._session)
        self.runs = PostgresRunRepository(self._session)
        self.events = PostgresEventRepository(self._session)
        self.snapshots = PostgresSnapshotRepository(self._session)
        self.decisions = PostgresDecisionRepository(self._session)
        self.text_context = PostgresTextContextRepository(self._session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        assert self._session is not None and self._transaction is not None
        try:
            await self._transaction.__aexit__(exc_type, exc, traceback)
        finally:
            try:
                await self._release_dispatch_lock()
            finally:
                await self._session.close()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("incident unit of work is not active")
        return self._session

    async def get_transition(
        self, incident_id: str, command_id: str, payload_sha256: str
    ) -> TransitionResult | None:
        session = self._require_session()
        row = (
            (
                await session.execute(
                    text("""SELECT payload_sha256, result FROM incident.transition_commits
                    WHERE incident_id=:incident_id AND command_id=:command_id"""),
                    {"incident_id": incident_id, "command_id": command_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["payload_sha256"] != payload_sha256:
            raise IncidentIdempotencyConflictError(
                f"command payload conflict: {incident_id}/{command_id}"
            )
        return _decode_result(row["result"], replayed=True)

    async def lock_command(self, incident_id: str, command_id: str) -> None:
        """Serialize validation and commit for one idempotency key."""
        await self._require_session().execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 146))"),
            {"key": f"{incident_id}:{command_id}"},
        )

    async def commit(self) -> None:
        """Commit the current unit; the dedicated dispatch connection remains held."""
        assert self._session is not None and self._transaction is not None
        await self._transaction.__aexit__(None, None, None)
        self._transaction = self._session.begin()
        await self._transaction.__aenter__()

    @staticmethod
    def _dispatch_lock_name(incident_id: str, run_id: str) -> str:
        return f"incident-investigation:{incident_id}:{run_id}"

    async def _lock_incident_run(self, incident_id: str, run_id: str) -> tuple[Any, Any]:
        session = self._require_session()
        incident = (
            (
                await session.execute(
                    text(
                        "SELECT version FROM incident.incidents "
                        "WHERE incident_id=:incident_id FOR UPDATE"
                    ),
                    {"incident_id": incident_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        run = (
            (
                await session.execute(
                    text(
                        "SELECT version FROM incident.runs "
                        "WHERE run_id=:run_id AND incident_id=:incident_id FOR UPDATE"
                    ),
                    {"run_id": run_id, "incident_id": incident_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if incident is None or run is None:
            raise IncidentStaleWriteError(f"missing incident run: {incident_id}/{run_id}")
        return incident, run

    async def _lock_run_event_sequence(self, run_id: str) -> None:
        await self._require_session().execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:run_id, 146))"),
            {"run_id": run_id},
        )

    async def _dispatch_events(self, run_id: str) -> list[Mapping[str, Any]]:
        session = self._require_session()
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT payload FROM incident.run_events "
                        "WHERE run_id=:run_id AND kind='dispatch_receipt' ORDER BY sequence"
                    ),
                    {"run_id": run_id},
                )
            )
            .mappings()
            .all()
        )
        return [cast(Mapping[str, Any], row["payload"]) for row in rows]

    async def _append_run_events(
        self,
        incident_id: str,
        run_id: str,
        *,
        decision: DecisionDraft,
        events: Sequence[EventDraft],
    ) -> tuple[RunEvent, ...]:
        session = self._require_session()
        if decision.run_id not in (None, run_id) or not events:
            raise ValueError("dispatch records require one run decision and at least one event")
        if any(event.kind not in {"dispatch_receipt", "investigation_result"} for event in events):
            raise ValueError(
                "investigation dispatch may append only safe result and receipt events"
            )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:run_id, 146))"),
            {"run_id": run_id},
        )
        await session.execute(
            text("""INSERT INTO incident.decisions
                (decision_id, incident_id, run_id, turn_id, document, decided_at)
                VALUES (:decision_id, :incident_id, :run_id, :turn_id,
                        CAST(:document AS jsonb), :decided_at)"""),
            {
                "decision_id": decision.decision_id,
                "incident_id": incident_id,
                "run_id": run_id,
                "turn_id": decision.turn_id,
                "document": _document(decision.document),
                "decided_at": decision.decided_at,
            },
        )
        last_sequence = await session.scalar(
            text(
                "SELECT COALESCE(MAX(sequence), -1) FROM incident.run_events WHERE run_id=:run_id"
            ),
            {"run_id": run_id},
        )
        stored: list[RunEvent] = []
        for sequence, draft in enumerate(events, start=int(last_sequence) + 1):
            payload = dict(draft.payload)
            payload.setdefault("decision_id", decision.decision_id)
            row = (
                (
                    await session.execute(
                        text("""INSERT INTO incident.run_events
                            (event_id, incident_id, run_id, turn_id, sequence,
                             kind, payload, occurred_at)
                            VALUES (:event_id, :incident_id, :run_id, :turn_id, :sequence,
                                    :kind, CAST(:payload AS jsonb), :occurred_at) RETURNING *"""),
                        {
                            "event_id": draft.event_id,
                            "incident_id": incident_id,
                            "run_id": run_id,
                            "turn_id": draft.turn_id,
                            "sequence": sequence,
                            "kind": draft.kind,
                            "payload": _document(payload),
                            "occurred_at": draft.occurred_at,
                        },
                    )
                )
                .mappings()
                .one()
            )
            stored.append(_event(cast(Mapping[str, Any], row)))
        await session.execute(
            text("UPDATE incident.runs SET updated_at=:updated_at WHERE run_id=:run_id"),
            {"updated_at": max(event.occurred_at for event in events), "run_id": run_id},
        )
        return tuple(stored)

    async def claim_run_dispatch(
        self,
        incident_id: str,
        run_id: str,
        *,
        intent_decision: DecisionDraft,
        intent_event: EventDraft,
        interrupted_decision: DecisionDraft,
        interrupted_event: EventDraft,
    ) -> Literal["claimed", "active", "complete", "interrupted"]:
        lock_name = self._dispatch_lock_name(incident_id, run_id)
        if self._dispatch_connection is not None:
            raise RuntimeError("unit of work already holds a dispatch lock")
        connection = await self._database.engine.connect()
        self._dispatch_connection = connection
        try:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:lock_name, 147))"),
                {"lock_name": lock_name},
            )
            if acquired:
                self._dispatch_lock_name_held = lock_name
            await connection.commit()
        except BaseException as error:
            self._dispatch_connection = None
            self._dispatch_lock_name_held = None
            try:
                await connection.invalidate(error)
            finally:
                await connection.close()
            raise
        if not acquired:
            self._dispatch_connection = None
            await connection.close()
            return "active"
        await self._lock_run_event_sequence(run_id)
        await self._lock_incident_run(incident_id, run_id)
        receipts = [
            item.get("dispatch_receipt")
            for item in await self._dispatch_events(run_id)
            if isinstance(item, Mapping)
        ]
        terminal = any(
            isinstance(receipt, Mapping)
            and receipt.get("dispatch_id") == run_id
            and receipt.get("phase") == "outcome"
            and receipt.get("status") in {"success", "confirmed_failure", "unknown"}
            for receipt in receipts
        )
        if terminal:
            return "complete"
        pending = any(
            isinstance(receipt, Mapping)
            and receipt.get("dispatch_id") == run_id
            and receipt.get("phase") == "intent"
            and receipt.get("status") == "pending"
            for receipt in receipts
        )
        if pending or receipts:
            await self._append_run_events(
                incident_id,
                run_id,
                decision=interrupted_decision,
                events=(interrupted_event,),
            )
            await self.commit()
            return "interrupted"
        await self._append_run_events(
            incident_id, run_id, decision=intent_decision, events=(intent_event,)
        )
        await self.commit()
        return "claimed"

    async def complete_run_dispatch(
        self,
        incident_id: str,
        run_id: str,
        *,
        decision: DecisionDraft,
        events: Sequence[EventDraft],
        expected_incident_version: int | None = None,
        incident_patch: JsonDocument | None = None,
    ) -> bool:
        await self._lock_run_event_sequence(run_id)
        incident, _run = await self._lock_incident_run(incident_id, run_id)
        receipts = [
            item.get("dispatch_receipt")
            for item in await self._dispatch_events(run_id)
            if isinstance(item, Mapping)
        ]
        if any(
            isinstance(receipt, Mapping)
            and receipt.get("dispatch_id") == run_id
            and receipt.get("phase") == "outcome"
            and receipt.get("status") in {"success", "confirmed_failure", "unknown"}
            for receipt in receipts
        ):
            return False
        if not any(
            isinstance(receipt, Mapping)
            and receipt.get("dispatch_id") == run_id
            and receipt.get("phase") == "intent"
            and receipt.get("status") == "pending"
            for receipt in receipts
        ):
            return False
        if (
            expected_incident_version is not None
            and int(incident["version"]) != expected_incident_version
        ):
            raise IncidentStaleWriteError(f"stale investigation result: {incident_id}/{run_id}")
        terminal_events = [
            receipt
            for event in events
            if event.kind == "dispatch_receipt"
            and isinstance((receipt := event.payload.get("dispatch_receipt")), Mapping)
            and receipt.get("dispatch_id") == run_id
            and receipt.get("phase") == "outcome"
            and receipt.get("status") in {"success", "confirmed_failure", "unknown"}
        ]
        if len(terminal_events) != 1:
            raise ValueError("a completed dispatch must append one terminal receipt")
        if incident_patch is not None:
            if (
                expected_incident_version is None
                or set(incident_patch) != {"hypotheses", "evidence"}
                or not isinstance(incident_patch["hypotheses"], list)
                or not isinstance(incident_patch["evidence"], list)
            ):
                raise ValueError(
                    "event-only dispatch patches require hypothesis and evidence lists"
                )
            if terminal_events[0].get("status") != "success":
                raise ValueError("event-only dispatch patches require a success receipt")
            patch_events = [
                event
                for event in events
                if event.kind == "investigation_result"
                and event.payload.get("incident_patch") == incident_patch
            ]
            if len(patch_events) != 1:
                raise ValueError("event-only dispatch patch must be recorded in its result event")
            updated_at = max(event.occurred_at for event in events)
            updated = await self._require_session().execute(
                text("""UPDATE incident.incidents
                    SET state=state || CAST(:incident_patch AS jsonb),
                        version=version+1, updated_at=:updated_at
                    WHERE incident_id=:incident_id AND version=:expected_version
                    RETURNING version"""),
                {
                    "incident_id": incident_id,
                    "incident_patch": _document(incident_patch),
                    "expected_version": expected_incident_version,
                    "updated_at": updated_at,
                },
            )
            if updated.scalar_one_or_none() is None:
                raise IncidentStaleWriteError(f"stale investigation result: {incident_id}/{run_id}")
        await self._append_run_events(incident_id, run_id, decision=decision, events=events)
        return True

    async def release_run_dispatch(self, incident_id: str, run_id: str) -> None:
        lock_name = self._dispatch_lock_name(incident_id, run_id)
        if self._dispatch_lock_name_held not in (None, lock_name):
            raise RuntimeError("unit of work holds a different dispatch lock")
        await self._release_dispatch_lock()

    async def _release_dispatch_lock(self) -> None:
        connection, self._dispatch_connection = self._dispatch_connection, None
        lock_name, self._dispatch_lock_name_held = self._dispatch_lock_name_held, None
        if connection is None:
            return
        try:
            if lock_name is not None:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:lock_name, 147))"),
                    {"lock_name": lock_name},
                )
                await connection.commit()
        except DBAPIError as error:
            await connection.invalidate(error)
        except BaseException:
            await connection.invalidate()
            raise
        finally:
            await connection.close()

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
        dispatch_id: str | None = None,
    ) -> TransitionResult:
        session = self._require_session()
        await self.lock_command(incident_id, command_id)
        replay = await self.get_transition(incident_id, command_id, payload_sha256)
        if replay is not None:
            return replay
        if len(payload_sha256) != 64 or not set(payload_sha256) <= set("0123456789abcdef"):
            raise ValueError("payload_sha256 must contain 64 hexadecimal characters")
        if decision.run_id not in (None, run_id):
            raise ValueError("decision run_id must match the transition run")
        if not events:
            raise ValueError("an incident transition must append at least one event")
        if snapshot is not None and (
            snapshot.incident_state != incident_state or snapshot.run_state != run_state
        ):
            raise ValueError("snapshot state must match the committed transition state")
        await self._lock_run_event_sequence(run_id)
        if dispatch_id is not None:
            if dispatch_id != run_id:
                raise IncidentStaleWriteError("investigation dispatch identity does not match run")
            receipts = [
                item.get("dispatch_receipt")
                for item in await self._dispatch_events(run_id)
                if isinstance(item, Mapping)
            ]
            if any(
                isinstance(receipt, Mapping)
                and receipt.get("dispatch_id") == dispatch_id
                and receipt.get("phase") == "outcome"
                and receipt.get("status") in {"success", "confirmed_failure", "unknown"}
                for receipt in receipts
            ):
                raise IncidentStaleWriteError("investigation dispatch is already terminal")
            if not any(
                isinstance(receipt, Mapping)
                and receipt.get("dispatch_id") == dispatch_id
                and receipt.get("phase") == "intent"
                and receipt.get("status") == "pending"
                for receipt in receipts
            ):
                raise IncidentStaleWriteError("investigation dispatch intent is missing")
            terminal_receipts = [
                receipt
                for event in events
                if event.kind == "dispatch_receipt"
                and isinstance((receipt := event.payload.get("dispatch_receipt")), Mapping)
                and receipt.get("dispatch_id") == dispatch_id
                and receipt.get("phase") == "outcome"
                and receipt.get("status") == "success"
            ]
            if len(terminal_receipts) != 1:
                raise ValueError("a dispatch transition must append its success receipt")
        updated_at = decision.decided_at
        incident_row = (
            (
                await session.execute(
                    text("""UPDATE incident.incidents
                    SET state=CAST(:state AS jsonb), version=version+1, updated_at=:updated_at
                    WHERE incident_id=:incident_id AND version=:expected_version RETURNING *"""),
                    {
                        "state": _document(incident_state),
                        "updated_at": updated_at,
                        "incident_id": incident_id,
                        "expected_version": expected_incident_version,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        run_row = (
            (
                await session.execute(
                    text("""UPDATE incident.runs
                    SET state=CAST(:state AS jsonb), version=version+1, updated_at=:updated_at
                    WHERE run_id=:run_id AND incident_id=:incident_id
                      AND version=:expected_version RETURNING *"""),
                    {
                        "state": _document(run_state),
                        "updated_at": updated_at,
                        "run_id": run_id,
                        "incident_id": incident_id,
                        "expected_version": expected_run_version,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if incident_row is None or run_row is None:
            raise IncidentStaleWriteError(f"stale incident transition: {incident_id}/{run_id}")
        await session.execute(
            text("""INSERT INTO incident.decisions
                (decision_id, incident_id, run_id, turn_id, document, decided_at)
                VALUES (:decision_id, :incident_id, :run_id, :turn_id,
                        CAST(:document AS jsonb), :decided_at)"""),
            {
                "decision_id": decision.decision_id,
                "incident_id": incident_id,
                "run_id": decision.run_id,
                "turn_id": decision.turn_id,
                "document": _document(decision.document),
                "decided_at": decision.decided_at,
            },
        )
        last_sequence = await session.scalar(
            text(
                "SELECT COALESCE(MAX(sequence), -1) FROM incident.run_events WHERE run_id=:run_id"
            ),
            {"run_id": run_id},
        )
        stored_events: list[RunEvent] = []
        for sequence, draft in enumerate(events, start=int(last_sequence) + 1):
            row = (
                (
                    await session.execute(
                        text("""INSERT INTO incident.run_events
                        (event_id, incident_id, run_id, turn_id, sequence,
                         kind, payload, occurred_at)
                        VALUES (:event_id, :incident_id, :run_id, :turn_id, :sequence, :kind,
                                CAST(:payload AS jsonb), :occurred_at) RETURNING *"""),
                        {
                            "event_id": draft.event_id,
                            "incident_id": incident_id,
                            "run_id": run_id,
                            "turn_id": draft.turn_id,
                            "sequence": sequence,
                            "kind": draft.kind,
                            "payload": _document(draft.payload),
                            "occurred_at": draft.occurred_at,
                        },
                    )
                )
                .mappings()
                .one()
            )
            stored_events.append(_event(row))
        final_sequence = stored_events[-1].sequence if stored_events else int(last_sequence)
        stored_snapshot = await self._append_snapshot(
            incident_id,
            run_id,
            version=run_row["version"],
            event_sequence=final_sequence,
            draft=snapshot,
        )
        result = TransitionResult(
            incident=_incident(incident_row),
            run=_run(run_row),
            events=tuple(stored_events),
            snapshot=stored_snapshot,
        )
        await session.execute(
            text("""INSERT INTO incident.transition_commits
                (incident_id, command_id, payload_sha256, result, committed_at)
                VALUES (:incident_id, :command_id, :payload_sha256,
                        CAST(:result AS jsonb), :committed_at)"""),
            {
                "incident_id": incident_id,
                "command_id": command_id,
                "payload_sha256": payload_sha256,
                "result": _document(_encode_result(result)),
                "committed_at": updated_at,
            },
        )
        return result

    async def _append_snapshot(
        self,
        incident_id: str,
        run_id: str,
        *,
        version: int,
        event_sequence: int,
        draft: SnapshotDraft | None,
    ) -> SnapshotRecord | None:
        if draft is None:
            return None
        row = (
            (
                await self._require_session().execute(
                    text("""INSERT INTO incident.snapshots
                    (snapshot_id, incident_id, run_id, version, event_sequence,
                     incident_state, run_state, created_at)
                    VALUES (:snapshot_id, :incident_id, :run_id, :version, :event_sequence,
                            CAST(:incident_state AS jsonb), CAST(:run_state AS jsonb), :created_at)
                    RETURNING *"""),
                    {
                        "snapshot_id": draft.snapshot_id,
                        "incident_id": incident_id,
                        "run_id": run_id,
                        "version": version,
                        "event_sequence": event_sequence,
                        "incident_state": _document(draft.incident_state),
                        "run_state": _document(draft.run_state),
                        "created_at": draft.created_at,
                    },
                )
            )
            .mappings()
            .one()
        )
        return _snapshot(row)

    async def load_replay(self, run_id: str, *, incident_id: str) -> ReplayRecord:
        session = self._require_session()
        incident_row = (
            (
                await session.execute(
                    text("""SELECT * FROM incident.incidents
                    WHERE incident_id=:incident_id FOR SHARE"""),
                    {"incident_id": incident_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if incident_row is None:
            raise RuntimeError(f"incident replay aggregate is unavailable: {run_id}")
        run_row = (
            (
                await session.execute(
                    text("""SELECT * FROM incident.runs
                    WHERE run_id=:run_id AND incident_id=:incident_id FOR SHARE"""),
                    {"run_id": run_id, "incident_id": incident_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if run_row is None:
            raise RuntimeError(f"incident replay aggregate is unavailable: {run_id}")
        snapshot = await self.snapshots.latest(run_id)
        sequence = snapshot.event_sequence if snapshot else -1
        replay_events: list[RunEvent] = []
        while batch := await self.events.list_after(run_id, sequence=sequence):
            replay_events.extend(batch)
            sequence = batch[-1].sequence
            if len(batch) < 1000:
                break
        return ReplayRecord(
            incident=_incident(incident_row),
            run=_run(run_row),
            snapshot=snapshot,
            events=tuple(replay_events),
        )


def _encode_time(value: datetime) -> str:
    return value.isoformat()


def _encode_result(result: TransitionResult) -> dict[str, Any]:
    incident = result.incident
    run = result.run
    snapshot = result.snapshot
    return {
        "incident": {
            "incident_id": incident.incident_id,
            "state": incident.state,
            "version": incident.version,
            "created_at": _encode_time(incident.created_at),
            "updated_at": _encode_time(incident.updated_at),
        },
        "run": {
            "run_id": run.run_id,
            "incident_id": run.incident_id,
            "state": run.state,
            "version": run.version,
            "created_at": _encode_time(run.created_at),
            "updated_at": _encode_time(run.updated_at),
        },
        "events": [
            {
                "event_id": event.event_id,
                "incident_id": event.incident_id,
                "run_id": event.run_id,
                "sequence": event.sequence,
                "kind": event.kind,
                "payload": event.payload,
                "occurred_at": _encode_time(event.occurred_at),
                "turn_id": event.turn_id,
            }
            for event in result.events
        ],
        "snapshot": (
            {
                "snapshot_id": snapshot.snapshot_id,
                "incident_id": snapshot.incident_id,
                "run_id": snapshot.run_id,
                "version": snapshot.version,
                "event_sequence": snapshot.event_sequence,
                "incident_state": snapshot.incident_state,
                "run_state": snapshot.run_state,
                "created_at": _encode_time(snapshot.created_at),
            }
            if snapshot
            else None
        ),
    }


def _decode_result(document: Mapping[str, Any], *, replayed: bool) -> TransitionResult:
    incident = document["incident"]
    run = document["run"]
    snapshot = document["snapshot"]
    return TransitionResult(
        incident=IncidentRecord(
            incident_id=incident["incident_id"],
            state=incident["state"],
            version=incident["version"],
            created_at=datetime.fromisoformat(incident["created_at"]),
            updated_at=datetime.fromisoformat(incident["updated_at"]),
        ),
        run=RunRecord(
            run_id=run["run_id"],
            incident_id=run["incident_id"],
            state=run["state"],
            version=run["version"],
            created_at=datetime.fromisoformat(run["created_at"]),
            updated_at=datetime.fromisoformat(run["updated_at"]),
        ),
        events=tuple(
            RunEvent(
                event_id=event["event_id"],
                incident_id=event["incident_id"],
                run_id=event["run_id"],
                sequence=event["sequence"],
                kind=event["kind"],
                payload=event["payload"],
                occurred_at=datetime.fromisoformat(event["occurred_at"]),
                turn_id=event["turn_id"],
            )
            for event in document["events"]
        ),
        snapshot=(
            SnapshotRecord(
                snapshot_id=snapshot["snapshot_id"],
                incident_id=snapshot["incident_id"],
                run_id=snapshot["run_id"],
                version=snapshot["version"],
                event_sequence=snapshot["event_sequence"],
                incident_state=snapshot["incident_state"],
                run_state=snapshot["run_state"],
                created_at=datetime.fromisoformat(snapshot["created_at"]),
            )
            if snapshot
            else None
        ),
        replayed=replayed,
    )
