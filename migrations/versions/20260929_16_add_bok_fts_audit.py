"""Add indexed English BoK search and metadata-only BoK audit vocabulary."""

import sqlalchemy as sa
from alembic import op

revision = "20260929_16"
down_revision = "20260929_15"
branch_labels = None
depends_on = None

OLD_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'mcp.discovery','mcp.invoke','principals.get','principals.list',"
    "'principals.status.replace','credentials.issue','credentials.list',"
    "'credentials.revoke','credentials.rotate','grants.create','grants.list',"
    "'grants.revoke','aliases.create','aliases.list','aliases.get',"
    "'aliases.assignment.replace','aliases.status.replace','catalog.create',"
    "'catalog.list','catalog.read','usage.read')"
)
OLD_REASON = (
    "reason_code IS NULL OR reason_code IN ('audit_unavailable','authentication_failed',"
    "'contract_validation_failed','grant_matched','no_matching_grant','redaction_failed',"
    "'redaction_uncertain','routing_unavailable','upstream_failed','upstream_invalid',"
    "'upstream_unavailable','resource_not_found','status_conflict')"
)
NEW_OPERATION = OLD_OPERATION[:-1] + ",'bok.search','bok.read')"
NEW_REASON = OLD_REASON[:-1] + ",'index_unavailable','storage_unavailable')"


def upgrade() -> None:
    op.create_index(
        "ix_bok_section_chunks_english_fts",
        "bok_section_chunks",
        [sa.text("to_tsvector('english', content)")],
        postgresql_using="gin",
    )
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_OPERATION)
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_reason_code", "audit_events", NEW_REASON)


def downgrade() -> None:
    bok_audit_exists = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events "
            "WHERE operation IN ('bok.search','bok.read'))"
        )
    )
    if bok_audit_exists:
        raise RuntimeError("cannot downgrade while BoK audit evidence exists")
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_reason_code", "audit_events", OLD_REASON)
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_OPERATION)
    op.drop_index("ix_bok_section_chunks_english_fts", table_name="bok_section_chunks")
