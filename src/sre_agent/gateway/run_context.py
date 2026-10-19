"""GET .../runs/{run_id}/context: what a run sent to the model, the replies and the tool
arguments (issue #39, audit finding C07). It is not a safe projection: its own action,
run.read_context, guards it, so watching a run with run.read is not reading it."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from sre_agent.gateway.incidents import (
    WORKFLOW_RESOURCE_TYPE,
    IncidentQueryService,
    IncidentWorkflowResourceReader,
)
from sre_agent.governance.authorization import AuthorizationDecisionEngine, AuthorizationEvaluation
from sre_agent.governance.dto import Principal
from sre_agent.incident.persistence import TextContextRecord
from sre_agent.incident.projections import IDENTIFIER_PATTERN, RUN_ID_PATTERN, utc_iso
from sre_agent.persistence.repositories import GrantRepository

CONTEXT_ACTION = "run.read_context"
TURN_FIELDS = ("assembled_input", "model_output", "tool_invocation", "request_id")


def project_run_context(
    incident_id: str, run_id: str, contexts: Sequence[TextContextRecord], retrieved_at: datetime
) -> dict[str, Any]:
    """run-context:1.0.0: each turn carries the schema's fields and nothing else."""
    turns = [
        {
            "turn_id": context.turn_id,
            "task_id": context.task_id,
            "sequence": context.sequence,
            **{field: context.content.get(field) for field in TURN_FIELDS},
            "occurred_at": utc_iso(context.occurred_at),
        }
        for context in contexts
    ]
    return {
        "run_id": run_id,
        "incident_id": incident_id,
        "turns": turns,
        "retrieved_at": utc_iso(retrieved_at),
    }


class RunContextService(IncidentQueryService):
    """The incident reads' authentication, errors and membership, with their own action."""

    async def _default_authorizer(
        self, session: Any, principal: Principal
    ) -> AuthorizationEvaluation:
        engine = AuthorizationDecisionEngine(
            IncidentWorkflowResourceReader(self.workflow), GrantRepository(session)
        )
        return await engine.evaluate(
            principal, CONTEXT_ACTION, WORKFLOW_RESOURCE_TYPE, self.workflow.workflow_id
        )

    async def get_run_context(
        self, incident_id: str, run_id: str, authorization: str | None
    ) -> JSONResponse:
        request_id = uuid4()
        if not self._valid_identifier(incident_id, IDENTIFIER_PATTERN):
            return self._error(request_id, 422)
        if not self._valid_identifier(run_id, RUN_ID_PATTERN):
            return self._error(request_id, 422)
        _, error = await self._authorized_principal(request_id, authorization)
        if error is not None:
            return error
        _, error = await self._incident_or_error(request_id, incident_id)
        if error is not None:
            return error
        try:
            async with self.units() as work:
                if await work.runs.get_for_incident(run_id, incident_id) is None:
                    return self._error(request_id, 404, "run_not_found")
                contexts = await work.text_context.list(run_id)
            payload = project_run_context(incident_id, run_id, contexts, datetime.now(UTC))
        except Exception:
            return self._error(request_id, 503)
        # Prompts and tool arguments never stay in a browser or proxy cache.
        return JSONResponse(payload, status_code=200, headers={"Cache-Control": "no-store"})


def run_context_router(service: RunContextService) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/incidents/{incident_id}/runs/{run_id}/context")
    async def run_context(incident_id: str, run_id: str, request: Request) -> JSONResponse:
        return await service.get_run_context(
            incident_id, run_id, request.headers.get("authorization")
        )

    return router
