from functools import partial

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import CheckConstraint as CK
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.sql.schema import ForeignKeyConstraint, UniqueConstraint

required = partial(mapped_column, nullable=False)


class Base(DeclarativeBase):
    pass


class PrincipalRow(Base):
    __tablename__ = "principals"
    __table_args__ = (
        CK("kind IN ('human','agent')", name="ck_principals_kind"),
        CK("status IN ('active','inactive')", name="ck_principals_status"),
        CK("updated_at >= created_at", name="ck_principals_lifecycle"),
    )
    principal_id = mapped_column(String(64), primary_key=True)
    kind = required(String(16))
    display_name = required(String(200))
    status = required(String(16))
    created_at = required(DateTime(timezone=True))
    updated_at = required(DateTime(timezone=True))


class CredentialRow(Base):
    __tablename__ = "credentials"
    __table_args__ = (
        CK("status IN ('active','revoked')", name="ck_credentials_status"),
        CK(
            "(status='active' AND revoked_at IS NULL) OR "
            "(status='revoked' AND revoked_at IS NOT NULL AND revoked_at >= created_at)",
            name="ck_credentials_lifecycle",
        ),
        CK("expires_at IS NULL OR expires_at > created_at", name="ck_credentials_expiry"),
        UniqueConstraint("prefix", name="uq_credentials_prefix"),
    )
    credential_id = mapped_column(String(64), primary_key=True)
    principal_id = required(String(64), ForeignKey("principals.principal_id"))
    prefix = required(String(16))
    key_hash = required(String(512))
    status = required(String(16))
    created_at = required(DateTime(timezone=True))
    expires_at = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at = mapped_column(DateTime(timezone=True), nullable=True)


class ResourceRow(Base):
    __tablename__ = "resources"
    __table_args__ = (
        CK(
            "resource_type IN ('llm_model','mcp_server','mcp_tool','skill','bok_collection',"
            "'administrative_control')",
            name="ck_resources_type",
        ),
        CK("status IN ('active','inactive')", name="ck_resources_status"),
        CK(
            "(resource_type='llm_model' AND model_alias_id IS NOT NULL AND alias IS NOT NULL "
            "AND concrete_model IS NOT NULL AND router='openrouter' "
            "AND inference_provider IS NOT NULL) OR (resource_type<>'llm_model' "
            "AND model_alias_id IS NULL AND alias IS NULL AND concrete_model IS NULL "
            "AND router IS NULL AND inference_provider IS NULL)",
            name="ck_resources_llm_assignment",
        ),
        UniqueConstraint("model_alias_id", name="uq_resources_model_alias_id"),
        UniqueConstraint("alias", name="uq_resources_alias"),
    )
    resource_type = mapped_column(String(32), primary_key=True)
    resource_id = mapped_column(String(200), primary_key=True)
    status = required(String(16))
    model_alias_id = mapped_column(String(64), nullable=True)
    alias = mapped_column(String(64), nullable=True)
    concrete_model = mapped_column(String(200), nullable=True)
    router = mapped_column(String(100), nullable=True)
    inference_provider = mapped_column(String(100), nullable=True)


class GrantRow(Base):
    __tablename__ = "grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["resource_type", "resource_id"],
            ["resources.resource_type", "resources.resource_id"],
        ),
        CK("effect='allow'", name="ck_grants_effect"),
        CK("status IN ('active','revoked')", name="ck_grants_status"),
        UniqueConstraint(
            "principal_id", "action", "resource_type", "resource_id", name="uq_grants_direct"
        ),
    )
    grant_id = mapped_column(String(64), primary_key=True)
    principal_id = required(String(64), ForeignKey("principals.principal_id"))
    action = required(String(64))
    resource_type = required(String(32))
    resource_id = required(String(200))
    effect = required(String(16))
    status = required(String(16))
    created_at = required(DateTime(timezone=True))


