"""Alert triage commands without HTTP (issue #23, chain C2a service).

CAS on expected_version, Idempotency-Key bindings with replay-after-auth,
eligibility revalidated inside the decision transaction, declaration via
the governed incident runtime with key-derived identifiers. The server
assigns incident/run/command ids, actor and timestamp.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import Principal
from sre_agent.incident.persistence import (
    IncidentIdempotencyConflictError,
    IncidentStaleWriteError,
)
from sre_agent.incident.runtime import (
    ActorReference,
    IncidentCommand,
    IncidentRuntime,
    InvalidTransitionError,
    PreconditionFailedError,
)
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import (
    PostgresDecisionRepository,
    PostgresEventRepository,
    PostgresIncidentRepository,
    PostgresIncidentUnitOfWork,
    PostgresRunRepository,
    PostgresSnapshotRepository,
    PostgresTextContextRepository,
)
from sre_agent.persistence.repositories import (
    GrantRepository,
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
    ResourceRepository,
)
from sre_agent.triage.store import TriageRepository

WORKFLOW_TYPE = "incident_workflow"
WORKFLOW_ID = "incident-response"
READ_ACTION = "alert.read"
SEVERITIES = ("sev1", "sev2", "sev3", "sev4")
ACTIONS = {
    "open_triage": "alert.triage",
    "triage_dismiss": "alert.dismiss",
    "triage_link": "alert.associate",
    "triage_declare": "incident.declare",
}
STATES = {
    "open_triage": "open",
    "triage_dismiss": "dismissed",
    "triage_link": "linked",
    "triage_declare": "declared",
}
KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
ELIGIBLE = {"active", "investigating", "mitigating", "verifying"}
ID_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"


class TriageError(Exception):
    def __init__(self, http_status: int, code: str) -> None:
        super().__init__(code)
        self.http_status = http_status
        self.code = code


class _SessionUnits(PostgresIncidentUnitOfWork):
    """Run incident transitions inside the triage transaction.

    Every repository statement and the commit protocol are inherited from
    the chain-A unit of work; only the session lifecycle differs (the outer
    triage transaction owns begin/commit/close), so the triage write and
    the incident creation commit atomically or roll back together.
    """

    def __init__(self, session: Any) -> None:
        self._session = session
        self._transaction = None
        self.incidents = PostgresIncidentRepository(session)
        self.runs = PostgresRunRepository(session)
        self.events = PostgresEventRepository(session)
        self.snapshots = PostgresSnapshotRepository(session)
        self.decisions = PostgresDecisionRepository(session)
        self.text_context = PostgresTextContextRepository(session)

    async def __aenter__(self) -> PostgresIncidentUnitOfWork:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


@dataclass(frozen=True, slots=True)
class TriageResult:
    status: str
    incident_id: str | None
    expected_version: int
    actor: str
    decided_at: str
    replayed: bool
    http_status: int


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: str) -> str:
    return hashlib.sha256(f"sre-triage-v1\0{value}".encode()).hexdigest()


class TriageService:
    def __init__(self, database: Database, workflow: IncidentWorkflow) -> None:
        self._database = database
        self._workflow = workflow
        self._units = lambda: PostgresIncidentUnitOfWork(database)
        self._runtime = IncidentRuntime(workflow, self._units)

    async def _authorize(self, session: Any, principal: Principal, action: str) -> None:
        engine = AuthorizationDecisionEngine(ResourceRepository(session), GrantRepository(session))
        decision = await engine.evaluate(principal, action, WORKFLOW_TYPE, WORKFLOW_ID)
        if decision.decision.decision != "allow":
            raise TriageError(403, "not_authorized")

    def _check(
        self,
        operation: str,
        alert_id: str,
        expected_version: int,
        reason: Any,
        severity: Any,
        impact: Any,
        target: Any,
        key: str,
    ) -> None:
        if (
            not isinstance(operation, str)
            or operation not in ACTIONS
            or not isinstance(alert_id, str)
            or not re.fullmatch(ID_PATTERN, alert_id)
            or type(expected_version) is not int
            or not isinstance(key, str)
            or not re.fullmatch(KEY_PATTERN, key)
        ):
            raise TriageError(400, "invalid_command")
        if reason is not None and not isinstance(reason, str):
            raise TriageError(422, "invalid_reason")
        if (operation == "open_triage") == (reason is not None):
            raise TriageError(422, "invalid_reason")
        if reason is not None and not 1 <= len(reason) <= 1000:
            raise TriageError(422, "invalid_reason")
        if operation == "triage_link" and (
            not isinstance(target, str) or not re.fullmatch(ID_PATTERN, target)
        ):
            raise TriageError(422, "invalid_target")
        if operation == "triage_link" and severity is not None and severity not in SEVERITIES:
            raise TriageError(422, "invalid_severity")
        # Declare: severity sev1..sev4 required; any impact is 422 (schema-closed).
        if operation == "triage_declare":
            if severity not in SEVERITIES:
                raise TriageError(422, "invalid_severity")
            if impact is not None:
                raise TriageError(422, "invalid_impact")

    async def execute(
        self,
        principal: Principal,
        *,
        alert_id: str,
        operation: str,
        expected_version: int,
        reason: str | None = None,
        severity: str | None = None,
        impact: str | None = None,
        target_incident_id: str | None = None,
        idempotency_key: str,
    ) -> TriageResult:
        self._check(
            operation,
            alert_id,
            expected_version,
            reason,
            severity,
            impact,
            target_incident_id,
            idempotency_key,
        )
        payload = {
            "alert_id": alert_id,
            "operation": operation,
            "expected_version": expected_version,
            "reason": reason,
            "severity": severity,
            "impact": impact,
            "target_incident_id": target_incident_id,
        }
        scope = f"triage:{alert_id}"
        digest = _digest(idempotency_key)
        created = 201 if operation == "triage_declare" else 200
        async with self._database.transaction() as session:
            await self._authorize(session, principal, ACTIONS[operation])
            if operation == "triage_link":
                await self._authorize(session, principal, "run.read")
            idem = IdempotencyRepository(session)
            try:
                binding = await idem.claim_or_replay(
                    scope=scope,
                    key_digest=digest,
                    payload_sha256=_digest(_canonical(payload)),
                    principal_id=principal.principal_id,
                    method="POST",
                    canonical_path=f"/v1/alerts/{alert_id}/triage/commands",
                    binding="at_least_24h",
                    outcome=IdempotencyOutcome(
                        response_status=created, resource_id=alert_id, replayed=False
                    ),
                )
            except IdempotencyConflictError:
                raise TriageError(409, "idempotency_conflict") from None
            if binding.replayed:
                stored = dict(binding.outcome.response_payload)
                return TriageResult(replayed=True, http_status=created, **stored)
            repository = TriageRepository(session)
            current = await repository.get(alert_id)
            if (current is None and expected_version != 1) or (
                current is not None and current["expected_version"] != expected_version
            ):
                raise TriageError(409, "stale_version")
            current_status = (current or {}).get("status")
            if current_status in {"dismissed", "linked", "declared"}:
                if operation == "triage_declare" and current_status == "declared":
                    raise TriageError(409, "already_declared")
                if operation == "triage_link":
                    # Keep the established destination error when a target has
                    # since become ineligible; this check performs no writes.
                    await self._transition(
                        session,
                        operation,
                        alert_id,
                        digest,
                        principal,
                        severity,
                        impact,
                        target_incident_id,
                    )
                raise TriageError(409, "terminal_decision")
            incident_id = await self._transition(
                session,
                operation,
                alert_id,
                digest,
                principal,
                severity,
                impact,
                target_incident_id,
            )
            persisted = await repository.write(
                alert_id=alert_id,
                expected_version=None if current is None else expected_version,
                status=STATES[operation],
                incident_id=incident_id,
                reason=reason,
                severity=severity,
                actor=principal.principal_id,
                decided_at=datetime.now(UTC),
            )
            if persisted is None:
                raise TriageError(409, "stale_version")
            decided = persisted["decided_at"]
            iso = decided.isoformat() if isinstance(decided, datetime) else str(decided)
            result = {
                "status": persisted["status"],
                "incident_id": persisted["incident_id"],
                "expected_version": persisted["expected_version"],
                "actor": persisted["actor"],
                "decided_at": iso,
            }
            await idem.set_response_payload(scope=scope, key_digest=digest, response_payload=result)
            return TriageResult(replayed=False, http_status=created, **result)

    async def read_state(self, principal: Principal, *, alert_id: str) -> dict[str, Any]:
        """Authoritative triage-state read (contract getAlertTriage).

        Only the contractual read grant authorizes the read; command grants
        alone are denied, unknown alerts 404. Single SELECT, no mutation,
        no existence leakage (403 first).
        """
        async with self._database.transaction() as session:
            await self._authorize(session, principal, READ_ACTION)
            try:
                current = await TriageRepository(session).get(alert_id)
            except Exception as error:
                raise TriageError(503, "storage_unavailable") from error
        if current is None:
            raise TriageError(404, "triage_not_found")
        decided = current.get("decided_at")
        iso = decided.isoformat() if isinstance(decided, datetime) else str(decided)
        return {
            "alert_id": alert_id,
            "status": current.get("status"),
            "incident_id": current.get("incident_id"),
            "expected_version": current.get("expected_version"),
            "reason": current.get("reason"),
            "actor": current.get("actor"),
            "decided_at": iso,
        }

    async def _transition(
        self,
        session: Any,
        operation: str,
        alert_id: str,
        digest: str,
        principal: Principal,
        severity: str | None,
        impact: str | None,
        target_incident_id: str | None,
    ) -> str | None:
        if operation == "triage_link":
            if target_incident_id is None:
                raise TriageError(422, "invalid_target")
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT state->>'state' AS state FROM incident.incidents"
                            " WHERE incident_id=:incident_id FOR UPDATE"
                        ),
                        {"incident_id": target_incident_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise TriageError(404, "incident_not_found")
            if row["state"] not in ELIGIBLE:
                raise TriageError(409, "destination_ineligible")
            return target_incident_id
        if operation != "triage_declare":
            return None
        now = datetime.now(UTC)
        incident_id = f"inc-{digest[:32]}"
        run_id = f"run_{digest[:32]}"
        units = _SessionUnits(session)
        incident_state = {
            "workflow_id": self._workflow.workflow_id,
            "workflow_version": self._workflow.version,
            "state": "triage",
            "severity": None,
            "impact": None,
            "alert": {},
            "hypotheses": [],
            "evidence": [],
            "mitigation_strategy": None,
            "postmortem": None,
        }
        run_state = {
            "workflow_version": self._workflow.version,
            "current_state": "triage",
            "status": "running",
            "pending_command": None,
        }
        try:
            await units.incidents.add(incident_id, incident_state, now=now)
            await units.runs.add(run_id, incident_id, run_state, now=now)
        except IntegrityError as error:
            # Same key-derived identifiers already committed: the triage
            # outcome is gone, so the closed answer is a key conflict.
            raise TriageError(409, "idempotency_conflict") from error
        runtime = IncidentRuntime(
            self._workflow,
            lambda: units,
            clock=lambda: now,
            id_factory=lambda prefix: f"{prefix}-{digest[:24]}",
        )
        command = IncidentCommand(
            command_id=f"cmd-{digest[:32]}",
            incident_id=incident_id,
            run_id=run_id,
            transition_id="triage_declare",
            actor="human",
            actor_reference=ActorReference(
                principal_id=principal.principal_id,
                display_name=principal.display_name,
            ),
            inputs={"severity": severity},
        )
        try:
            await runtime.execute(command)
        except (InvalidTransitionError, PreconditionFailedError) as error:
            raise TriageError(422, "invalid_transition") from error
        except IncidentStaleWriteError as error:
            raise TriageError(409, "stale_version") from error
        except IncidentIdempotencyConflictError as error:
            raise TriageError(409, "idempotency_conflict") from error
        return incident_id
