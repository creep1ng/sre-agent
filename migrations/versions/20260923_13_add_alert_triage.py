"""Durable alert triage decisions with optimistic concurrency."""

import sqlalchemy as sa
from alembic import op

revision = "20260923_13"
down_revision = "20260922_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_triage",
        sa.Column("alert_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("incident_id", sa.String(64), nullable=True),
        sa.Column("expected_version", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("severity", sa.String(8), nullable=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open','dismissed','linked','declared')",
            name="ck_alert_triage_status",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('sev1','sev2','sev3','sev4')",
            name="ck_alert_triage_severity",
        ),
        sa.CheckConstraint(
            "(status='linked' AND incident_id IS NOT NULL) OR "
            "(status='declared' AND incident_id IS NOT NULL) OR "
            "(status IN ('open','dismissed') AND incident_id IS NULL)",
            name="ck_alert_triage_linkage",
        ),
        sa.CheckConstraint(
            "(status='declared' AND severity IS NOT NULL) OR status <> 'declared'",
            name="ck_alert_triage_declare_severity",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM alert_triage)")):
        raise RuntimeError("cannot downgrade while triage decisions exist")
    op.drop_table("alert_triage")
