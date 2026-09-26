from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from sre_agent import _core
from sre_agent.governance.authorization import AuthorizationDenialCause
from sre_agent.governance.dto import (
    AuditEvent,
    AuditRef,
    Consumption,
    ModelAlias,
    PolicyDecision,
    PrincipalContext,
)  # noqa: E501

_RESPONSE_STATUS: TypeAdapter[int] = TypeAdapter(
    Annotated[int, *AuditEvent.model_fields["response_status"].metadata]
)


class AuditProjector:
    def __init__(self, key: bytes, key_version: int = 1) -> None:
        self._key, self._version = key, key_version

    def reference(self, domain: str, value: str) -> AuditRef:
        return AuditRef(
            algorithm="hmac-sha-256",
            key_version=self._version,
            digest=_core.audit_reference_digest(self._key, domain, value),
        )

    @staticmethod
    def control_plan(
        status: int,
        stage: str,
        reason: str | None,
        terminal: bool,
        retryable: bool,
        context: PrincipalContext | None,
        resource_ref: tuple[str, str] | None,
        decision: PolicyDecision | None,
        authorization_denial_cause: AuthorizationDenialCause | None,
    ) -> dict:
        """Pass control facts to the sole native terminal-audit authority."""
        status = _RESPONSE_STATUS.validate_python(status, strict=True)
        return _core.project_control_audit(
            status,
            stage,
            reason,
            terminal,
            retryable,
            context,
            resource_ref,
            decision,
            authorization_denial_cause,
        )

    def control_event(
        self,
        request_id: UUID,
        status: int,
        latency_ms: int,
        stage: str,
        *,
        operation: str,
        action: str,
        reason: str | None = None,
        retryable: bool = False,
        context: PrincipalContext | None = None,
        resource_ref: tuple[str, str] | None = None,
        decision: PolicyDecision | None = None,
        authorization_denial_cause: AuthorizationDenialCause | None = None,
        _projection: dict | None = None,
    ) -> AuditEvent:
        """Project a metadata-only administrative control-plane event.

        Control operations never carry LLM routing evidence; identity and
        resource are HMAC references only, per ADR-005 domain separation.
        """
        projection = (
            _projection
            if _projection is not None
            else self.control_plan(
                status,
                stage,
                reason,
                False,
                retryable,
                context,
                resource_ref,
                decision,
                authorization_denial_cause,
            )
        )

        def resolve_fields(fields: dict | None) -> dict | None:
            if fields is None:
                return None
            return {
                name: self.reference(*value) if name.endswith("_ref") else value
                for name, value in fields.items()
            }

        identity = resolve_fields(projection["identity"])
        if identity is not None:
            identity["authenticated_at"] = context.authenticated_at
        return AuditEvent(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            operation=operation,
            action=action,
            stage=projection["stage"],
            outcome=projection["outcome"],
            reason_code=projection["reason"],
            authorization_denial_cause=projection["authorization_denial_cause"],
            response_status=status,
            retryable=projection["retryable"],
            latency_ms=latency_ms,
            correlation={"request_id": request_id},
            identity=identity,
            resource=resolve_fields(projection["resource"]),
            policy_decision=resolve_fields(projection["policy_decision"]),
            routing=projection["routing"],
            redaction={
                "policy_version": "redaction-1.0.0",
                "result": "success",
                "source_class": "none",
                "categories": [],
                "match_count": 0,
                "sink_eligible": False,
            },
            content_state="absent",
            authoritative_acceptance="accepted",
            ordinary_result="released",
            exporter_result="not_attempted",
        )

    def event(
        self,
        request_id: UUID,
        status: int,
        latency_ms: int,
        stage: str,
        *,
        reason: str | None = None,
        retryable: bool = False,
        context: PrincipalContext | None = None,
        alias: str | None = None,
        decision: PolicyDecision | None = None,
        authorization_denial_cause: AuthorizationDenialCause | None = None,
        assignment: ModelAlias | None = None,
        identifiers: dict[str, str] | None = None,
        consumption: Consumption | None = None,
    ) -> AuditEvent:
        status = _RESPONSE_STATUS.validate_python(status, strict=True)
        projection = _core.project_responses_audit(
            status,
            reason,
            (
                context.principal.principal_id,
                context.principal.kind,
                context.principal.status,
                context.credential_id,
            )
            if context
            else None,
            alias,
            (decision.decision, decision.reason_code, decision.policy_id) if decision else None,
            (assignment.concrete_model, assignment.inference_provider) if assignment else None,
            list((identifiers or {}).items()),
        )

        def resolve_fields(fields: dict | None) -> dict | None:
            if fields is None:
                return None
            return {
                name: self.reference(*value) if name.endswith("_ref") else value
                for name, value in fields.items()
            }

        projection["correlation"] = {
            "request_id": request_id,
            **{
                name: self.reference(domain, value)
                for name, domain, value in projection.pop("correlation_refs")
            },
        }
        for field in ("identity", "resource", "policy_decision", "routing"):
            projection[field] = resolve_fields(projection[field])
        if projection["identity"] is not None:
            projection["identity"]["authenticated_at"] = context.authenticated_at
        if projection["model_alias_ref"] is not None:
            projection["model_alias_ref"] = self.reference(*projection["model_alias_ref"])

        return AuditEvent(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            stage=stage,
            reason_code=reason,
            authorization_denial_cause=authorization_denial_cause,
            response_status=status,
            retryable=retryable,
            latency_ms=latency_ms,
            consumption=consumption,
            **projection,
        )
