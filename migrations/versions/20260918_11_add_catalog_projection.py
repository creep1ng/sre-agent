"""Expose the closed owner-backed catalog projection over resources."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260918_11"
down_revision = "20260918_10"
branch_labels = None
depends_on = None

OLD_AUDIT_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create',"
    "'principals.get','principals.list','principals.status.replace',"
    "'credentials.issue','credentials.list','credentials.revoke','credentials.rotate',"
    "'grants.create','grants.list','grants.revoke',"
    "'aliases.create','aliases.list','aliases.get',"
    "'aliases.assignment.replace','aliases.status.replace')"
)
CATALOG_OPERATIONS = ("catalog.create", "catalog.list", "catalog.read")
NEW_AUDIT_OPERATION = (
    OLD_AUDIT_OPERATION[:-1]
    + ","
    + ",".join(f"'{operation}'" for operation in CATALOG_OPERATIONS)
    + ")"
)
OLD_STATUS = "status IN ('active','inactive')"
NEW_STATUS = "status IN ('registered','draft','published','indexing','active','inactive','revoked')"
CATALOG_PROJECTION = (
    "(resource_type='administrative_control' AND owner_id IS NULL AND source IS NULL "
    "AND source_ref IS NULL AND display_name IS NULL AND visibility IS NULL "
    "AND description IS NULL AND tags IS NULL) OR "
    "(resource_type<>'administrative_control' AND owner_id IS NOT NULL "
    "AND source IS NOT NULL AND source_ref IS NOT NULL AND display_name IS NOT NULL "
    "AND visibility IS NOT NULL AND description IS NOT NULL)"
)
CATALOG_SOURCE = "source IS NULL OR source IN ('model_alias','mcp','skill','bok')"
CATALOG_VISIBILITY = "visibility IS NULL OR visibility IN ('public','private','hidden')"
CATALOG_OWNER = (
    "(resource_type='llm_model' AND source='model_alias') OR "
    "(resource_type IN ('mcp_server','mcp_tool') AND source='mcp') OR "
    "(resource_type='skill' AND source='skill') OR "
    "(resource_type='bok_collection' AND source='bok') OR "
    "(resource_type='administrative_control' AND source IS NULL)"
)


def upgrade() -> None:
    op.add_column("resources", sa.Column("owner_id", sa.String(64), nullable=True))
    op.add_column("resources", sa.Column("source", sa.String(32), nullable=True))
    op.add_column("resources", sa.Column("source_ref", sa.String(200), nullable=True))
    op.add_column("resources", sa.Column("display_name", sa.String(200), nullable=True))
    op.add_column("resources", sa.Column("visibility", sa.String(16), nullable=True))
    op.add_column("resources", sa.Column("description", sa.String(500), nullable=True))
    op.add_column("resources", sa.Column("tags", JSONB, nullable=True))
    # Backfill seeded llm_model rows with ADMIN-authoritative catalog metadata.
    # Owner is the subsystem owner of the RESOURCE (the alias itself for llm);
    # discoverability defaults to a private projection of the alias slug.
    op.execute(
        sa.text(
            "UPDATE resources SET owner_id = model_alias_id, source = 'model_alias', "
            "source_ref = model_alias_id, display_name = alias, visibility = 'private', "
            "description = '', tags = '[]'::jsonb "
            "WHERE resource_type = 'llm_model' AND owner_id IS NULL"
        )
    )
    op.drop_constraint("ck_resources_status", "resources", type_="check")
    op.create_check_constraint("ck_resources_status", "resources", NEW_STATUS)
    op.create_check_constraint("ck_resources_catalog_projection", "resources", CATALOG_PROJECTION)
    op.create_check_constraint("ck_resources_catalog_source", "resources", CATALOG_SOURCE)
    op.create_check_constraint("ck_resources_catalog_visibility", "resources", CATALOG_VISIBILITY)
    op.create_check_constraint("ck_resources_catalog_owner", "resources", CATALOG_OWNER)
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_AUDIT_OPERATION)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events "
            "WHERE operation IN ('catalog.create','catalog.list','catalog.read'))"
        )
    ):
        raise RuntimeError("cannot downgrade while catalog audit evidence exists")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM resources "
            "WHERE resource_type IN "
            "('mcp_server','mcp_tool','skill','bok_collection'))"
        )
    ):
        raise RuntimeError("cannot downgrade while catalog resources exist")
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_AUDIT_OPERATION)
    op.drop_constraint("ck_resources_catalog_owner", "resources", type_="check")
    op.drop_constraint("ck_resources_catalog_visibility", "resources", type_="check")
    op.drop_constraint("ck_resources_catalog_source", "resources", type_="check")
    op.drop_constraint("ck_resources_catalog_projection", "resources", type_="check")
    op.drop_constraint("ck_resources_status", "resources", type_="check")
    op.create_check_constraint("ck_resources_status", "resources", OLD_STATUS)
    op.drop_column("resources", "tags")
    op.drop_column("resources", "description")
    op.drop_column("resources", "visibility")
    op.drop_column("resources", "display_name")
    op.drop_column("resources", "source_ref")
    op.drop_column("resources", "source")
    op.drop_column("resources", "owner_id")
