"""Strict Pydantic projections of the authoritative HT-01 contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")]
ResourceType = Literal["llm_model", "mcp_server", "mcp_tool", "skill", "bok_collection"]
AuditRefValue = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ReasonCode = Literal[
    "audit_unavailable",
    "authentication_failed",
    "contract_validation_failed",
    "grant_matched",
    "no_matching_grant",
    "redaction_failed",
    "redaction_uncertain",
    "routing_unavailable",
    "upstream_failed",
    "upstream_invalid",
    "upstream_unavailable",
]


class StrictDTO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Principal(StrictDTO):
    principal_id: Identifier
    kind: Literal["human", "agent"]
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    status: Literal["active", "inactive"]
    created_at: AwareDatetime
    updated_at: AwareDatetime


class CredentialReference(StrictDTO):
    credential_id: Identifier
    principal_id: Identifier
    prefix: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{4,16}$")]
    status: Literal["active", "revoked"]
    created_at: AwareDatetime
    expires_at: AwareDatetime | None
    revoked_at: AwareDatetime | None


class PrincipalContext(StrictDTO):
    principal: Principal
    credential_id: Identifier
    authenticated_at: AwareDatetime


class Resource(StrictDTO):
    resource_type: ResourceType
    resource_id: Annotated[str, Field(min_length=1, max_length=200)]


class ModelAlias(StrictDTO):
    model_alias_id: Identifier
    alias: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    concrete_model: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$")]
    router: Annotated[str, Field(min_length=1, max_length=100)]
    inference_provider: Annotated[str, Field(min_length=1, max_length=100)]
    status: Literal["active", "inactive"]


class Grant(StrictDTO):
    grant_id: Identifier
    principal_id: Identifier
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{1,63}$")]
    resource: Resource
    effect: Literal["allow"]
    status: Literal["active", "revoked"]
    created_at: AwareDatetime


class PolicyDecision(StrictDTO):
    decision: Literal["allow", "deny"]
    reason_code: Literal["grant_matched", "no_matching_grant"]
    policy_id: str | None

    @model_validator(mode="after")
    def validate_outcome(self) -> "PolicyDecision":
        valid_allow = self.reason_code == "grant_matched" and bool(self.policy_id)
        valid_deny = self.reason_code == "no_matching_grant" and self.policy_id is None
        if (self.decision == "allow" and not valid_allow) or (
            self.decision == "deny" and not valid_deny
        ):
            raise ValueError("policy decision fields are inconsistent")
        return self


class AuditRef(StrictDTO):
    algorithm: Literal["hmac-sha-256"]
    key_version: Annotated[int, Field(ge=1, le=2_147_483_647)]
    digest: AuditRefValue


class Correlation(StrictDTO):
    request_id: UUID
    incident_ref: AuditRef | None = None
    run_ref: AuditRef | None = None
    task_ref: AuditRef | None = None
    trace_ref: AuditRef | None = None


class AuthenticatedIdentity(StrictDTO):
    principal_ref: AuditRef
    principal_kind: Literal["human", "agent"]
    principal_status: Literal["active", "inactive"]
    credential_ref: AuditRef
    authenticated_at: AwareDatetime


class PartialPrincipalIdentity(StrictDTO):
    principal_ref: AuditRef
    principal_kind: Literal["human", "agent"]
    principal_status: Literal["active", "inactive"]
    credential_ref: AuditRef | None = None


class CredentialOnlyIdentity(StrictDTO):
    credential_ref: AuditRef


class ResourceEvidence(StrictDTO):
    resource_type: ResourceType
    resource_ref: AuditRef


class RoutingEvidence(StrictDTO):
    model_ref: AuditRef
    router: Literal["openrouter"]
    provider_ref: AuditRef


class AllowDecisionEvidence(StrictDTO):
    decision: Literal["allow"]
    reason_code: Literal["grant_matched"]
    policy_ref: AuditRef | None = None
    grant_ref: AuditRef


class DenyDecisionEvidence(StrictDTO):
    decision: Literal["deny"]
    reason_code: Literal["no_matching_grant"]


class UntrustedIdentifier(StrictDTO):
    kind: Literal["incident", "model_alias", "resource", "run", "task", "trace"]
    ref: AuditRef


class UntrustedInput(StrictDTO):
    trust: Literal["untrusted"]
    identifiers: Annotated[list[UntrustedIdentifier], Field(max_length=8)]


class Redaction(StrictDTO):
    policy_version: Literal["redaction-1.0.0"]
    result: Literal["success", "failed"]
    source_class: Literal[
        "none",
        "llm_input",
        "llm_response",
        "mcp_log",
        "sandbox_output",
        "command_output",
        "tool_arguments",
        "tool_result",
        "free_content",
    ]
    categories: Annotated[
        list[
            Literal[
                "credential",
                "personal_data",
                "provider_secret",
                "configured_pattern",
                "unsafe_structure",
                "uncertain",
            ]
        ],
        Field(max_length=8),
    ]
    match_count: Annotated[int, Field(ge=0, le=10_000)]
    sink_eligible: bool
    tool_schema_version: Literal["1.0.0"] | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "Redaction":
        absent = self.source_class == "none"
        if absent != (
            self.result == "success"
            and not self.categories
            and self.match_count == 0
            and not self.sink_eligible
        ):
            raise ValueError("redaction fields are inconsistent")
        if not absent and self.sink_eligible != (self.result == "success"):
            raise ValueError("redaction eligibility is inconsistent")
        return self


class FullyRedacted(StrictDTO):
    representation: Literal["fully_redacted"]


class SanitizedText(StrictDTO):
    representation: Literal["sanitized_text"]
    text: Annotated[str, Field(min_length=1, max_length=65_536)]


class AuditEvent(StrictDTO):
    event_id: (
        UUID
        | Annotated[
            str,
            Field(
                pattern=(
                    r"^cor_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
                    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
                )
            ),
        ]
    )
    occurred_at: AwareDatetime
    operation: Literal[
        "audit.accept",
        "audit.export",
        "audit.project",
        "audit.redact",
        "credentials.authenticate",
        "responses.create",
    ]
    action: Literal["authenticate", "export", "invoke", "persist", "read_metadata", "redact"]
    stage: Literal[
        "validation",
        "authentication",
        "authorization",
        "routing",
        "upstream",
        "response",
        "audit",
    ]
    outcome: Literal["success", "denied", "error"]
    reason_code: ReasonCode | None
    response_status: Annotated[int, Field(ge=100, le=599)]
    retryable: bool
    correlation: Correlation
    identity: AuthenticatedIdentity | PartialPrincipalIdentity | CredentialOnlyIdentity | None = (
        None
    )
    resource: ResourceEvidence | None = None
    model_alias_ref: AuditRef | None = None
    policy_decision: AllowDecisionEvidence | DenyDecisionEvidence | None = None
    routing: RoutingEvidence | None = None
    untrusted_input: UntrustedInput | None = None
    redaction: Redaction
    content_state: Literal["absent", "redacted", "redaction_failed"]
    redacted_content: FullyRedacted | SanitizedText | None = None
    authoritative_acceptance: Literal["accepted", "rejected"]
    ordinary_result: Literal["released", "suppressed"]
    exporter_result: Literal["not_attempted", "succeeded", "failed"]
    correction_of_event_id: UUID | None = None

    @model_validator(mode="after")
    def validate_contract_relationships(self) -> "AuditEvent":
        no_subject = self.stage in {"validation", "audit"}
        subject = (self.identity, self.resource, self.model_alias_ref, self.policy_decision)
        if no_subject and any(value is not None for value in (*subject, self.routing)):
            raise ValueError("this audit stage cannot carry subject evidence")
        if self.stage in {"authorization", "routing", "upstream", "response"} and any(
            value is None for value in subject[:3]
        ):
            raise ValueError("this audit stage requires identity and resource evidence")
        expected_redaction = {"absent": "none", "redacted": "success", "redaction_failed": "failed"}
        actual_redaction = (
            self.redaction.source_class if self.content_state == "absent" else self.redaction.result
        )
        if actual_redaction != expected_redaction[self.content_state]:
            raise ValueError("content and redaction states are inconsistent")
        if isinstance(self.redacted_content, SanitizedText) and self.redaction.source_class not in {
            "llm_input",
            "llm_response",
        }:
            raise ValueError("sanitized text is limited to LLM content")
        if self.authoritative_acceptance == "rejected" and (
            self.reason_code != "audit_unavailable" or self.ordinary_result != "suppressed"
        ):
            raise ValueError("rejected audit events must fail closed")
        return self
