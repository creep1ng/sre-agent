"""Persist metadata-only consumption reservations before provider work."""

import sqlalchemy as sa
from alembic import op

revision = "20260929_17"
down_revision = "20260929_16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consumption_reservations",
        sa.Column("reservation_id", sa.String(64), nullable=False),
        sa.Column("incident_id", sa.String(64), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policy_version", sa.BigInteger(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("token_exposure", sa.BigInteger(), nullable=True),
        sa.Column("usd_exposure", sa.Numeric(56, 36), nullable=True),
        sa.Column("settled_tokens", sa.BigInteger(), nullable=True),
        sa.Column("settled_usd_cost", sa.Numeric(56, 36), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("policy_version >= 0", name="ck_consumption_reservation_version"),
        sa.CheckConstraint("length(model) > 0", name="ck_consumption_reservation_model"),
        sa.CheckConstraint("length(provider) > 0", name="ck_consumption_reservation_provider"),
        sa.CheckConstraint(
            "period_start = date_trunc('month', period_start AT TIME ZONE 'UTC') "
            "AT TIME ZONE 'UTC'",
            name="ck_consumption_reservation_period_utc_month",
        ),
        sa.CheckConstraint(
            "token_exposure IS NULL OR token_exposure >= 0",
            name="ck_consumption_reservation_tokens",
        ),
        sa.CheckConstraint(
            "usd_exposure IS NULL OR usd_exposure >= 0",
            name="ck_consumption_reservation_usd",
        ),
        sa.CheckConstraint(
            "settled_tokens IS NULL OR settled_tokens >= 0",
            name="ck_consumption_reservation_settled_tokens",
        ),
        sa.CheckConstraint(
            "settled_usd_cost IS NULL OR settled_usd_cost >= 0",
            name="ck_consumption_reservation_settled_usd",
        ),
        sa.CheckConstraint(
            "state IN ('reserved','settled','released')",
            name="ck_consumption_reservation_state",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incident.incidents.incident_id"],
            name="fk_consumption_reservation_incident",
        ),
        sa.PrimaryKeyConstraint("reservation_id", name="pk_consumption_reservations"),
    )
    op.create_index(
        "ix_consumption_reservations_period_incident",
        "consumption_reservations",
        ["period_start", "incident_id"],
    )
    op.create_index(
        "ix_consumption_reservations_period_workspace",
        "consumption_reservations",
        ["period_start"],
        postgresql_where=sa.text("incident_id IS NULL"),
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION reject_consumption_period_change() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.period_start IS DISTINCT FROM OLD.period_start THEN
            RAISE EXCEPTION 'consumption reservation period is immutable';
          END IF;
          RETURN NEW;
        END $$"""
    )
    op.execute(
        """CREATE TRIGGER consumption_reservation_period_immutable
        BEFORE UPDATE OF period_start ON consumption_reservations
        FOR EACH ROW EXECUTE FUNCTION reject_consumption_period_change()"""
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM consumption_reservations)")):
        raise RuntimeError("cannot downgrade while reservations exist")
    op.drop_table("consumption_reservations")
    op.execute("DROP FUNCTION reject_consumption_period_change()")
