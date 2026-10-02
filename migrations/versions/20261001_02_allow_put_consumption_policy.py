"""Allow idempotent writes to the consumption policy.

Rebased onto the integrated foundation head (20261001_01) during the #441
merge: the operation vocabulary below starts from the integrated list and
only appends the replace operation, so BoK/skill/status words survive.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261001_02"
down_revision = "20261001_01"
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
    "'catalog.status.replace','skills.resolve','consumption_limits.get')"
)
NEW_OPERATION = OLD_OPERATION[:-1] + ",'consumption_limits.replace')"


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_OPERATION)
    op.drop_constraint("ck_idempotency_method", "idempotency_records", type_="check")
    op.create_check_constraint(
        "ck_idempotency_method", "idempotency_records", "method IN ('POST','PUT')"
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_put_evidence = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM idempotency_records WHERE method='PUT') "
            "OR EXISTS (SELECT 1 FROM audit_events WHERE operation='consumption_limits.replace')"
        )
    )
    if has_put_evidence:
        raise RuntimeError(
            "cannot downgrade while consumption-write audit evidence or "
            "PUT idempotency bindings exist"
        )

    op.drop_constraint("ck_idempotency_method", "idempotency_records", type_="check")
    op.create_check_constraint("ck_idempotency_method", "idempotency_records", "method = 'POST'")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_OPERATION)
