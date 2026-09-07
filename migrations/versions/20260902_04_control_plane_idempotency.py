"""Widen control resources and audit vocabulary for administrative control plane."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902_04"
down_revision = "20260901_03"
branch_labels = None
depends_on = None

OLD_RESOURCES_TYPE = (
    "resource_type IN ('llm_model','mcp_server','mcp_tool','skill','bok_collection')"
)
NEW_RESOURCES_TYPE = (
    "resource_type IN ('llm_model','mcp_server','mcp_tool','skill','bok_collection',"
    "'administrative_control')"
)
OLD_AUDIT_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create')"
)
NEW_AUDIT_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'principals.get','principals.list','principals.status.replace',"
    "'credentials.issue','credentials.list','credentials.revoke','credentials.rotate')"
)
OLD_AUDIT_ACTION = "action IN ('authenticate','export','invoke','persist','read_metadata','redact')"
NEW_AUDIT_ACTION = (
    "action IN ('authenticate','export','invoke','persist','read_metadata','redact',"
    "'admin.read','admin.write')"
)


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("scope", sa.String(320), nullable=False),
        sa.Column("key_digest", sa.String(64), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("canonical_path", sa.String(200), nullable=False),
        sa.Column("binding", sa.String(32), nullable=False),
        sa.Column(
            "outcome",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transition_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("method = 'POST'", name="ck_idempotency_method"),
        sa.CheckConstraint(
            "binding IN ('at_least_24h','principal_lifetime')",
            name="ck_idempotency_binding",
        ),
        sa.CheckConstraint("transition_count = 1", name="ck_idempotency_transitions"),
        sa.PrimaryKeyConstraint("scope", "key_digest", name="pk_idempotency_records"),
    )
    op.drop_constraint("ck_resources_type", "resources", type_="check")
    op.create_check_constraint("ck_resources_type", "resources", NEW_RESOURCES_TYPE)
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_AUDIT_OPERATION)
    op.drop_constraint("ck_audit_events_action", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_action", "audit_events", NEW_AUDIT_ACTION)


def downgrade() -> None:
    op.drop_constraint("ck_audit_events_action", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_action", "audit_events", OLD_AUDIT_ACTION)
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_AUDIT_OPERATION)
    op.drop_constraint("ck_resources_type", "resources", type_="check")
    op.create_check_constraint("ck_resources_type", "resources", OLD_RESOURCES_TYPE)
    op.drop_table("idempotency_records")
