"""Allow idempotent writes to the consumption policy."""

import sqlalchemy as sa
from alembic import op

revision = "20260929_16"
down_revision = "20260929_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_idempotency_method", "idempotency_records", type_="check")
    op.create_check_constraint(
        "ck_idempotency_method", "idempotency_records", "method IN ('POST','PUT')"
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_put_bindings = connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM idempotency_records WHERE method='PUT')")
    )
    if has_put_bindings:
        raise RuntimeError("cannot downgrade while PUT idempotency bindings exist")

    op.drop_constraint("ck_idempotency_method", "idempotency_records", type_="check")
    op.create_check_constraint("ck_idempotency_method", "idempotency_records", "method = 'POST'")
