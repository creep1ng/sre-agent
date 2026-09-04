import hmac  # noqa: I001
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sre_agent.governance.authorization import AuthorizationDenialCause
from sre_agent.governance.dto import AuditEvent, AuditRef, ModelAlias, PolicyDecision, PrincipalContext  # noqa: E501  # fmt: skip


class AuditProjector:
    def __init__(self, key: bytes, key_version: int = 1) -> None:
        self._key, self._version = key, key_version

    def reference(self, domain: str, value: str) -> AuditRef:
        data = f"sre-audit-v1\0{domain}\0{value}".encode()
        return AuditRef(
            algorithm="hmac-sha-256",
            key_version=self._version,
            digest=hmac.new(self._key, data, sha256).hexdigest(),
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
    ) -> AuditEvent:
        """Project a metadata-only administrative control-plane event.

        Control operations never carry LLM routing evidence; identity and
        resource are HMAC references only, per ADR-005 domain separation.
        """
        ref = self.reference
        identity = None
        if context:
            identity = {
                "principal_ref": ref("principal", context.principal.principal_id),
                "principal_kind": context.principal.kind,
                "principal_status": context.principal.status,
                "credential_ref": ref("credential", context.credential_id),
                "authenticated_at": context.authenticated_at,
            }
        policy = None
        if decision:
            policy = {"decision": decision.decision, "reason_code": decision.reason_code}
            if decision.policy_id:
                policy["grant_ref"] = ref("grant", decision.policy_id)
        resource = None
        if resource_ref is not None:
            resource = {
                "resource_type": resource_ref[0],
                "resource_ref": ref("resource", f"{resource_ref[0]}/{resource_ref[1]}"),
            }
        # fmt: off
        audit_decision = None
        if decision is not None:
            if decision.decision == "allow":
                if decision.policy_id is None:
                    raise ValueError("control allow requires a grant policy_id")
                audit_decision = {
                    "decision": "allow", "reason_code": "grant_matched",
                    "grant_ref": ref("grant", decision.policy_id),
                }
            else:
                audit_decision = {"decision": "deny", "reason_code": "no_matching_grant"}
        cause = (
            authorization_denial_cause
            if stage == "authorization" and status == 403 and audit_decision is not None
            and audit_decision["decision"] == "deny"
            else None
        )
        return AuditEvent(
            event_id=uuid4(), occurred_at=datetime.now(UTC), operation=operation,
            action=action, stage=stage, outcome="success" if status < 400 else
            ("denied" if status in {403, 404} else "error"), reason_code=reason,
            authorization_denial_cause=cause,
            response_status=status, retryable=retryable, latency_ms=latency_ms,
            correlation={"request_id": request_id}, identity=identity,
            resource=resource, policy_decision=audit_decision,
            redaction={"policy_version": "redaction-1.0.0", "result": "success",
                       "source_class": "none", "categories": [], "match_count": 0,
                       "sink_eligible": False},
            content_state="absent", authoritative_acceptance="accepted",
            ordinary_result="released", exporter_result="not_attempted",
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
    ) -> AuditEvent:
        ref = self.reference
        correlation = {"request_id": request_id}
        for name, value in (identifiers or {}).items():
            correlation[f"{name}_ref"] = ref(name, value)
        identity = None
        if context:
            identity = {
                "principal_ref": ref("principal", context.principal.principal_id),
                "principal_kind": context.principal.kind,
                "principal_status": context.principal.status,
                "credential_ref": ref("credential", context.credential_id),
                "authenticated_at": context.authenticated_at,
            }
        policy = None
        if decision:
            policy = {"decision": decision.decision, "reason_code": decision.reason_code}
            if decision.policy_id:
                policy["grant_ref"] = ref("grant", decision.policy_id)
        # fmt: off
        return AuditEvent(
            event_id=uuid4(), occurred_at=datetime.now(UTC), operation="responses.create",
            action="invoke", stage=stage, outcome="success" if status < 400 else
            ("denied" if status == 403 else "error"), reason_code=reason,
            authorization_denial_cause=authorization_denial_cause,
            response_status=status, retryable=retryable, latency_ms=latency_ms,
            correlation=correlation, identity=identity,
            resource={"resource_type": "llm_model", "resource_ref": ref("resource", alias)}
            if context and alias else None,
            model_alias_ref=ref("model_alias", alias) if context and alias else None,
            policy_decision=policy,
            routing={"model_ref": ref("model", assignment.concrete_model),
                     "router": "openrouter",
                     "provider_ref": ref("provider", assignment.inference_provider)}
            if assignment else None,
            redaction={"policy_version": "redaction-1.0.0", "result": "success",
                       "source_class": "none", "categories": [], "match_count": 0,
                       "sink_eligible": False},
            content_state="absent", authoritative_acceptance="accepted",
            ordinary_result="released", exporter_result="not_attempted",
        )
