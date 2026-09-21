"""Expose the model-alias CAS version and admit alias mutation audit events."""

import sqlalchemy as sa
from alembic import op

revision = "20260918_10"
down_revision = "20260917_09"
branch_labels = None
depends_on = None

OLD_AUDIT_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'principals.get','principals.list','principals.status.replace',"
    "'credentials.issue','credentials.list','credentials.revoke','credentials.rotate',"
    "'grants.create','grants.list','grants.revoke',"
    "'aliases.create','aliases.list','aliases.get')"
)
ALIAS_MUTATION_OPERATIONS = ("aliases.assignment.replace", "aliases.status.replace")
NEW_AUDIT_OPERATION = (
    OLD_AUDIT_OPERATION[:-1]
    + ","
    + ",".join(f"'{operation}'" for operation in ALIAS_MUTATION_OPERATIONS)
    + ")"
)


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(sa.text("UPDATE resources SET updated_at = now() WHERE updated_at IS NULL"))
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_AUDIT_OPERATION)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events "
            "WHERE operation IN "
            "('aliases.assignment.replace','aliases.status.replace'))"
        )
    ):
        raise RuntimeError("cannot downgrade while alias mutation audit evidence exists")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_AUDIT_OPERATION)
    op.drop_column("resources", "updated_at")
