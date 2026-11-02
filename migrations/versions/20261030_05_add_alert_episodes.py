"""Record the alert episodes Grafana delivers by webhook (issue #765).

One row per episode: a Grafana fingerprint (the alert's label set) and the instant it started
firing. A repeated delivery updates the same row; `resolved` closes it. The table lives in the
incident schema so it references the incident it opened or joined, and the test resets that
drop the schema clear it too.
"""

from alembic import op

revision = "20261030_05"
down_revision = "20261030_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE incident.alert_episodes (
      episode_id varchar(64) PRIMARY KEY,
      source varchar(32) NOT NULL,
      fingerprint varchar(128) NOT NULL,
      starts_at timestamptz NOT NULL,
      rule varchar(200) NOT NULL,
      service varchar(200) NOT NULL,
      severity varchar(8) NOT NULL,
      status varchar(16) NOT NULL,
      summary text NOT NULL,
      labels jsonb NOT NULL,
      group_key text,
      received_count integer NOT NULL,
      first_received_at timestamptz NOT NULL,
      last_received_at timestamptz NOT NULL,
      resolved_at timestamptz,
      incident_id varchar(64) REFERENCES incident.incidents(incident_id),
      investigation_run_id varchar(64),
      CONSTRAINT uq_alert_episode UNIQUE (source, fingerprint, starts_at),
      CONSTRAINT ck_alert_episode_status CHECK (status IN ('firing', 'resolved')),
      CONSTRAINT ck_alert_episode_severity CHECK (severity IN ('sev1', 'sev2', 'sev3', 'sev4')),
      CONSTRAINT ck_alert_episode_count CHECK (received_count >= 1)
    )""")
    op.execute(
        "CREATE INDEX ix_alert_episodes_last_received ON incident.alert_episodes (last_received_at)"
    )
    op.execute("ALTER TABLE incident.alert_episodes OWNER TO sre_incident_owner")
    op.execute("GRANT SELECT ON incident.alert_episodes TO sre_incident_reader")
    op.execute("GRANT SELECT, INSERT, UPDATE ON incident.alert_episodes TO sre_incident_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE incident.alert_episodes")
