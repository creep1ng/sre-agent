"""Allow metadata-only MCP gateway audit events."""

import sqlalchemy as sa
from alembic import op

revision = "20260921_13"
down_revision = "20260921_12"
branch_labels = None
depends_on = None


OLD_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'principals.get','principals.list','principals.status.replace',"
    "'credentials.issue','credentials.list','credentials.revoke','credentials.rotate',"
    "'grants.create','grants.list','grants.revoke','aliases.create','aliases.list',"
    "'aliases.get','aliases.assignment.replace','aliases.status.replace','catalog.create',"
    "'catalog.list','catalog.read')"
)
NEW_OPERATION = OLD_OPERATION[:-1] + ",'mcp.discovery','mcp.invoke')"


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_OPERATION)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events "
            "WHERE operation IN ('mcp.discovery','mcp.invoke'))"
        )
    ):
        raise RuntimeError("cannot downgrade while MCP audit evidence exists")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_OPERATION)
