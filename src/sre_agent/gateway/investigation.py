"""Dispatch governed investigation runs and persist their bounded results."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from secrets import token_hex
from typing import Any
from uuid import UUID

from sre_agent.governance.dto import PrincipalContext
from sre_agent.incident.persistence import (
    DecisionDraft,
    EventDraft,
    IncidentStaleWriteError,
    IncidentUnitOfWork,
    TransitionResult,
)
from sre_agent.incident.runtime import (
    ActorReference,
    IncidentCommand,
    IncidentRuntime,
    IncidentView,
)
from sre_agent.investigator.client import GatewayClient, GatewaySettings, MCPGatewayClient
from sre_agent.investigator.contract import (
    Conclude,
    IncidentContext,
    InvestigationRequest,
    InvestigationResult,
    ProposeHypothesis,
    ProposeMitigation,
    RequestHuman,
)
from sre_agent.investigator.loop import investigate
from sre_agent.investigator.ports import EvidenceUnavailable
from sre_agent.persistence.repositories import CredentialRepository

UnitOfWorkFactory = Callable[[], IncidentUnitOfWork]


class InvestigationRunDispatcher:
    """Run only the investigation increment through server-owned gateway identity."""

    def __init__(
        self,
        sessions: Any,
        runtime: IncidentRuntime,
        units: UnitOfWorkFactory,
        gateway_settings: GatewaySettings | None,
        *,
        http: Any = None,
    ) -> None:
        self.sessions, self.runtime, self.units = sessions, runtime, units
        self.gateway_settings = gateway_settings
        self.gateway = GatewayClient(gateway_settings, http) if gateway_settings else None
        self.evidence = MCPGatewayClient(gateway_settings, http) if gateway_settings else None

    async def after_start(self, started: TransitionResult) -> None:
        if not any(
            event.kind == "state_change"
            and event.payload.get("transition_id") == "start_investigation"
            for event in started.events
        ):
            return

        principal = await self._configured_agent()
        actor_reference = (
            ActorReference(principal_id=principal.principal.principal_id)
            if principal is not None
            else None
        )
        incident_id, run_id = started.incident.incident_id, started.run.run_id
        now = datetime.now(UTC)
        async with self.units() as work:
            claim = await work.claim_run_dispatch(
                incident_id,
                run_id,
                intent_decision=self._decision(
                    incident_id, run_id, actor_reference, now, "investigation dispatch intent"
                ),
                intent_event=self._receipt_event(
                    incident_id,
                    run_id,
                    actor_reference,
                    phase="intent",
                    status="pending",
                    now=now,
                ),
                interrupted_decision=self._decision(
                    incident_id, run_id, actor_reference, now, "interrupted investigation dispatch"
                ),
                interrupted_event=self._receipt_event(
                    incident_id,
                    run_id,
                    actor_reference,
                    phase="outcome",
                    status="unknown",
                    reason_code="producer_interrupted",
                    now=now,
                ),
            )
            if claim == "active":
                return
            try:
                if claim != "claimed":
                    return
                if self.gateway_settings is None or self.gateway is None or self.evidence is None:
                    await self._finish(
                        work,
                        incident_id,
                        run_id,
                        actor_reference,
                        status="confirmed_failure",
                        reason_code="harness_not_configured",
                    )
                    return
                if principal is None or principal.principal.kind != "agent":
                    await self._finish(
                        work,
                        incident_id,
                        run_id,
                        actor_reference,
                        status="confirmed_failure",
                        reason_code="harness_identity_unavailable",
                    )
                    return
                assert actor_reference is not None
                await self._investigate(work, incident_id, run_id, principal, actor_reference)
            finally:
                await work.release_run_dispatch(incident_id, run_id)

    async def _configured_agent(self) -> PrincipalContext | None:
        if self.gateway_settings is None:
            return None
        async with self.sessions() as session:
            context = await CredentialRepository(session).authenticate(
                self.gateway_settings.api_key.get_secret_value()
            )
        if (
            context is None
            or context.principal.kind != "agent"
            or context.principal.status != "active"
        ):
            return None
        return context

    async def _investigate(
        self,
        work: IncidentUnitOfWork,
        incident_id: str,
        run_id: str,
        principal: PrincipalContext,
        actor_reference: ActorReference,
    ) -> None:
        request_ids: list[UUID] = []
        try:
            view = await self.runtime.current(incident_id, run_id)
            context = IncidentContext.model_validate(view.incident_state)
            assert self.evidence is not None and self.gateway is not None
            capabilities, discovery_id = await self.evidence.discover()
            request_ids.append(discovery_id)
        except EvidenceUnavailable as error:
            if error.request_id is not None:
                request_ids.append(error.request_id)
            status = "confirmed_failure" if error.kind in {"denied", "rejected"} else "unknown"
            await self._finish(
                work,
                incident_id,
                run_id,
                actor_reference,
                status=status,
                reason_code=f"mcp_discovery_{error.kind}",
                request_ids=request_ids,
            )
            return

        try:
            result = await investigate(
                InvestigationRequest(
                    incident_id=incident_id,
                    run_id=run_id,
                    objective="investigate",
                    context=context,
                    authorized_capabilities=capabilities,
                ),
                self.gateway,
                self.evidence,
            )
        except Exception:
            await self._finish(
                work,
                incident_id,
                run_id,
                actor_reference,
                status="unknown",
                reason_code="investigator_failed",
                request_ids=request_ids,
            )
            return

        request_ids.extend(result.request_ids)
        all_request_ids = _unique_ids(request_ids)
        mcp_request_ids = _unique_ids(result.mcp_request_ids)
        if result.status == "denied":
            await self._finish(
                work,
                incident_id,
                run_id,
                actor_reference,
                status="confirmed_failure",
                reason_code="governed_call_denied",
                request_ids=all_request_ids,
                mcp_request_ids=mcp_request_ids,
                result_status=result.status,
                diagnostic=self._result_diagnostic(result),
            )
            return
        if result.status == "pre_dispatch_rejected":
            await self._finish(
                work,
                incident_id,
                run_id,
                actor_reference,
                status="confirmed_failure",
                reason_code="investigation_mcp_contract_rejected",
                request_ids=all_request_ids,
                mcp_request_ids=mcp_request_ids,
                result_status=result.status,
                diagnostic=self._result_diagnostic(result),
            )
            return
        if result.outcome is None or result.status not in {"completed", "needs_human"}:
            await self._finish(
                work,
                incident_id,
                run_id,
                actor_reference,
                status="unknown",
                reason_code=f"investigation_{result.status}",
                request_ids=all_request_ids,
                mcp_request_ids=mcp_request_ids,
                result_status=result.status,
                diagnostic=self._result_diagnostic(result),
            )
            return

        try:
            await self._persist_result(
                work,
                incident_id,
                run_id,
                view,
                view.incident_version,
                principal,
                actor_reference,
                result,
                all_request_ids,
                mcp_request_ids,
            )
        except IncidentStaleWriteError:
            await self._finish(
                work,
                incident_id,
                run_id,
                actor_reference,
                status="unknown",
                reason_code="stale_incident_snapshot",
                request_ids=all_request_ids,
                mcp_request_ids=mcp_request_ids,
                result_status=result.status,
            )
        except Exception:
            await self._finish(
                work,
                incident_id,
                run_id,
                actor_reference,
                status="unknown",
                reason_code="result_persistence_uncertain",
                request_ids=all_request_ids,
                mcp_request_ids=mcp_request_ids,
                result_status=result.status,
            )

    async def _persist_result(
        self,
        work: IncidentUnitOfWork,
        incident_id: str,
        run_id: str,
        view: IncidentView,
        expected_incident_version: int,
        principal: PrincipalContext,
        actor_reference: ActorReference,
        result: InvestigationResult,
        request_ids: Sequence[UUID],
        mcp_request_ids: Sequence[UUID],
    ) -> None:
        assert result.outcome is not None
        now = datetime.now(UTC)
        turn_id = result.turns[-1].turn_id if result.turns else None
        incident_patch = (
            self._hypothesis_patch(
                result.outcome,
                view,
                self._merge_evidence(result, view.incident_state.get("evidence", [])),
            )
            if isinstance(result.outcome, ProposeHypothesis) and result.remaining_step_budget < 1
            else None
        )
        outcome_event = self._result_event(
            incident_id,
            run_id,
            actor_reference,
            result,
            now,
            request_ids,
            turn_id,
            incident_patch=incident_patch,
        )
        receipt_event = self._receipt_event(
            incident_id,
            run_id,
            actor_reference,
            phase="outcome",
            status="success",
            now=now,
            request_ids=request_ids,
            mcp_request_ids=mcp_request_ids,
            turn_id=turn_id,
            result_status=result.status,
        )
        command = self._runtime_command(
            incident_id,
            run_id,
            view,
            expected_incident_version,
            principal,
            result,
            (outcome_event, receipt_event),
        )
        if command is not None:
            await self.runtime.execute(command)
            return
        await work.complete_run_dispatch(
            incident_id,
            run_id,
            decision=self._decision(
                incident_id, run_id, actor_reference, now, "accepted investigation result"
            ),
            events=(outcome_event, receipt_event),
            expected_incident_version=expected_incident_version,
            incident_patch=incident_patch,
        )

    def _runtime_command(
        self,
        incident_id: str,
        run_id: str,
        view: IncidentView,
        expected_incident_version: int,
        principal: PrincipalContext,
        result: InvestigationResult,
        events: Sequence[EventDraft],
    ) -> IncidentCommand | None:
        outcome = result.outcome
        patch: dict[str, Any] = {}
        evidence = self._merge_evidence(result, view.incident_state.get("evidence", []))
        if isinstance(outcome, ProposeHypothesis):
            if result.remaining_step_budget < 1:
                return None
            patch = self._hypothesis_patch(outcome, view, evidence)
            transition_id, transition_outcome = "continue_investigation", "continue_investigation"
            inputs: Mapping[str, Any] = {
                "remaining_step_budget": result.remaining_step_budget,
                "incident_patch": patch,
            }
        elif isinstance(outcome, ProposeMitigation):
            mitigation = {
                "mitigation_id": f"mit_{token_hex(8)}",
                "description": outcome.description,
                "steps": outcome.steps,
                "risk": outcome.risk,
                "verification_check": outcome.verification_check,
                "approval_status": "pending",
                "execution_mode": "simulated",
                "based_on_hypothesis": outcome.based_on_hypothesis,
                "created_by": "agent",
                "created_at": datetime.now(UTC).isoformat(),
            }
            patch = {"mitigation_strategy": mitigation, "evidence": evidence}
            transition_id, transition_outcome = "propose_mitigation", "propose_mitigation"
            inputs = {"incident_patch": patch}
        else:
            return None
        return IncidentCommand(
            command_id=f"investigation-{run_id}",
            incident_id=incident_id,
            run_id=run_id,
            transition_id=transition_id,
            actor="agent",
            actor_reference=ActorReference(principal.principal.principal_id),
            outcome=transition_outcome,
            expected_incident_version=expected_incident_version,
            dispatch_id=run_id,
            turn_id=result.turns[-1].turn_id if result.turns else None,
            inputs=inputs,
            extra_events=tuple(events),
        )

    def _hypothesis_patch(
        self,
        outcome: ProposeHypothesis,
        view: IncidentView,
        evidence: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        hypothesis = {
            "hypothesis_id": f"hyp_{token_hex(8)}",
            "statement": outcome.statement,
            "confidence": outcome.confidence,
            "status": "open",
            "supporting_evidence": outcome.supporting_evidence,
            "created_by": "agent",
            "created_at": datetime.now(UTC).isoformat(),
        }
        return {
            "hypotheses": [*self._existing_hypotheses(view.incident_state), hypothesis],
            "evidence": list(evidence),
        }

    @staticmethod
    def _existing_hypotheses(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        existing = state.get("hypotheses", [])
        return list(existing) if isinstance(existing, list) else []

    @staticmethod
    def _merge_evidence(result: InvestigationResult, existing: Any) -> list[Mapping[str, Any]]:
        merged = list(existing) if isinstance(existing, list) else []
        known = {item.get("evidence_id") for item in merged if isinstance(item, Mapping)}
        for item in result.evidence:
            document = item.model_dump(
                mode="json",
                include={
                    "evidence_id",
                    "source",
                    "tool",
                    "datasource_uid",
                    "query",
                    "time_window",
                    "summary",
                    "collected_at",
                    "request_id",
                },
            )
            if document["evidence_id"] not in known:
                merged.append(document)
                known.add(document["evidence_id"])
        return merged

    async def _finish(
        self,
        work: IncidentUnitOfWork,
        incident_id: str,
        run_id: str,
        actor_reference: ActorReference | None,
        *,
        status: str,
        reason_code: str,
        request_ids: Sequence[UUID] = (),
        mcp_request_ids: Sequence[UUID] = (),
        result_status: str | None = None,
        diagnostic: Mapping[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        await work.complete_run_dispatch(
            incident_id,
            run_id,
            decision=self._decision(
                incident_id, run_id, actor_reference, now, "investigation dispatch outcome"
            ),
            events=(
                self._receipt_event(
                    incident_id,
                    run_id,
                    actor_reference,
                    phase="outcome",
                    status=status,
                    reason_code=reason_code,
                    now=now,
                    request_ids=request_ids,
                    mcp_request_ids=mcp_request_ids,
                    result_status=result_status,
                    diagnostic=diagnostic,
                ),
            ),
        )

    @classmethod
    def _decision(
        cls,
        incident_id: str,
        run_id: str,
        actor_reference: ActorReference | None,
        now: datetime,
        reason: str,
    ) -> DecisionDraft:
        reference = cls._actor_reference(actor_reference)
        return DecisionDraft(
            decision_id=f"dec_{token_hex(8)}",
            document={
                "actor": "agent" if reference else "system",
                "actor_reference": reference,
                "decision_point": "investigation_dispatch",
                "reason": reason,
                "decided_at": now.isoformat(),
            },
            decided_at=now,
            run_id=run_id,
        )

    @classmethod
    def _receipt_event(
        cls,
        incident_id: str,
        run_id: str,
        actor_reference: ActorReference | None,
        *,
        phase: str,
        status: str,
        now: datetime,
        reason_code: str | None = None,
        request_ids: Sequence[UUID] = (),
        mcp_request_ids: Sequence[UUID] = (),
        turn_id: str | None = None,
        result_status: str | None = None,
        diagnostic: Mapping[str, Any] | None = None,
    ) -> EventDraft:
        receipt: dict[str, Any] = {
            "dispatch_id": run_id,
            "phase": phase,
            "status": status,
            "request_ids": [str(item) for item in _unique_ids(request_ids)],
            "mcp_request_ids": [str(item) for item in _unique_ids(mcp_request_ids)],
        }
        if reason_code:
            receipt["reason_code"] = reason_code
        if result_status:
            receipt["result_status"] = result_status
        if diagnostic is not None:
            receipt["diagnostic"] = dict(diagnostic)
        return EventDraft(
            event_id=f"evt_{token_hex(8)}",
            kind="dispatch_receipt",
            payload={
                "state": "investigating",
                "dispatch_receipt": receipt,
                "request_id": str(request_ids[-1]) if request_ids else None,
            },
            occurred_at=now,
            turn_id=turn_id,
        )

    @staticmethod
    def _result_diagnostic(result: InvestigationResult) -> dict[str, Any] | None:
        failure = result.failure_diagnostic
        if failure is None:
            return None
        return {
            "stage": failure.stage,
            "kind": failure.kind,
            "http_status": failure.http_status,
            "request_id": str(failure.request_id) if failure.request_id else None,
            "turn_count": len(result.turns),
            "collected_evidence_count": len(result.evidence),
        }

    @classmethod
    def _result_event(
        cls,
        incident_id: str,
        run_id: str,
        actor_reference: ActorReference,
        result: InvestigationResult,
        now: datetime,
        request_ids: Sequence[UUID],
        turn_id: str | None,
        incident_patch: Mapping[str, Any] | None = None,
    ) -> EventDraft:
        assert result.outcome is not None
        action = result.outcome.action
        outcome: dict[str, Any] = {
            "action": action,
            "evidence_ids": [item.evidence_id for item in result.evidence],
        }
        if isinstance(result.outcome, ProposeHypothesis):
            outcome["statement"] = result.outcome.statement
            outcome["confidence"] = result.outcome.confidence
            outcome["supporting_evidence"] = result.outcome.supporting_evidence
        elif isinstance(result.outcome, ProposeMitigation):
            outcome["based_on_hypothesis"] = result.outcome.based_on_hypothesis
        elif isinstance(result.outcome, Conclude):
            outcome["summary"] = result.outcome.summary
            outcome["supporting_evidence"] = result.outcome.supporting_evidence
        elif isinstance(result.outcome, RequestHuman):
            outcome["reason"] = result.outcome.reason
        return EventDraft(
            event_id=f"evt_{token_hex(8)}",
            kind="investigation_result",
            payload={
                "state": "investigating",
                "outcome": outcome,
                **({"incident_patch": incident_patch} if incident_patch is not None else {}),
                "evidence_references": [
                    {
                        "evidence_id": item.evidence_id,
                        "source": item.source,
                        "tool": item.tool,
                        "datasource_uid": item.datasource_uid,
                        "query": item.query,
                        "time_window": item.time_window,
                        "summary": item.summary,
                        "request_id": str(item.request_id) if item.request_id else None,
                    }
                    for item in result.evidence
                ],
                "request_id": str(result.turns[-1].request_id)
                if result.turns and result.turns[-1].request_id
                else (str(request_ids[-1]) if request_ids else None),
            },
            occurred_at=now,
            turn_id=turn_id,
        )

    @staticmethod
    def _actor_reference(actor: ActorReference | None) -> dict[str, Any] | None:
        if actor is None:
            return None
        return {
            "reference_version": actor.reference_version,
            "principal_id": actor.principal_id,
        }


def _unique_ids(values: Sequence[UUID]) -> list[UUID]:
    return list(dict.fromkeys(values))
