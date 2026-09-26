"""Allow request-correlated metadata-only Skill resolution audit events."""

import sqlalchemy as sa
from alembic import op

revision = "20260926_16"
down_revision = "20260926_15"
branch_labels = None
depends_on = None

OLD_OPERATION = (
    "operation IN ('audit.accept','audit.export','audit.project','audit.redact',"
    "'credentials.authenticate','responses.create','principals.create','principals.get',"
    "'principals.list','principals.status.replace','credentials.issue','credentials.list',"
    "'credentials.revoke','credentials.rotate','grants.create','grants.list','grants.revoke',"
    "'aliases.create','aliases.list','aliases.get','aliases.assignment.replace',"
    "'aliases.status.replace','catalog.create','catalog.list','catalog.read',"
    "'mcp.discovery','mcp.invoke','catalog.status.replace')"
)
NEW_OPERATION = OLD_OPERATION[:-1] + ",'skills.resolve')"
OLD_DENIAL = """authorization_denial_cause IS NULL OR (
  authorization_denial_cause IN (
    'principal_inactive', 'resource_missing', 'resource_inactive', 'grant_not_applicable'
  ) AND stage = 'authorization' AND outcome = 'denied'
  AND reason_code = 'no_matching_grant' AND (
    response_status = 403 OR (
      response_status = 404 AND action = 'admin.read'
      AND COALESCE(resource ->> 'resource_type' = 'administrative_control', false)
    )
  )
)"""
NEW_DENIAL = """authorization_denial_cause IS NULL OR (
  authorization_denial_cause IN (
    'principal_inactive', 'resource_missing', 'resource_inactive', 'grant_not_applicable'
  ) AND stage = 'authorization' AND outcome = 'denied'
  AND reason_code = 'no_matching_grant' AND (
    response_status = 403 OR (
      response_status = 404 AND action = 'admin.read'
      AND COALESCE(resource ->> 'resource_type' = 'administrative_control', false)
    ) OR (
      response_status = 404 AND action = 'invoke'
      AND COALESCE(resource ->> 'resource_type' = 'skill', false)
    )
  )
)"""


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", NEW_OPERATION)
    op.drop_constraint("ck_audit_events_authorization_denial_cause", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_authorization_denial_cause", "audit_events", NEW_DENIAL
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM audit_events WHERE operation='skills.resolve')")
    ):
        raise RuntimeError("cannot downgrade while Skill resolution audit evidence exists")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events WHERE response_status=404 "
            "AND action='invoke' AND resource->>'resource_type'='skill' "
            "AND authorization_denial_cause IS NOT NULL)"
        )
    ):
        raise RuntimeError("cannot downgrade while Skill denial audit evidence exists")
    op.drop_constraint("ck_audit_events_authorization_denial_cause", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_authorization_denial_cause", "audit_events", OLD_DENIAL
    )
    op.drop_constraint("ck_audit_events_operation", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_operation", "audit_events", OLD_OPERATION)
