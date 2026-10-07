"""Persist triage decision provenance without inferring legacy origin."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_01"
down_revision = "20260923_13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_triage",
        sa.Column(
            "decision_origin",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.add_column(
        "alert_triage",
        sa.Column("responsible_system", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_alert_triage_decision_origin",
        "alert_triage",
        "decision_origin IN ('manual','external_automatic','unknown')",
    )
    op.create_check_constraint(
        "ck_alert_triage_provenance_pair",
        "alert_triage",
        "(decision_origin = 'external_automatic' AND responsible_system IS NOT NULL "
        "AND responsible_system ~ '[^[:space:]]') OR "
        "(decision_origin IN ('manual','unknown') AND responsible_system IS NULL)",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM alert_triage "
            "WHERE decision_origin <> 'unknown' OR responsible_system IS NOT NULL)"
        )
    ):
        raise RuntimeError("cannot downgrade while provenance data exists")
    op.drop_constraint("ck_alert_triage_provenance_pair", "alert_triage", type_="check")
    op.drop_constraint("ck_alert_triage_decision_origin", "alert_triage", type_="check")
    op.drop_column("alert_triage", "responsible_system")
    op.drop_column("alert_triage", "decision_origin")
