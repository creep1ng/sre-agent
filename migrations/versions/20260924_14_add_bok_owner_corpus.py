"""Add immutable BoK owner corpus versions, documents, and section chunks."""

import sqlalchemy as sa
from alembic import op

revision = "20260924_14"
down_revision = "20260922_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bok_collection_versions",
        sa.Column("collection_id", sa.String(100), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('indexing','ready','active','inactive','revoked')",
            name="ck_bok_versions_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('public','private','hidden')", name="ck_bok_versions_visibility"
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_bok_versions_lifecycle"),
        sa.PrimaryKeyConstraint("collection_id", "version", name="pk_bok_collection_versions"),
    )
    op.create_table(
        "bok_documents",
        sa.Column("collection_id", sa.String(100), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_ref", sa.String(500), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id", "version"],
            ["bok_collection_versions.collection_id", "bok_collection_versions.version"],
            name="fk_bok_documents_collection_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("collection_id", "version", "document_id", name="pk_bok_documents"),
    )
    op.create_table(
        "bok_section_chunks",
        sa.Column("collection_id", sa.String(100), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(100), nullable=False),
        sa.Column("section_id", sa.String(100), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint("chunk_index >= 0", name="ck_bok_chunks_index"),
        sa.ForeignKeyConstraint(
            ["collection_id", "version", "document_id"],
            ["bok_documents.collection_id", "bok_documents.version", "bok_documents.document_id"],
            name="fk_bok_chunks_document_version",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "collection_id",
            "version",
            "document_id",
            "section_id",
            "chunk_index",
            name="pk_bok_section_chunks",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM bok_collection_versions)")):
        raise RuntimeError("cannot downgrade while BoK collection versions exist")
    op.drop_table("bok_section_chunks")
    op.drop_table("bok_documents")
    op.drop_table("bok_collection_versions")
