"""Admit mitigation.execute in the audit log: each approval that reaches the deploy-executor (#722).

The operation vocabulary starts from the current one (20261001_02) and only appends the new word,
without publishing a new audit schema release, as the definition of ready of #722 decided.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261031_01"
down_revision = "20261026_01"
branch_labels = None
depends_on = None

OLD_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create','principals.get',"
    "'principals.list','principals.status.replace','credentials.issue','credentials.list',"
    "'credentials.revoke','credentials.rotate','grants.create','grants.list','grants.revoke',"
    "'aliases.create','aliases.list','aliases.get','aliases.assignment.replace',"
    "'aliases.status.replace','catalog.create','catalog.list','catalog.read',"
    "'mcp.discovery','mcp.invoke','usage.read','bok.search','bok.read',"
    "'catalog.status.replace','skills.resolve','consumption_limits.get',"
    "'consumption_limits.replace')"
)
NEW_OPERATION = OLD_OPERATION[:-1] + ",'mitigation.execute')"


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_OPERATION)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM audit_events WHERE operation='mitigation.execute')")
    ):
        raise RuntimeError("cannot downgrade while mitigation.execute audit evidence exists")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_OPERATION)
