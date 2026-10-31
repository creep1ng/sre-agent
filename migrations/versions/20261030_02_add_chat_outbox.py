"""Link chats with one-time codes and queue their messages in a durable outbox (issue #766)."""

from alembic import op

revision = "20261030_02"
down_revision = "20261030_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only the SHA-256 of a code is stored: a database read never yields a usable link.
    op.execute("""CREATE TABLE incident.chat_link_codes (
      code_sha256 char(64) PRIMARY KEY,
      created_at timestamptz NOT NULL,
      expires_at timestamptz NOT NULL,
      used_at timestamptz,
      used_by_chat_id bigint,
      CONSTRAINT ck_chat_link_code_use CHECK ((used_at IS NULL) = (used_by_chat_id IS NULL))
    )""")
    # The allow list: only these chats ever receive incident information.
    op.execute("""CREATE TABLE incident.chat_links (
      chat_id bigint PRIMARY KEY,
      code_sha256 char(64) NOT NULL REFERENCES incident.chat_link_codes(code_sha256),
      linked_at timestamptz NOT NULL
    )""")
    # One row per message and chat; (chat_id, dedup_key) makes every producer idempotent.
    op.execute("""CREATE TABLE incident.chat_outbox (
      message_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      chat_id bigint NOT NULL,
      kind varchar(64) NOT NULL,
      dedup_key varchar(200) NOT NULL,
      payload jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      attempts integer NOT NULL DEFAULT 0,
      next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      sent_at timestamptz,
      last_error varchar(200),
      CONSTRAINT uq_chat_outbox_dedup UNIQUE (chat_id, dedup_key),
      CONSTRAINT ck_chat_outbox_payload CHECK (jsonb_typeof(payload) = 'object')
    )""")
    op.execute(
        "CREATE INDEX ix_chat_outbox_due ON incident.chat_outbox (next_attempt_at) "
        "WHERE sent_at IS NULL"
    )
    # Every dispatch writes an intent receipt when it starts and an outcome receipt when it
    # ends, whichever code path writes them; enqueueing here keeps the message in the same
    # transaction as the receipt.
    op.execute("""CREATE FUNCTION incident.enqueue_dispatch_chat_messages() RETURNS trigger
      LANGUAGE plpgsql AS $$
      DECLARE
        phase text := NEW.payload -> 'dispatch_receipt' ->> 'phase';
        kind text := CASE phase WHEN 'intent' THEN 'investigation_ack'
                                WHEN 'outcome' THEN 'investigation_conclusion' END;
      BEGIN
        IF kind IS NOT NULL THEN
          INSERT INTO incident.chat_outbox (chat_id, kind, dedup_key, payload)
          SELECT chat_id, kind, kind || ':' || NEW.run_id,
                 jsonb_build_object('incident_id', NEW.incident_id, 'run_id', NEW.run_id,
                                    'event_id', NEW.event_id)
          FROM incident.chat_links
          ON CONFLICT (chat_id, dedup_key) DO NOTHING;
        END IF;
        RETURN NULL;
      END $$""")
    op.execute("""CREATE TRIGGER run_events_chat_outbox AFTER INSERT ON incident.run_events
      FOR EACH ROW WHEN (NEW.kind = 'dispatch_receipt')
      EXECUTE FUNCTION incident.enqueue_dispatch_chat_messages()""")
    op.execute(
        "ALTER FUNCTION incident.enqueue_dispatch_chat_messages() OWNER TO sre_incident_owner"
    )
    for table in ("chat_link_codes", "chat_links", "chat_outbox"):
        op.execute(f"ALTER TABLE incident.{table} OWNER TO sre_incident_owner")
        op.execute(f"GRANT SELECT ON incident.{table} TO sre_incident_reader")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON incident.{table} TO sre_incident_runtime")


def downgrade() -> None:
    op.execute("DROP TRIGGER run_events_chat_outbox ON incident.run_events")
    op.execute("DROP FUNCTION incident.enqueue_dispatch_chat_messages()")
    op.execute("DROP TABLE incident.chat_outbox")
    op.execute("DROP TABLE incident.chat_links")
    op.execute("DROP TABLE incident.chat_link_codes")
