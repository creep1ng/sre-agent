"""Allow metadata-only model-alias control-plane audit events."""

import sqlalchemy as sa
from alembic import op

revision = "20260917_09"
down_revision = "20260916_08"
branch_labels = None
depends_on = None

OLD_AUDIT_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'principals.get','principals.list','principals.status.replace',"
    "'credentials.issue','credentials.list','credentials.revoke','credentials.rotate',"
    "'grants.create','grants.list','grants.revoke')"
)
ALIAS_AUDIT_OPERATIONS = ("aliases.create", "aliases.list", "aliases.get")
NEW_AUDIT_OPERATION = (
    OLD_AUDIT_OPERATION[:-1]
    + ","
    + ",".join(f"'{operation}'" for operation in ALIAS_AUDIT_OPERATIONS)
    + ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_AUDIT_OPERATION)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events "
            "WHERE operation IN ('aliases.create','aliases.list','aliases.get'))"
        )
    ):
        raise RuntimeError("cannot downgrade while alias audit evidence exists")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_AUDIT_OPERATION)
