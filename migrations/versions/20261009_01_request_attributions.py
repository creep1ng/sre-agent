"""Store immutable per-request routing attribution separately from audit HMACs."""

import sqlalchemy as sa
from alembic import op

revision = "20261009_01"
down_revision = "20261007_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_attributions",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("audit_event_id", sa.String(length=40), nullable=False),
        sa.Column("requested_alias", sa.String(length=64), nullable=False),
        sa.Column("requested_model", sa.String(length=200), nullable=False),
        sa.Column("requested_provider", sa.String(length=64), nullable=False),
        sa.Column("requested_router", sa.String(length=64), nullable=False),
        sa.Column("credited_model", sa.String(length=200), nullable=True),
        sa.Column("credited_provider", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_request_attributions_request_id",
        ),
        sa.CheckConstraint(
            "requested_alias ~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$'",
            name="ck_request_attributions_alias",
        ),
        sa.CheckConstraint(
            "requested_model ~ '^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$'",
            name="ck_request_attributions_requested_model",
        ),
        sa.CheckConstraint(
            "requested_provider ~ '^[a-z][a-z0-9._-]{0,63}$'",
            name="ck_request_attributions_requested_provider",
        ),
        sa.CheckConstraint(
            "requested_router ~ '[^[:space:]]'", name="ck_request_attributions_router"
        ),
        sa.CheckConstraint(
            "credited_model IS NULL OR credited_model ~ '^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$'",
            name="ck_request_attributions_credited_model",
        ),
        sa.CheckConstraint(
            "credited_provider IS NULL OR credited_provider ~ '^[a-z][a-z0-9._-]{0,63}$'",
            name="ck_request_attributions_credited_provider",
        ),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_events.event_id"]),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint("audit_event_id", name="uq_request_attributions_audit_event"),
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION reject_request_attribution_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'request_attributions are append-only'; END; $$"""
    )
    op.execute(
        """CREATE TRIGGER request_attributions_append_only
        BEFORE UPDATE OR DELETE ON request_attributions
        FOR EACH ROW EXECUTE FUNCTION reject_request_attribution_mutation()"""
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM request_attributions)")):
        raise RuntimeError("cannot downgrade while request attribution evidence exists")
    op.execute("DROP TRIGGER request_attributions_append_only ON request_attributions")
    op.drop_table("request_attributions")
    op.execute("DROP FUNCTION reject_request_attribution_mutation()")
