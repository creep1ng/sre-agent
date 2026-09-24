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

from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.governance.dto import Principal
from sre_agent.incident.runtime import IncidentRuntime
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
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
ACTIONS = {"open_triage": "alert.triage", "triage_dismiss": "alert.dismiss"}
STATES = {"open_triage": "open", "triage_dismiss": "dismissed"}
KEY_PATTERN = r"^[\x20-\x7E]{16,128}$"
ID_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"


class TriageError(Exception):
    def __init__(self, http_status: int, code: str) -> None:
        super().__init__(code)
        self.http_status = http_status
        self.code = code


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


def _command_id(digest: str, step: str) -> str:
    return f"cmd-{digest[:12]}-{step}"


class TriageService:
    def __init__(self, database: Database, workflow: IncidentWorkflow) -> None:
        self._database = database
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
        key: str,
    ) -> None:
        # Slice boundary: link and declaration execute in C2a-3.
        if operation in ("triage_link", "triage_declare"):
            raise TriageError(422, "operation_not_supported")
        if (
            operation not in ACTIONS
            or not re.fullmatch(ID_PATTERN, alert_id)
            or not isinstance(expected_version, int)
            or not re.fullmatch(KEY_PATTERN, key)
        ):
            raise TriageError(400, "invalid_command")
        if (operation == "open_triage") == (reason is not None):
            raise TriageError(422, "invalid_reason")
        if reason is not None and not 1 <= len(reason) <= 1000:
            raise TriageError(422, "invalid_reason")

    async def execute(
        self,
        principal: Principal,
        *,
        alert_id: str,
        operation: str,
        expected_version: int,
        reason: str | None = None,
        idempotency_key: str,
    ) -> TriageResult:
        self._check(operation, alert_id, expected_version, reason, idempotency_key)
        payload = {
            "alert_id": alert_id,
            "operation": operation,
            "expected_version": expected_version,
            "reason": reason,
        }
        scope = f"triage:{alert_id}"
        digest = _digest(idempotency_key)
        created = 201 if operation == "triage_declare" else 200
        async with self._database.transaction() as session:
            await self._authorize(session, principal, ACTIONS[operation])
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
            persisted = await repository.write(
                alert_id=alert_id,
                expected_version=None if current is None else expected_version,
                status=STATES[operation],
                incident_id=None,
                reason=reason,
                severity=None,
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
