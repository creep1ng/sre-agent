"""Admit consumption-limit denial vocabulary for gateway admission."""

import sqlalchemy as sa
from alembic import op

revision = "20260929_18"
down_revision = "20260929_17"
branch_labels = None
depends_on = None


OLD_REASON = """reason_code IS NULL OR reason_code IN (
  'audit_unavailable', 'authentication_failed', 'contract_validation_failed',
  'grant_matched', 'no_matching_grant', 'redaction_failed', 'redaction_uncertain',
  'routing_unavailable', 'upstream_failed', 'upstream_invalid', 'upstream_unavailable',
  'resource_not_found', 'status_conflict'
)"""
NEW_REASON = """reason_code IS NULL OR reason_code IN (
  'audit_unavailable', 'authentication_failed', 'contract_validation_failed',
  'grant_matched', 'no_matching_grant', 'redaction_failed', 'redaction_uncertain',
  'routing_unavailable', 'upstream_failed', 'upstream_invalid', 'upstream_unavailable',
  'resource_not_found', 'status_conflict', 'incident_limit_exceeded',
  'monthly_limit_exceeded', 'consumption_bounds_unavailable', 'policy_unavailable'
)"""


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_reason_code", "audit_events", NEW_REASON)


def downgrade() -> None:
    has_admission_evidence = op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM audit_events WHERE reason_code IN ("
            "'incident_limit_exceeded','monthly_limit_exceeded',"
            "'consumption_bounds_unavailable','policy_unavailable'))"
        )
    )
    if has_admission_evidence:
        raise RuntimeError("cannot downgrade while consumption admission denials exist")
    op.drop_constraint("ck_audit_events_reason_code", "audit_events", type_="check")
    op.create_check_constraint("ck_audit_events_reason_code", "audit_events", OLD_REASON)
