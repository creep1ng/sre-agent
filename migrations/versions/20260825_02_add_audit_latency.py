"""Add required audit-event latency after backfilling legacy rows."""

import sqlalchemy as sa
from alembic import op

revision = "20260825_02"
down_revision = "20260822_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("UPDATE audit_events SET latency_ms = 0 WHERE latency_ms IS NULL")
    op.execute(
        """CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"""
    )
    op.alter_column("audit_events", "latency_ms", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint("ck_audit_events_latency", "audit_events", "latency_ms >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_audit_events_latency", "audit_events", type_="check")
    op.drop_column("audit_events", "latency_ms")
