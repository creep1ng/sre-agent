"""Index each closed incident's approved postmortem as a recallable memory (issue #773)."""

from alembic import op

revision = "20261030_04"
down_revision = "20261030_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per closed incident, written with the close. The row is the memory change log:
    # what entered (content), when (indexed_at) and from which incident, postmortem version and
    # close event. The foreign key to the approved revision is the source record a citation needs.
    op.execute("""CREATE TABLE incident.incident_memories (
      memory_id varchar(64) PRIMARY KEY,
      incident_id varchar(64) NOT NULL REFERENCES incident.incidents(incident_id),
      postmortem_id varchar(64) NOT NULL,
      postmortem_version bigint NOT NULL,
      close_event_id varchar(64) NOT NULL REFERENCES incident.run_events(event_id),
      service varchar(200) NOT NULL,
      signal varchar(200),
      content text NOT NULL,
      indexed_at timestamptz NOT NULL,
      CONSTRAINT uq_incident_memory UNIQUE (incident_id),
      CONSTRAINT fk_incident_memory_source FOREIGN KEY (postmortem_id, postmortem_version)
        REFERENCES incident.postmortem_revisions(postmortem_id, version),
      CONSTRAINT ck_incident_memory_id CHECK (memory_id ~ '^mem_[a-z0-9]{16}$'),
      CONSTRAINT ck_incident_memory_content CHECK (length(content) BETWEEN 1 AND 6000)
    )""")
    # The BoK's lexical search (docs/bok-retrieval.md): English full text, filtered by service.
    op.execute("""CREATE INDEX ix_incident_memories_content ON incident.incident_memories
      USING gin (to_tsvector('english', content))""")
    op.execute("CREATE INDEX ix_incident_memories_service ON incident.incident_memories (service)")
    op.execute("""CREATE TRIGGER incident_memories_append_only BEFORE UPDATE OR DELETE
      ON incident.incident_memories FOR EACH ROW
      EXECUTE FUNCTION incident.reject_append_only_mutation()""")
    op.execute("ALTER TABLE incident.incident_memories OWNER TO sre_incident_owner")
    op.execute("GRANT SELECT ON incident.incident_memories TO sre_incident_reader")
    op.execute("GRANT SELECT, INSERT ON incident.incident_memories TO sre_incident_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE incident.incident_memories")
