"""Record deploys, rollbacks and CI results as change events (issue #770)."""

from alembic import op

revision = "20261030_03"
down_revision = "20261030_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per (source, external_id, service): a resent event finds its row instead of
    # adding one. Rows are append-only facts about what changed and when.
    op.execute("""CREATE TABLE incident.change_events (
      change_id varchar(64) PRIMARY KEY,
      source varchar(32) NOT NULL,
      external_id varchar(200) NOT NULL,
      service varchar(64) NOT NULL,
      kind varchar(16) NOT NULL,
      status varchar(16) NOT NULL,
      version varchar(200),
      commit_sha varchar(64),
      ref varchar(200),
      author varchar(100),
      url varchar(500),
      occurred_at timestamptz NOT NULL,
      recorded_at timestamptz NOT NULL,
      recorded_by varchar(64) NOT NULL,
      CONSTRAINT uq_change_event_external UNIQUE (source, external_id, service),
      CONSTRAINT ck_change_event_kind CHECK (kind IN ('deploy', 'rollback', 'ci')),
      CONSTRAINT ck_change_event_status CHECK (status IN ('succeeded', 'failed'))
    )""")
    op.execute(
        "CREATE INDEX ix_change_events_service_occurred "
        "ON incident.change_events (service, occurred_at DESC)"
    )
    op.execute("""CREATE TRIGGER change_events_append_only BEFORE UPDATE OR DELETE
      ON incident.change_events FOR EACH ROW
      EXECUTE FUNCTION incident.reject_append_only_mutation()""")
    op.execute("ALTER TABLE incident.change_events OWNER TO sre_incident_owner")
    op.execute("GRANT SELECT ON incident.change_events TO sre_incident_reader")
    op.execute("GRANT SELECT, INSERT ON incident.change_events TO sre_incident_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE incident.change_events")
