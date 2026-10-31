"""Bind linked chats to a human and ask them for mitigation decisions (issue #767)."""

from alembic import op

revision = "20261030_767"
down_revision = "20261030_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The human principal a chat decides as: named when the code is issued, copied on linking.
    # Chats linked before this revision have none and can read but never decide.
    op.execute("ALTER TABLE incident.chat_link_codes ADD COLUMN principal_id varchar(64)")
    op.execute("ALTER TABLE incident.chat_links ADD COLUMN principal_id varchar(64)")
    # One decision message per linked chat and proposal. The token is the opaque callback data;
    # the incident version is the one the human reviews, so a decision taken meanwhile in the
    # console makes the tap stale instead of deciding twice. Deferred to the commit, so the
    # dispatch conclusion of the same transaction is queued first.
    op.execute("""CREATE FUNCTION incident.enqueue_mitigation_decision() RETURNS trigger
      LANGUAGE plpgsql AS $$
      DECLARE
        mitigation text := NEW.payload -> 'incident_state' -> 'mitigation_strategy'
                           ->> 'mitigation_id';
      BEGIN
        INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
        SELECT chat_id, 'mitigation_decision',
               'mitigation_decision:' || NEW.run_id || ':' || mitigation,
               jsonb_build_object('incident_id', NEW.incident_id, 'run_id', NEW.run_id,
                 'mitigation_id', mitigation,
                 'token', replace(gen_random_uuid()::text, '-', ''),
                 'incident_version', (SELECT version FROM incident.incidents
                                      WHERE incident_id = NEW.incident_id))
        FROM incident.chat_links
        ON CONFLICT (chat_id, dedup_key) DO NOTHING;
        RETURN NULL;
      END $$""")
    op.execute("ALTER FUNCTION incident.enqueue_mitigation_decision() OWNER TO sre_incident_owner")
    op.execute("""CREATE CONSTRAINT TRIGGER run_events_chat_decision
      AFTER INSERT ON incident.run_events DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW WHEN (NEW.kind = 'state_change'
                         AND NEW.payload ->> 'transition_id' = 'propose_mitigation')
      EXECUTE FUNCTION incident.enqueue_mitigation_decision()""")
    op.execute(
        "CREATE INDEX ix_chat_outbox_decision_token ON incident.chat_outbox "
        "((payload ->> 'token')) WHERE kind = 'mitigation_decision'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX incident.ix_chat_outbox_decision_token")
    op.execute("DROP TRIGGER run_events_chat_decision ON incident.run_events")
    op.execute("DROP FUNCTION incident.enqueue_mitigation_decision()")
    op.execute("ALTER TABLE incident.chat_links DROP COLUMN principal_id")
    op.execute("ALTER TABLE incident.chat_link_codes DROP COLUMN principal_id")
