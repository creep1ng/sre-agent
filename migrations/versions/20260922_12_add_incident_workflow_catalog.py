"""Admit the stable incident_workflow resource in the governed catalog."""

import sqlalchemy as sa
from alembic import op

revision = "20260922_12"
down_revision = "20260918_11"
branch_labels = None
depends_on = None

NEW_TYPE = (
    "resource_type IN ('llm_model','mcp_server','mcp_tool','skill','bok_collection',"
    "'administrative_control','incident_workflow')"
)
OLD_TYPE = (
    "resource_type IN ('llm_model','mcp_server','mcp_tool','skill','bok_collection',"
    "'administrative_control')"
)
NEW_SOURCE = "source IS NULL OR source IN ('model_alias','mcp','skill','bok','incident_workflow')"
OLD_SOURCE = "source IS NULL OR source IN ('model_alias','mcp','skill','bok')"
NEW_OWNER = (
    "(resource_type='llm_model' AND source='model_alias') OR "
    "(resource_type IN ('mcp_server','mcp_tool') AND source='mcp') OR "
    "(resource_type='skill' AND source='skill') OR "
    "(resource_type='bok_collection' AND source='bok') OR "
    "(resource_type='administrative_control' AND source IS NULL) OR "
    "(resource_type='incident_workflow' AND source='incident_workflow')"
)
OLD_OWNER = (
    "(resource_type='llm_model' AND source='model_alias') OR "
    "(resource_type IN ('mcp_server','mcp_tool') AND source='mcp') OR "
    "(resource_type='skill' AND source='skill') OR "
    "(resource_type='bok_collection' AND source='bok') OR "
    "(resource_type='administrative_control' AND source IS NULL)"
)


def upgrade() -> None:
    op.drop_constraint("ck_resources_type", "resources", type_="check")
    op.create_check_constraint("ck_resources_type", "resources", NEW_TYPE)
    op.drop_constraint("ck_resources_catalog_source", "resources", type_="check")
    op.create_check_constraint("ck_resources_catalog_source", "resources", NEW_SOURCE)
    op.drop_constraint("ck_resources_catalog_owner", "resources", type_="check")
    op.create_check_constraint("ck_resources_catalog_owner", "resources", NEW_OWNER)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM resources WHERE resource_type='incident_workflow')")
    ):
        raise RuntimeError("cannot downgrade while incident_workflow resources exist")
    op.drop_constraint("ck_resources_catalog_owner", "resources", type_="check")
    op.create_check_constraint("ck_resources_catalog_owner", "resources", OLD_OWNER)
    op.drop_constraint("ck_resources_catalog_source", "resources", type_="check")
    op.create_check_constraint("ck_resources_catalog_source", "resources", OLD_SOURCE)
    op.drop_constraint("ck_resources_type", "resources", type_="check")
    op.create_check_constraint("ck_resources_type", "resources", OLD_TYPE)
