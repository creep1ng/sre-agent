"""Add owner-authoritative MCP server and tool lifecycle tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260921_12"
down_revision = "20260918_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("server_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("contract_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("tags", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("contract_version = '1.0.0'", name="ck_mcp_servers_contract_version"),
        sa.CheckConstraint(
            "status IN ('registered','active','inactive')", name="ck_mcp_servers_status"
        ),
        sa.CheckConstraint(
            "visibility IN ('public','private','hidden')", name="ck_mcp_servers_visibility"
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_mcp_servers_lifecycle"),
        sa.PrimaryKeyConstraint("server_id", name="pk_mcp_servers"),
    )
    op.create_table(
        "mcp_tools",
        sa.Column("tool_id", sa.String(64), nullable=False),
        sa.Column("server_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("contract_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("upstream_name", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("tags", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.server_id"]),
        sa.CheckConstraint("contract_version = '1.0.0'", name="ck_mcp_tools_contract_version"),
        sa.CheckConstraint(
            "status IN ('registered','active','inactive')", name="ck_mcp_tools_status"
        ),
        sa.CheckConstraint(
            "visibility IN ('public','private','hidden')", name="ck_mcp_tools_visibility"
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_mcp_tools_lifecycle"),
        sa.PrimaryKeyConstraint("tool_id", name="pk_mcp_tools"),
        sa.UniqueConstraint("server_id", "upstream_name", name="uq_mcp_tools_server_upstream"),
    )


def downgrade() -> None:
    op.drop_table("mcp_tools")
    op.drop_table("mcp_servers")
