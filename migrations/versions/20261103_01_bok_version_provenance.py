"""Record who published a BoK collection version and from where (#33).

The author reached only the audit event's HMAC principal reference and the origin was validated
then dropped. Both now live on the version they describe. They are nullable: seeded versions and
those published before this revision have no human author on record.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261103_01"
down_revision = "20261102_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bok_collection_versions", sa.Column("published_by", sa.String(64)))
    op.add_column("bok_collection_versions", sa.Column("origin", sa.String(97)))
    op.create_check_constraint(
        "ck_bok_versions_origin",
        "bok_collection_versions",
        "origin ~ '^[a-z][a-z0-9-]{1,31}(:[A-Za-z0-9._-]{1,64})?$'",
    )
    op.create_check_constraint(
        "ck_bok_versions_provenance",
        "bok_collection_versions",
        "(published_by IS NULL) = (origin IS NULL)",
    )


def downgrade() -> None:
    op.drop_column("bok_collection_versions", "origin")
    op.drop_column("bok_collection_versions", "published_by")
