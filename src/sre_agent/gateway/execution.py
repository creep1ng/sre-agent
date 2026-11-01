"""The deploy-executor as the gateway reaches it (#722): its catalog, what an approval must still
hold before the operation it approved runs, and the signed call that runs it.

The order is the one `docs/deploy-executor.md` records: the approval must still apply to the
incident as it stands, the executor's catalog must still offer the operation, and the agent must
hold `mitigation.execute` on it. A refused approval moves nothing and says why. Only then is the
executor called, signed, with an `Idempotency-Key` derived from the run and the mitigation: a
retried approval replays the executor's result instead of running the operation again. Every
attempt the agent's identity makes is audited as `mitigation.execute`, however it ends, and an
operation that ran is not answered before its audit is written.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from time import monotonic, time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from uuid import UUID

import httpx

from sre_agent.executor.signature import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign, usable_key
from sre_agent.gateway.audit import AuditProjector
from sre_agent.governance.authorization import AuthorizationDecisionEngine, AuthorizationEvaluation
from sre_agent.governance.dto import PrincipalContext
from sre_agent.incident.runtime import IncidentRuntime
from sre_agent.investigator.contract import ProposedOperation, ServiceOperations
from sre_agent.persistence.repositories import (
    CredentialRepository,
    GrantRepository,
    ResourceRepository,
)
from sre_agent.settings import Settings

if TYPE_CHECKING:
    from sre_agent.gateway.responses import AuditStore

logger = logging.getLogger(__name__)
# A rollback recreates a container and waits for it to be healthy: seconds, not milliseconds.
EXECUTION_TIMEOUT_SECONDS = 60


class ExecutionRefused(Exception):
    """The approval cannot run its operation; nothing moved, and the answer says why. `reason` is
    the audit's reason code for an attempt that reached the agent's identity."""

    def __init__(self, status: int, code: str, message: str, reason: str | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.reason = status, code, message, reason


async def service_operations(
    executor_url: str | None, service: str
) -> tuple[ServiceOperations | None, bool]:
    """The executor's catalog for a service, its one source (#722): what it offers, nothing when
    the service is not enrolled, or unreadable (fail closed)."""
    if executor_url is None:
        return None, False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{executor_url}/v1/services/{quote(service, safe='')}")
        body = response.json()
        if response.status_code == 404 and body["error"]["code"] == "service_not_enrolled":
            return None, False
        response.raise_for_status()
        view = ServiceOperations(
            service=service,
            running_image=body["container"]["image"],
            available_tags=body["available_tags"],
            operations=body["operations"],
        )
    except Exception:
        return None, True
    return view, False


class OperationExecutor:
    """Every check an approval's operation must pass, then the deploy-executor call that runs it."""

    def __init__(
        self,
        sessions: Callable[[], Any],
        runtime: IncidentRuntime,
        settings: Settings,
        audit: AuditStore | None = None,
    ) -> None:
        gateway, secret = settings.investigator_gateway, settings.audit_hmac_key
        self.sessions, self.runtime, self.url = sessions, runtime, settings.deploy_executor_url
        self.key = usable_key(settings.deploy_executor_signing_key)
        # The agent the grant is over is the one the investigator acts as.
        self.agent_key = gateway.api_key.get_secret_value() if gateway else None
        self.audit = audit if secret else None
        self.projector = AuditProjector(secret.encode()) if secret else None

    async def run(
        self, incident_id: str, run_id: str, expected_version: int | None, request_id: UUID
    ) -> Mapping[str, Any] | None:
        """The executor's receipt for the operation this approval runs, or None if it runs none."""
        view = await self.runtime.current(incident_id, run_id)
        strategy = view.incident_state.get("mitigation_strategy") or {}
        if (
            "operation" not in strategy
            or view.incident_state.get("state") != "mitigating"
            or view.incident_version != expected_version
        ):
            # Nothing to run, or the runtime replays this approval or refuses it as stale.
            return None
        operation = ProposedOperation.model_validate(strategy["operation"])
        context = await self._agent()
        if self.url is None or self.key is None or context is None or self.audit is None:
            # Nothing runs where nothing would audit it.
            raise ExecutionRefused(
                503,
                "executor_unavailable",
                "The deploy-executor, its agent or the audit is not configured.",
            )
        started, evaluation = monotonic(), None
        try:
            catalog, unreadable = await service_operations(self.url, operation.service)
            if unreadable:
                raise ExecutionRefused(
                    503,
                    "executor_unavailable",
                    "The deploy-executor's catalog could not be read.",
                    "upstream_unavailable",
                )
            problem = catalog.problem(operation) if catalog else "the service is no longer enrolled"
            if problem:
                raise ExecutionRefused(
                    409,
                    "precondition_failed",
                    f"The deploy-executor no longer offers it: {problem}.",
                    "status_conflict",
                )
            evaluation = await self._evaluate(context, operation)
            if evaluation.decision.decision != "allow":
                raise ExecutionRefused(
                    403,
                    "operation_not_authorized",
                    "The agent holds no mitigation.execute grant for this operation.",
                )
            receipt = await self._execute(
                operation, f"mitexec-{run_id}-{strategy['mitigation_id']}"
            )
        except ExecutionRefused as refused:
            await self._audited(
                started, request_id, (incident_id, run_id), context, operation, evaluation, refused
            )
            raise
        await self._audited(
            started, request_id, (incident_id, run_id), context, operation, evaluation
        )
        return receipt

    async def _agent(self) -> PrincipalContext | None:
        if self.agent_key is None:
            return None
        async with self.sessions() as session:
            context = await CredentialRepository(session).authenticate(self.agent_key)
        return context if context is not None and context.principal.kind == "agent" else None

    async def _evaluate(
        self, context: PrincipalContext, operation: ProposedOperation
    ) -> AuthorizationEvaluation:
        async with self.sessions() as session:
            engine = AuthorizationDecisionEngine(
                ResourceRepository(session), GrantRepository(session)
            )
            return await engine.evaluate(
                context.principal,
                "mitigation.execute",
                "service_operation",
                f"{operation.service}:{operation.operation}",
            )

    async def _audited(
        self,
        started: float,
        request_id: UUID,
        ids: tuple[str, str],
        context: PrincipalContext,
        operation: ProposedOperation,
        evaluation: AuthorizationEvaluation | None,
        refused: ExecutionRefused | None = None,
    ) -> None:
        """One mitigation.execute audit event for this attempt, correlated with its run."""
        if self.audit is None or self.projector is None:
            return
        status = refused.status if refused else 200
        stage = (
            "response" if refused is None else ("authorization" if status == 403 else "upstream")
        )
        try:
            event = self.projector.control_event(
                request_id,
                status,
                int((monotonic() - started) * 1000),
                stage,
                operation="mitigation.execute",
                action="invoke",
                reason=refused.reason if refused else None,
                retryable=status == 503,
                context=context,
                resource_ref=("service_operation", f"{operation.service}:{operation.operation}"),
                decision=evaluation.decision if evaluation else None,
                authorization_denial_cause=evaluation.denial_cause if evaluation else None,
                identifiers={"incident_id": ids[0], "run_id": ids[1]},
            )
            await self.audit.append(event)
        except Exception as error:
            # Only the type is logged, never the content. A refusal stands as answered; an
            # operation that ran is not answered without its audit, and nothing moves: the retry
            # sends the same key, so the executor replays its result and the audit is written.
            logger.error("mitigation_execute_audit_failed error=%s", type(error).__name__)
            if refused is None:
                raise

    async def _execute(self, operation: ProposedOperation, key: str) -> Mapping[str, Any]:
        assert self.url is not None and self.key is not None
        path = f"/v1/operations/{operation.operation}"
        body = json.dumps({"service": operation.service, **operation.parameters}).encode()
        timestamp = str(int(time()))
        headers = {
            "content-type": "application/json",
            "idempotency-key": key,
            TIMESTAMP_HEADER: timestamp,
            SIGNATURE_HEADER: sign(self.key, "POST", path, key, body, timestamp),
        }
        try:
            async with httpx.AsyncClient(timeout=EXECUTION_TIMEOUT_SECONDS) as client:
                response = await client.post(self.url + path, content=body, headers=headers)
            result = response.json()
            if response.status_code == 200:
                return {
                    "execution_id": result["execution_id"],
                    "outcome": result["outcome"],
                    "replayed": result["replayed"],
                    "before_image": result["before"]["image"],
                    "after_image": result["after"]["image"],
                    "executed_at": result["executed_at"],
                    "duration_ms": result["duration_ms"],
                }
            code = str(result["error"]["code"])
        except Exception:
            # Nothing to read: retrying sends the same key, which replays and never runs twice.
            raise ExecutionRefused(
                503,
                "executor_unavailable",
                "The deploy-executor gave no usable answer.",
                "upstream_unavailable",
            ) from None
        # Only what the executor marks retryable (Docker down or slow) is worth retrying: it
        # keeps any other failure for this key, and a refusal answers the same again.
        code = code if re.fullmatch(r"[a-z][a-z0-9_]{1,63}", code) else "an error"
        retryable = response.status_code in (503, 504)
        raise ExecutionRefused(
            503 if retryable else 409,
            "execution_failed",
            f"The deploy-executor answered {response.status_code} {code}: the incident stays "
            "mitigating.",
            "upstream_unavailable" if retryable else "upstream_failed",
        )
