"""Allow metadata-only grant control-plane audit events."""

import sqlalchemy as sa
from alembic import op

revision = "20260916_08"
down_revision = "20260910_07"
branch_labels = None
depends_on = None

OLD_AUDIT_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'principals.get','principals.list','principals.status.replace',"
    "'credentials.issue','credentials.list','credentials.revoke','credentials.rotate')"
)
GRANT_AUDIT_OPERATIONS = ("grants.create", "grants.list", "grants.revoke")
NEW_AUDIT_OPERATION = (
    OLD_AUDIT_OPERATION[:-1]
    + ","
    + ",".join(f"'{operation}'" for operation in GRANT_AUDIT_OPERATIONS)
    + ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_AUDIT_OPERATION)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events "
            "WHERE operation IN ('grants.create','grants.list','grants.revoke'))"
        )
    ):
        raise RuntimeError("cannot downgrade while grant audit evidence exists")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_AUDIT_OPERATION)
