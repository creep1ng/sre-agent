"""GET .../runs/{run_id}/context: what a run sent to the model, the replies and the tool
arguments (issue #39, audit finding C07), plus the reasoning the incident recorded from them
(hypotheses, evidence, mitigation). It is not a safe projection: its own action,
run.read_context, guards it, so watching a run with run.read is not reading it."""

from collections.abc import Mapping, Sequence
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
# The allow-listed subset of the incident-state artifacts the reasoning carries.
HYPOTHESIS_FIELDS = (
    "hypothesis_id", "statement", "confidence", "status", "supporting_evidence",
    "contradicting_evidence", "next_check", "created_by", "created_at",
)  # fmt: skip
EVIDENCE_FIELDS = (
    "evidence_id", "source", "tool", "datasource_uid", "query", "time_window", "summary",
    "collected_at", "request_id",
)  # fmt: skip
MITIGATION_FIELDS = (
    "mitigation_id", "description", "steps", "risk", "expected_effect", "verification_check",
    "approval_status", "execution_mode", "based_on_hypothesis", "created_by", "created_at",
)  # fmt: skip


def _allowed(item: Any, fields: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    return {field: item[field] for field in fields if field in item}


def project_reasoning(incident_state: Any) -> dict[str, Any]:
    """The incident's recorded reasoning: only allow-listed fields, explicit when empty."""
    state = incident_state if isinstance(incident_state, Mapping) else {}

    def listed(key: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        values = state.get(key)
        items = values if isinstance(values, list) else []
        return [kept for kept in (_allowed(item, fields) for item in items) if kept is not None]

    return {
        "hypotheses": listed("hypotheses", HYPOTHESIS_FIELDS),
        "evidence": listed("evidence", EVIDENCE_FIELDS),
        "mitigation_strategy": _allowed(state.get("mitigation_strategy"), MITIGATION_FIELDS),
    }


def project_run_context(
    incident_id: str,
    run_id: str,
    contexts: Sequence[TextContextRecord],
    retrieved_at: datetime,
    incident_state: Any = None,
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
        "reasoning": project_reasoning(incident_state),
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
                # Read after the run check, in the same unit: the reasoning is current.
                incident = await work.incidents.get(incident_id)
            payload = project_run_context(
                incident_id,
                run_id,
                contexts,
                datetime.now(UTC),
                incident.state if incident is not None else None,
            )
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
