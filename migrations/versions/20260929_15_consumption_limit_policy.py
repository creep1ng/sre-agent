"""Create the unset single-workspace consumption policy."""

import sqlalchemy as sa
from alembic import op

revision = "20260929_15"
down_revision = "20260926_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consumption_limit_policies",
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("incident_token_limit", sa.BigInteger(), nullable=True),
        sa.Column("monthly_usd_limit", sa.Numeric(32, 12), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("policy_id = 1", name="ck_consumption_policy_singleton"),
        sa.CheckConstraint("version >= 0", name="ck_consumption_policy_version"),
        sa.CheckConstraint(
            "incident_token_limit IS NULL OR incident_token_limit >= 0",
            name="ck_consumption_policy_incident_limit",
        ),
        sa.CheckConstraint(
            "monthly_usd_limit IS NULL OR monthly_usd_limit >= 0",
            name="ck_consumption_policy_monthly_limit",
        ),
        sa.PrimaryKeyConstraint("policy_id", name="pk_consumption_limit_policies"),
    )
    op.execute(
        sa.text(
            "INSERT INTO consumption_limit_policies "
            "(policy_id, version, incident_token_limit, monthly_usd_limit, updated_at) "
            "VALUES (1, 0, NULL, NULL, now())"
        )
    )


def downgrade() -> None:
    op.drop_table("consumption_limit_policies")
