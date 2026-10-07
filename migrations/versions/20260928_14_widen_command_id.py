"""Hold the whole idempotency key the run API contract admits.

The contract (urn:sre-agent:schema, incident-runs.openapi.yaml) accepts an
Idempotency-Key of 8 to 200 characters, while incident.transition_commits stored
it in varchar(128). Narrowing the boundary to the column would reject requests
the contract admits, so the column follows the contract instead.

Widening a varchar is not a rewrite in PostgreSQL, but command_id is part of the
primary key, so the index is rebuilt. Downgrade fails loudly if any stored key is
longer than the old width: truncating an idempotency key would merge two
different commands into one.
"""

from alembic import op

revision = "20260928_14"
down_revision = "20260929_18"
branch_labels = None
depends_on = None

TABLE = "incident.transition_commits"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN command_id TYPE varchar(200)")


def downgrade() -> None:
    op.execute(f"""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM {TABLE} WHERE length(command_id) > 128) THEN
        RAISE EXCEPTION 'cannot narrow command_id: a stored idempotency key exceeds 128 characters';
      END IF;
    END
    $$
    """)
    op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN command_id TYPE varchar(128)")
