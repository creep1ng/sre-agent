"""Join the immutable Skills branch and the BoK full-text branch into one head."""

import sqlalchemy as sa
from alembic import op

revision = "20260930_21"
down_revision = ("20260930_17", "20260929_16")
branch_labels = None
depends_on = None

SKILLS_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'mcp.discovery','mcp.invoke','principals.get','principals.list',"
    "'principals.status.replace','credentials.issue','credentials.list',"
    "'credentials.revoke','credentials.rotate','grants.create','grants.list',"
    "'grants.revoke','aliases.create','aliases.list','aliases.get',"
    "'aliases.assignment.replace','aliases.status.replace','catalog.create',"
    "'catalog.list','catalog.read','usage.read')"
)
BOK_OPERATION = SKILLS_OPERATION[:-1] + ",'bok.search','bok.read')"
SKILLS_REASON = (
    "reason_code IS NULL OR reason_code IN ('audit_unavailable','authentication_failed',"
    "'contract_validation_failed','grant_matched','no_matching_grant','redaction_failed',"
    "'redaction_uncertain','routing_unavailable','upstream_failed','upstream_invalid',"
    "'upstream_unavailable','resource_not_found','status_conflict')"
)
BOK_REASON = SKILLS_REASON[:-1] + ",'index_unavailable','storage_unavailable')"


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", BOK_OPERATION)
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_reason_code", "audit_events", BOK_REASON)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events "
            "WHERE operation IN ('bok.search', 'bok.read'))"
        )
    ):
        raise RuntimeError("cannot downgrade BoK merge while BoK audit evidence exists")
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_reason_code", "audit_events", SKILLS_REASON)
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", SKILLS_OPERATION)