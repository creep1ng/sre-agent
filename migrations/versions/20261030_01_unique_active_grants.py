"""Keep grants unique among active rows only, so a revoked grant can be granted again (#759)."""

import sqlalchemy as sa
from alembic import op

revision = "20261030_01"
down_revision = "20261018_01"
branch_labels = None
depends_on = None
SHARED_KEYS = sa.text(
    "SELECT string_agg(grant_id, ',' ORDER BY grant_id) FROM grants "
    "GROUP BY principal_id, action, resource_type, resource_id HAVING count(*) > 1"
)


def upgrade() -> None:
    # A revoked row keeps its audit trail; it must not occupy the key of a new active grant.
    op.execute("ALTER TABLE grants DROP CONSTRAINT uq_grants_direct")
    op.execute(
        "CREATE UNIQUE INDEX uq_grants_active_direct "
        "ON grants (principal_id, action, resource_type, resource_id) WHERE status = 'active'"
    )


def downgrade() -> None:
    # The old constraint spans revoked rows too: refuse while any two grants share its key.
    shared = op.get_bind().scalars(SHARED_KEYS).all()
    if shared:
        raise RuntimeError("cannot downgrade while grants share a key: " + "; ".join(shared))
    op.execute("DROP INDEX uq_grants_active_direct")
    op.execute(
        "ALTER TABLE grants ADD CONSTRAINT uq_grants_direct "
        "UNIQUE (principal_id, action, resource_type, resource_id)"
    )
