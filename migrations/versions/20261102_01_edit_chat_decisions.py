"""Edit the chat's decision message on every decision and on recovery (#767, #723).

A mitigation decided in the console or the API used to leave the Telegram message with live
buttons. The bot now keeps the Telegram id of every message it sends, and each decision on the
mitigation or its verification (`apply_mitigation`, `reject_mitigation`, `verification_passed`,
`verification_failed`), whatever the channel, queues one `decision_update` per decision message
of that incident. The gateway renders it when it sends it, so it always shows the current state.
An edit changes a message the person already has: it is not an interrupt, so the policy of
20261030_08 does not gate it.
"""

from alembic import op

revision = "20261102_01"
down_revision = "20261030_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE incident.chat_outbox ADD COLUMN telegram_message_id bigint")
    op.execute(
        "CREATE INDEX ix_chat_outbox_decision_incident ON incident.chat_outbox "
        "((payload ->> 'incident_id')) WHERE kind = 'mitigation_decision'"
    )
    # Only messages sent to a chat that is still linked through the same link: unlinking stops
    # the edits as it stops the taps.
    op.execute("""CREATE FUNCTION incident.enqueue_decision_updates() RETURNS trigger
      LANGUAGE plpgsql AS $$
      BEGIN
        INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
        SELECT m.chat_id, 'decision_update',
               'decision_update:' || m.message_id || ':' || NEW.decision_id,
               jsonb_build_object('target', m.message_id, 'incident_id', NEW.incident_id,
                                  'decision_id', NEW.decision_id)
        FROM incident.chat_outbox m
        JOIN incident.chat_links l
          ON l.chat_id = m.chat_id AND l.code_sha256 = m.payload ->> 'link'
        WHERE m.kind = 'mitigation_decision' AND m.payload ->> 'incident_id' = NEW.incident_id
        ON CONFLICT (chat_id, dedup_key) DO NOTHING;
        RETURN NULL;
      END $$""")
    op.execute("ALTER FUNCTION incident.enqueue_decision_updates() OWNER TO sre_incident_owner")
    op.execute("""CREATE TRIGGER decisions_chat_update AFTER INSERT ON incident.decisions
      FOR EACH ROW WHEN (NEW.document ->> 'transition_id' IN ('apply_mitigation',
        'reject_mitigation', 'verification_passed', 'verification_failed'))
      EXECUTE FUNCTION incident.enqueue_decision_updates()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER decisions_chat_update ON incident.decisions")
    op.execute("DROP FUNCTION incident.enqueue_decision_updates()")
    op.execute("DELETE FROM incident.chat_outbox WHERE kind = 'decision_update'")
    op.execute("DROP INDEX incident.ix_chat_outbox_decision_incident")
    op.execute("ALTER TABLE incident.chat_outbox DROP COLUMN telegram_message_id")
