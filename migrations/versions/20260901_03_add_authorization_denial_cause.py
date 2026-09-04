"""Add a nullable, audit-only authorization denial cause."""

import sqlalchemy as sa
from alembic import op

revision = "20260901_03"
down_revision = "20260825_02"
branch_labels = None
depends_on = None

CONSTRAINT = """authorization_denial_cause IS NULL OR (
  authorization_denial_cause IN (
    'principal_inactive', 'resource_missing', 'resource_inactive', 'grant_not_applicable'
  ) AND stage = 'authorization' AND outcome = 'denied'
  AND reason_code = 'no_matching_grant' AND response_status = 403
)"""


def upgrade() -> None:
    op.add_column(
        "audit_events", sa.Column("authorization_denial_cause", sa.String(32), nullable=True)
    )
    op.create_check_constraint(
        "ck_audit_events_authorization_denial_cause", "audit_events", CONSTRAINT
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_events_authorization_denial_cause", "audit_events", type_="check")
    op.drop_column("audit_events", "authorization_denial_cause")
