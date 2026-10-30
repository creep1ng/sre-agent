"""The deploy-executor as the gateway reaches it (#722): its catalog, and what an approval must
still hold before the operation it approved runs.

The order is the one `docs/deploy-executor.md` records: the approval must still apply to the
incident as it stands, the executor's catalog must still offer the operation, and the agent must
hold `mitigation.execute` on it. A refused approval moves nothing and says why.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.incident.runtime import IncidentRuntime
from sre_agent.investigator.contract import ProposedOperation, ServiceOperations
from sre_agent.persistence.repositories import (
    CredentialRepository,
    GrantRepository,
    ResourceRepository,
)
from sre_agent.settings import Settings


class ExecutionRefused(Exception):
    """The approval cannot run its operation; nothing moved, and the answer says why."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


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
    """Every check an approval's operation must pass before the deploy-executor runs it."""

    def __init__(self, sessions: Callable[[], Any], runtime: IncidentRuntime, settings: Settings):
        gateway = settings.investigator_gateway
        self.sessions, self.runtime, self.url = sessions, runtime, settings.deploy_executor_url
        # The agent the grant is over is the one the investigator acts as.
        self.agent_key = gateway.api_key.get_secret_value() if gateway else None

    async def admit(
        self, incident_id: str, run_id: str, expected_version: int | None
    ) -> tuple[ProposedOperation, str] | None:
        """The operation this approval runs and its mitigation, or None when it runs nothing."""
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
        catalog, unreadable = await service_operations(self.url, operation.service)
        if self.url is None or self.agent_key is None or unreadable:
            raise ExecutionRefused(
                503,
                "executor_unavailable",
                "The deploy-executor is not configured or not reachable.",
            )
        problem = catalog.problem(operation) if catalog else "the service is no longer enrolled"
        if problem:
            raise ExecutionRefused(
                409, "precondition_failed", f"The deploy-executor no longer offers it: {problem}."
            )
        if not await self._granted(self.agent_key, operation):
            raise ExecutionRefused(
                403,
                "operation_not_authorized",
                "The agent holds no mitigation.execute grant for this operation.",
            )
        return operation, str(strategy["mitigation_id"])

    async def _granted(self, agent_key: str, operation: ProposedOperation) -> bool:
        async with self.sessions() as session:
            context = await CredentialRepository(session).authenticate(agent_key)
            if context is None or context.principal.kind != "agent":
                return False
            engine = AuthorizationDecisionEngine(
                ResourceRepository(session), GrantRepository(session)
            )
            evaluation = await engine.evaluate(
                context.principal,
                "mitigation.execute",
                "service_operation",
                f"{operation.service}:{operation.operation}",
            )
        return evaluation.decision.decision == "allow"
