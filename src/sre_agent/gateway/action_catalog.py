"""GET /v1/action-catalog: what the deploy-executor may run, who runs it and what it ran (#870).

Three sources, joined here and never in the browser: the executor's own catalog (through the
gateway's executor client), the `mitigation.execute` evaluation an approval passes, and the
`mitigation.execute` audit events. The audit keeps HMAC references only, so an attempt is matched
to its operation and to a recent run by recomputing those references. A run.read incident query,
not audited; it returns no executor address, signing detail or proposal parameter.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sre_agent.gateway.execution import OperationExecutor, executor_catalog, service_operations
from sre_agent.gateway.incidents import IncidentQueryService
from sre_agent.incident.persistence import IncidentUnitOfWork
from sre_agent.incident.projections import actor_reference, utc_iso
from sre_agent.incident.workflow import IncidentWorkflow
from sre_agent.investigator.contract import ProposedOperation

# Attempts read from the audit, runs an attempt may belong to, attempts shown per operation.
AUDIT_WINDOW, RUN_WINDOW, EXECUTIONS_SHOWN = 50, 200, 5
OUTCOMES = {"success": "succeeded", "denied": "refused", "error": "failed"}


class ActionCatalogService(IncidentQueryService):
    """The action catalog under the incident list's authorization (run.read)."""

    def __init__(
        self,
        sessions: Any,
        workflow: IncidentWorkflow,
        units: Callable[[], IncidentUnitOfWork],
        executor: OperationExecutor,
    ) -> None:
        super().__init__(sessions, workflow, units)
        self.executor = executor

    async def read(self, authorization: str | None) -> JSONResponse:
        request_id = uuid4()
        _, error = await self._authorized_principal(request_id, authorization)
        if error is not None:
            return error
        try:
            status, offered = await self._offered()
            runner = await self._runner(offered)
            executions = await self._executions(offered)
        except Exception:
            return self._error(request_id, 503)
        services: dict[str, list[dict[str, Any]]] = {}
        for (service, operation), parameters in offered.items():
            services.setdefault(service, []).append(
                {
                    "operation": operation,
                    "parameters": parameters,
                    "runner": runner.get((service, operation)),
                    "executions": executions.get((service, operation), [])[:EXECUTIONS_SHOWN],
                }
            )
        body = {
            "executor_status": status,
            "services": [
                {"service": service, "operations": operations}
                for service, operations in sorted(services.items())
            ],
        }
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    async def _offered(self) -> tuple[str, dict[tuple[str, str], list[dict[str, Any]] | None]]:
        """Each (service, operation) with its parameters; the registered resources when the
        executor does not answer, with parameters unknown."""
        url = self.executor.url
        catalog = await executor_catalog(url) if url is not None else None
        if catalog is None:
            async with self.sessions() as session:
                rows = await session.execute(
                    text(
                        "SELECT resource_id FROM resources WHERE resource_type='service_operation'"
                        " AND status='active' ORDER BY resource_id"
                    )
                )
                registered = [row[0].partition(":") for row in rows]
            status = "unavailable" if url is not None else "not_configured"
            return status, {(service, operation): None for service, _, operation in registered}
        rollbacks = [
            entry["service"]
            for entry in catalog
            if any(item["operation"] == "deployment.rollback" for item in entry["operations"])
        ]
        views = await asyncio.gather(*(service_operations(url, name) for name in rollbacks))
        tags: dict[str, list[str]] = {}
        for name, (view, _) in zip(rollbacks, views, strict=True):
            if view is not None:
                running = (view.running_image or "").rpartition(":")[2]
                tags[name] = [tag for tag in view.available_tags if tag != running]
        offered: dict[tuple[str, str], list[dict[str, Any]] | None] = {}
        for entry in catalog:
            flags = entry.get("flags") or {}
            for item in entry["operations"]:
                parameters = []
                for name in item["parameters"]:
                    if name == "to_tag":
                        allowed = tags.get(entry["service"])
                    elif name == "flag":
                        allowed = sorted(flags)
                    elif name == "variant":
                        allowed = sorted({v for flag in flags.values() for v in flag["allowed"]})
                    else:
                        allowed = None
                    parameters.append({"name": name, "allowed": allowed})
                offered[(entry["service"], item["operation"])] = parameters
        return "available", offered

    async def _runner(self, offered: dict[tuple[str, str], Any]) -> dict[tuple[str, str], Any]:
        """The agent approvals run as, for each operation it holds mitigation.execute on."""
        context = await self.executor._agent()
        if context is None:
            return {}
        runner = {"principal_id": context.principal.principal_id,
                  "display_name": context.principal.display_name}  # fmt: skip
        allowed = {}
        for service, operation in offered:
            evaluation = await self.executor._evaluate(
                context, ProposedOperation(service=service, operation=operation)
            )
            if evaluation.decision.decision == "allow":
                allowed[(service, operation)] = runner
        return allowed

    async def _executions(
        self, offered: dict[tuple[str, str], Any]
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """The latest mitigation.execute attempts per operation, with incident and approver."""
        projector = self.executor.projector
        if projector is None:
            return {}  # Nothing runs without the audit key, so nothing ran.

        def digest(domain: str, value: str) -> str:
            return projector.reference(domain, value).digest

        operations = {
            digest("resource", f"service_operation/{service}:{operation}"): (service, operation)
            for service, operation in offered
        }
        executions: dict[tuple[str, str], list[dict[str, Any]]] = {}
        async with self.sessions() as session:
            events = (
                (
                    await session.execute(
                        text(
                            "SELECT occurred_at, outcome, reason_code,"
                            " resource->'resource_ref'->>'digest' AS operation,"
                            " correlation->'run_ref'->>'digest' AS run"
                            " FROM audit_events WHERE operation='mitigation.execute'"
                            " ORDER BY occurred_at DESC LIMIT :limit"
                        ),
                        {"limit": AUDIT_WINDOW},
                    )
                )
                .mappings()
                .all()
            )
            recent = await session.execute(
                text(
                    "SELECT run_id, incident_id FROM incident.runs"
                    " ORDER BY created_at DESC LIMIT :limit"
                ),
                {"limit": RUN_WINDOW},
            )
            runs = {digest("run_id", run_id): (run_id, incident) for run_id, incident in recent}
            for event in events:
                key = operations.get(event["operation"])
                if key is None:
                    continue
                run_id, incident_id = runs.get(event["run"], (None, None))
                approver = None
                if run_id is not None:
                    # The approval's decision is recorded once the attempt is answered.
                    document = await session.scalar(
                        text(
                            "SELECT document FROM incident.decisions WHERE run_id=:run"
                            " AND document->>'decision_point'='mitigation_approval'"
                            " AND decided_at >= :at ORDER BY decided_at LIMIT 1"
                        ),
                        {"run": run_id, "at": event["occurred_at"]},
                    )
                    reference = actor_reference(document)
                    if reference is not None:
                        approver = {"principal_id": reference["principal_id"],
                                    "display_name": reference.get("display_name")}  # fmt: skip
                executions.setdefault(key, []).append(
                    {
                        "occurred_at": utc_iso(event["occurred_at"]),
                        "outcome": OUTCOMES[event["outcome"]],
                        "reason_code": event["reason_code"],
                        "incident_id": incident_id,
                        "approved_by": approver,
                    }
                )
        return executions


def action_catalog_router(service: ActionCatalogService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/action-catalog")
    async def action_catalog(request: Request) -> JSONResponse:
        return await service.read(request.headers.get("authorization"))

    return router
