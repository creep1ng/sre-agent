"""Create the isolated authoritative incident store."""

from alembic import op

revision = "20260907_06"
down_revision = "20260907_05"
branch_labels = None
depends_on = None

APPEND_ONLY_TABLES = ("decisions", "run_events", "snapshots", "text_context")


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sre_incident_owner') THEN
        CREATE ROLE sre_incident_owner NOLOGIN;
      END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sre_incident_runtime') THEN
        CREATE ROLE sre_incident_runtime NOLOGIN;
      END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='sre_incident_reader') THEN
        CREATE ROLE sre_incident_reader NOLOGIN;
      END IF;
    END $$""")
    op.execute("CREATE SCHEMA incident AUTHORIZATION sre_incident_owner")
    op.execute("REVOKE ALL ON SCHEMA incident FROM PUBLIC")
    op.execute("""CREATE TABLE incident.incidents (
      incident_id varchar(64) PRIMARY KEY,
      state jsonb NOT NULL,
      version bigint NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL,
      updated_at timestamptz NOT NULL,
      CONSTRAINT ck_incident_version CHECK (version >= 0),
      CONSTRAINT ck_incident_lifecycle CHECK (updated_at >= created_at)
    )""")
    op.execute("""CREATE TABLE incident.runs (
      run_id varchar(64) PRIMARY KEY,
      incident_id varchar(64) NOT NULL REFERENCES incident.incidents(incident_id),
      state jsonb NOT NULL,
      version bigint NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL,
      updated_at timestamptz NOT NULL,
      CONSTRAINT uq_incident_runs_identity UNIQUE (incident_id, run_id),
      CONSTRAINT ck_incident_run_version CHECK (version >= 0),
      CONSTRAINT ck_incident_run_lifecycle CHECK (updated_at >= created_at)
    )""")
    op.execute("""CREATE TABLE incident.decisions (
      decision_id varchar(64) PRIMARY KEY,
      incident_id varchar(64) NOT NULL REFERENCES incident.incidents(incident_id),
      run_id varchar(64),
      turn_id varchar(64),
      document jsonb NOT NULL,
      decided_at timestamptz NOT NULL,
      CONSTRAINT fk_incident_decision_run FOREIGN KEY (incident_id, run_id)
        REFERENCES incident.runs(incident_id, run_id)
    )""")
    op.execute("""CREATE TABLE incident.run_events (
      event_id varchar(64) PRIMARY KEY,
      incident_id varchar(64) NOT NULL,
      run_id varchar(64) NOT NULL,
      turn_id varchar(64),
      sequence bigint NOT NULL,
      kind varchar(64) NOT NULL,
      payload jsonb NOT NULL,
      occurred_at timestamptz NOT NULL,
      CONSTRAINT fk_incident_event_run FOREIGN KEY (incident_id, run_id)
        REFERENCES incident.runs(incident_id, run_id),
      CONSTRAINT uq_incident_run_event_sequence UNIQUE (run_id, sequence),
      CONSTRAINT ck_incident_event_sequence CHECK (sequence >= 0)
    )""")
    op.execute("""CREATE INDEX ix_incident_run_events_replay
      ON incident.run_events (run_id, sequence, event_id)""")
    op.execute("""CREATE TABLE incident.snapshots (
      snapshot_id varchar(64) PRIMARY KEY,
      incident_id varchar(64) NOT NULL,
      run_id varchar(64) NOT NULL,
      version bigint NOT NULL,
      event_sequence bigint NOT NULL,
      incident_state jsonb NOT NULL,
      run_state jsonb NOT NULL,
      created_at timestamptz NOT NULL,
      CONSTRAINT fk_incident_snapshot_run FOREIGN KEY (incident_id, run_id)
        REFERENCES incident.runs(incident_id, run_id),
      CONSTRAINT uq_incident_snapshot_version UNIQUE (run_id, version),
      CONSTRAINT uq_incident_snapshot_sequence UNIQUE (run_id, event_sequence),
      CONSTRAINT ck_incident_snapshot_version CHECK (version >= 0),
      CONSTRAINT ck_incident_snapshot_sequence CHECK (event_sequence >= -1)
    )""")
    op.execute("""CREATE TABLE incident.text_context (
      turn_id varchar(64) PRIMARY KEY,
      incident_id varchar(64) NOT NULL,
      run_id varchar(64) NOT NULL,
      task_id varchar(64),
      sequence bigint NOT NULL,
      content jsonb NOT NULL,
      occurred_at timestamptz NOT NULL,
      CONSTRAINT fk_incident_context_run FOREIGN KEY (incident_id, run_id)
        REFERENCES incident.runs(incident_id, run_id),
      CONSTRAINT uq_incident_context_sequence UNIQUE (run_id, sequence),
      CONSTRAINT uq_incident_context_task UNIQUE (run_id, task_id),
      CONSTRAINT ck_incident_context_sequence CHECK (sequence >= 0)
    )""")
    op.execute("""CREATE TABLE incident.transition_commits (
      incident_id varchar(64) NOT NULL REFERENCES incident.incidents(incident_id),
      command_id varchar(128) NOT NULL,
      payload_sha256 varchar(64) NOT NULL,
      result jsonb NOT NULL,
      committed_at timestamptz NOT NULL,
      PRIMARY KEY (incident_id, command_id),
      CONSTRAINT ck_incident_transition_digest
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$')
    )""")
    op.execute("""CREATE FUNCTION incident.reject_append_only_mutation() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
      END $$""")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"""CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE
          ON incident.{table} FOR EACH ROW
          EXECUTE FUNCTION incident.reject_append_only_mutation()""")
    for table in (
        "incidents",
        "runs",
        "decisions",
        "run_events",
        "snapshots",
        "text_context",
        "transition_commits",
    ):
        op.execute(f"ALTER TABLE incident.{table} OWNER TO sre_incident_owner")
    op.execute("ALTER FUNCTION incident.reject_append_only_mutation() OWNER TO sre_incident_owner")
    op.execute("GRANT USAGE ON SCHEMA incident TO sre_incident_runtime, sre_incident_reader")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA incident TO sre_incident_reader")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON incident.incidents, incident.runs TO sre_incident_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON incident.decisions, incident.run_events, "
        "incident.snapshots, incident.text_context, incident.transition_commits "
        "TO sre_incident_runtime"
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA incident CASCADE")
    op.execute("DROP ROLE IF EXISTS sre_incident_reader")
    op.execute("DROP ROLE IF EXISTS sre_incident_runtime")
    op.execute("DROP ROLE IF EXISTS sre_incident_owner")
