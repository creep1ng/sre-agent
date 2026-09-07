"""Allow audit-only 404 evidence for denied administrative control reads."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_05"
down_revision = "20260902_04"
branch_labels = None
depends_on = None

OLD_CONSTRAINT = """authorization_denial_cause IS NULL OR (
  authorization_denial_cause IN (
    'principal_inactive', 'resource_missing', 'resource_inactive', 'grant_not_applicable'
  ) AND stage = 'authorization' AND outcome = 'denied'
  AND reason_code = 'no_matching_grant' AND response_status = 403
)"""
OLD_REASON_CODE_CONSTRAINT = """reason_code IS NULL OR reason_code IN (
  'audit_unavailable', 'authentication_failed', 'contract_validation_failed',
  'grant_matched', 'no_matching_grant', 'redaction_failed', 'redaction_uncertain',
  'routing_unavailable', 'upstream_failed', 'upstream_invalid', 'upstream_unavailable'
)"""
NEW_REASON_CODE_CONSTRAINT = """reason_code IS NULL OR reason_code IN (
  'audit_unavailable', 'authentication_failed', 'contract_validation_failed',
  'grant_matched', 'no_matching_grant', 'redaction_failed', 'redaction_uncertain',
  'routing_unavailable', 'upstream_failed', 'upstream_invalid', 'upstream_unavailable',
  'resource_not_found', 'status_conflict'
)"""
NEW_CONSTRAINT = """authorization_denial_cause IS NULL OR (
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


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_reason_code", "audit_events", NEW_REASON_CODE_CONSTRAINT
    )
    op.drop_constraint("ck_audit_events_authorization_denial_cause", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_authorization_denial_cause", "audit_events", NEW_CONSTRAINT
    )


def downgrade() -> None:
    has_control_read_denials = op.get_bind().scalar(
        sa.text(
            """SELECT EXISTS (
              SELECT 1 FROM audit_events
              WHERE (authorization_denial_cause IS NOT NULL AND response_status = 404)
                 OR reason_code IN ('resource_not_found', 'status_conflict')
            )"""
        )
    )
    if has_control_read_denials:
        raise RuntimeError("cannot downgrade while 404 authorization denial audit evidence exists")
    op.drop_constraint("ck_audit_events_authorization_denial_cause", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_authorization_denial_cause", "audit_events", OLD_CONSTRAINT
    )
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_reason_code", "audit_events", OLD_REASON_CODE_CONSTRAINT
    )
