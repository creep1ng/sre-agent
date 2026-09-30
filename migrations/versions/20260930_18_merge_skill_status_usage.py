"""Integrate status and usage history without rewriting published migrations."""

import sqlalchemy as sa
from alembic import op

revision = "20260930_18"
down_revision = "20260926_15"
branch_labels = None
depends_on = None

NEW_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create','principals.get',"
    "'principals.list','principals.status.replace','credentials.issue','credentials.list',"
    "'credentials.revoke','credentials.rotate','grants.create','grants.list','grants.revoke',"
    "'aliases.create','aliases.list','aliases.get','aliases.assignment.replace',"
    "'aliases.status.replace','catalog.create','catalog.list','catalog.read',"
    "'mcp.discovery','mcp.invoke','usage.read','catalog.status.replace',"
    "'bok.search','bok.read')"
)
TARGET_OPERATION = NEW_OPERATION.replace(
    ",'catalog.status.replace','bok.search','bok.read'", ",'bok.search','bok.read'"
)
TARGET_REASON = (
    "reason_code IS NULL OR reason_code IN ('audit_unavailable','authentication_failed',"
    "'contract_validation_failed','grant_matched','no_matching_grant','redaction_failed',"
    "'redaction_uncertain','routing_unavailable','upstream_failed','upstream_invalid',"
    "'upstream_unavailable','resource_not_found','index_unavailable','storage_unavailable')"
)


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_OPERATION)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events WHERE operation IN "
            "('catalog.status.replace', 'skills.resolve'))"
        )
    ):
        raise RuntimeError("cannot downgrade integration while audit evidence exists")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", TARGET_OPERATION)
