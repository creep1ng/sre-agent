"""Persist immutable owner-authoritative instruction-only Skill versions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260924_14"
down_revision = "20260922_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_versions",
        sa.Column("skill_id", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("resource_type = 'skill'", name="ck_skill_versions_resource_type"),
        sa.CheckConstraint(
            "resource_id = skill_id || '@' || version", name="ck_skill_versions_resource_id"
        ),
        sa.CheckConstraint(
            "skill_id ~ '^[a-z][a-z0-9-]{2,62}[a-z0-9]$'",
            name="ck_skill_versions_skill_id",
        ),
        sa.CheckConstraint(
            "version ~ '^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$'",
            name="ck_skill_versions_version",
        ),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_skill_versions_hash"),
        sa.ForeignKeyConstraint(
            ["resource_type", "resource_id"],
            ["resources.resource_type", "resources.resource_id"],
        ),
        sa.PrimaryKeyConstraint("skill_id", "version"),
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION reject_skill_version_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'published Skill versions are immutable'; END; $$"""
    )
    op.execute(
        """CREATE TRIGGER skill_versions_append_only BEFORE UPDATE OR DELETE ON skill_versions
        FOR EACH ROW EXECUTE FUNCTION reject_skill_version_mutation()"""
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM skill_versions)")):
        raise RuntimeError("cannot downgrade while immutable Skill versions exist")
    op.execute("DROP TRIGGER skill_versions_append_only ON skill_versions")
    op.drop_table("skill_versions")
    op.execute("DROP FUNCTION reject_skill_version_mutation()")