class IdempotencyRecordRow(Base):
    """Scoped POST binding: replay on same hash, conflict on different hash."""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        CK("method = 'POST'", name="ck_idempotency_method"),
        CK(
            "binding IN ('at_least_24h','principal_lifetime')",
            name="ck_idempotency_binding",
        ),
        CK("transition_count = 1", name="ck_idempotency_transitions"),
    )
    scope = mapped_column(String(320), primary_key=True)
    key_digest = mapped_column(String(64), primary_key=True)
    payload_sha256 = required(String(64))
    principal_id = required(String(64))
    method = required(String(16))
    canonical_path = required(String(200))
    binding = required(String(32))
    outcome = required(JSONB)
    created_at = required(DateTime(timezone=True))
    expires_at = mapped_column(DateTime(timezone=True), nullable=True)
    transition_count = required(Integer)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CK(
            "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
            "'credentials.authenticate','responses.create','principals.create',"
            "'principals.get','principals.list','principals.status.replace',"
            "'credentials.issue','credentials.list','credentials.revoke','credentials.rotate')",
            name="ck_audit_events_operation",
        ),
        CK(
            "action IN ('authenticate','export','invoke','persist','read_metadata','redact',"
            "'admin.read','admin.write')",
            name="ck_audit_events_action",
        ),
        CK(
            "stage IN ('validation','authentication','authorization','routing','upstream',"
            "'response','audit')",
            name="ck_audit_events_stage",
        ),
        CK("outcome IN ('success','denied','error')", name="ck_audit_events_outcome"),
        CK(
            "reason_code IS NULL OR reason_code IN ('audit_unavailable','authentication_failed',"
            "'contract_validation_failed','grant_matched','no_matching_grant','redaction_failed',"
            "'redaction_uncertain','routing_unavailable','upstream_failed','upstream_invalid',"
            "'upstream_unavailable')",
            name="ck_audit_events_reason_code",
        ),
        CK(
            "authorization_denial_cause IS NULL OR (authorization_denial_cause IN "
            "('principal_inactive','resource_missing','resource_inactive','grant_not_applicable') "
            "AND stage='authorization' AND outcome='denied' "
            "AND reason_code='no_matching_grant' AND response_status=403)",
            name="ck_audit_events_authorization_denial_cause",
        ),
        CK("response_status BETWEEN 100 AND 599", name="ck_audit_events_response"),
        CK("latency_ms >= 0", name="ck_audit_events_latency"),
        CK(
            "content_state IN ('absent','redacted','redaction_failed')",
            name="ck_audit_events_content_state",
        ),
        CK(
            "authoritative_acceptance IN ('accepted','rejected')", name="ck_audit_events_acceptance"
        ),
        CK("ordinary_result IN ('released','suppressed')", name="ck_audit_events_result"),
        CK(
            "exporter_result IN ('not_attempted','succeeded','failed')",
            name="ck_audit_events_exporter",
        ),
    )
    event_id = mapped_column(String(40), primary_key=True)
    occurred_at = required(DateTime(timezone=True))
    operation = required(String(32))
    action = required(String(32))
    stage = required(String(32))
    outcome = required(String(16))
    reason_code = mapped_column(String(64), nullable=True)
    authorization_denial_cause = mapped_column(String(32), nullable=True)
    response_status = required(Integer)
    retryable = required(Boolean)
    latency_ms = required(Integer)
    correlation = required(JSONB)
    identity = mapped_column(JSONB, nullable=True)
    resource = mapped_column(JSONB, nullable=True)
    model_alias_ref = mapped_column(JSONB, nullable=True)
    policy_decision = mapped_column(JSONB, nullable=True)
    routing = mapped_column(JSONB, nullable=True)
    untrusted_input = mapped_column(JSONB, nullable=True)
    redaction = required(JSONB)
    content_state = required(String(32))
    redacted_content = mapped_column(JSONB, nullable=True)
    authoritative_acceptance = required(String(16))
    ordinary_result = required(String(16))
    exporter_result = required(String(16))
    correction_of_event_id = mapped_column(String(40), nullable=True)
