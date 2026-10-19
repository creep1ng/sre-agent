"""Persist the versioned postmortem artifact and its human reviews (issue #335)."""

from alembic import op

revision = "20261018_01"
down_revision = "20261009_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The head row names the current version; revisions and reviews are append-only,
    # so an edit never destroys the version a reviewer approved.
    op.execute("""CREATE TABLE incident.postmortems (
      postmortem_id varchar(64) PRIMARY KEY,
      incident_id varchar(64) NOT NULL REFERENCES incident.incidents(incident_id),
      version bigint NOT NULL,
      run_ids jsonb NOT NULL,
      created_at timestamptz NOT NULL,
      updated_at timestamptz NOT NULL,
      CONSTRAINT uq_incident_postmortem UNIQUE (incident_id),
      CONSTRAINT ck_postmortem_id CHECK (postmortem_id ~ '^pm_[a-z0-9_-]{1,60}$'),
      CONSTRAINT ck_postmortem_version CHECK (version >= 1),
      CONSTRAINT ck_postmortem_run_ids CHECK (jsonb_typeof(run_ids) = 'array')
    )""")
    op.execute("""CREATE TABLE incident.postmortem_revisions (
      postmortem_id varchar(64) NOT NULL REFERENCES incident.postmortems(postmortem_id),
      version bigint NOT NULL,
      content jsonb NOT NULL,
      edited_by varchar(64) NOT NULL,
      edited_at timestamptz NOT NULL,
      PRIMARY KEY (postmortem_id, version)
    )""")
    op.execute("""CREATE TABLE incident.postmortem_reviews (
      postmortem_id varchar(64) NOT NULL,
      version bigint NOT NULL,
      sequence bigint GENERATED ALWAYS AS IDENTITY,
      outcome varchar(32) NOT NULL,
      reviewer_id varchar(64) NOT NULL,
      comment text,
      reviewed_at timestamptz NOT NULL,
      PRIMARY KEY (postmortem_id, sequence),
      CONSTRAINT fk_postmortem_review_revision FOREIGN KEY (postmortem_id, version)
        REFERENCES incident.postmortem_revisions(postmortem_id, version),
      CONSTRAINT ck_postmortem_review_outcome
        CHECK (outcome IN ('approved', 'changes_requested'))
    )""")
    for table in ("postmortem_revisions", "postmortem_reviews"):
        op.execute(f"""CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE
          ON incident.{table} FOR EACH ROW
          EXECUTE FUNCTION incident.reject_append_only_mutation()""")
    for table in ("postmortems", "postmortem_revisions", "postmortem_reviews"):
        op.execute(f"ALTER TABLE incident.{table} OWNER TO sre_incident_owner")
        op.execute(f"GRANT SELECT ON incident.{table} TO sre_incident_reader")
    op.execute("GRANT SELECT, INSERT, UPDATE ON incident.postmortems TO sre_incident_runtime")
    op.execute(
        "GRANT SELECT, INSERT ON incident.postmortem_revisions, incident.postmortem_reviews "
        "TO sre_incident_runtime"
    )


def downgrade() -> None:
    op.execute("DROP TABLE incident.postmortem_reviews")
    op.execute("DROP TABLE incident.postmortem_revisions")
    op.execute("DROP TABLE incident.postmortems")
