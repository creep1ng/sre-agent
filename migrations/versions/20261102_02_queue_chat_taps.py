"""Run a Telegram tap through the API's approval path, not the gateway's (#722, #767).

A one-tap approval used to execute the command inside the internet-facing Telegram gateway, which
holds no executor key, so a mitigation with a catalog operation moved to `verifying` while nothing
ran. The gateway now only records the tap it verified (chat, Telegram user, token): one row here.
The API claims it and sends the command as the linked human through `RunCommandService`, the same
path as the console (catalog and grant checks, the signed executor call, its audit and timeline),
and writes the outcome back. The gateway answers the tap from that outcome; the decision message
is edited from the outbox.
"""

from alembic import op

revision = "20261102_02"
down_revision = "20261102_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per distinct tap: a repeated tap of the same button has the same idempotency key
    # and waits for the same outcome. `body` is the run command as the console would send it.
    op.execute("""CREATE TABLE incident.chat_taps (
      tap_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      idempotency_key varchar(128) NOT NULL,
      chat_id bigint NOT NULL,
      decision_message_id bigint NOT NULL REFERENCES incident.chat_outbox(message_id),
      principal_id varchar(64) NOT NULL,
      incident_id varchar(64) NOT NULL,
      run_id varchar(64) NOT NULL,
      body jsonb NOT NULL,
      queued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      claimed_at timestamptz,
      attempts integer NOT NULL DEFAULT 0,
      done_at timestamptz,
      status_code integer,
      error_code varchar(64),
      CONSTRAINT uq_chat_tap_key UNIQUE (idempotency_key),
      CONSTRAINT ck_chat_tap_outcome CHECK ((done_at IS NULL) = (status_code IS NULL)),
      CONSTRAINT ck_chat_tap_body CHECK (jsonb_typeof(body) = 'object')
    )""")
    op.execute("CREATE INDEX ix_chat_taps_due ON incident.chat_taps (tap_id) WHERE done_at IS NULL")
    op.execute("ALTER TABLE incident.chat_taps OWNER TO sre_incident_owner")
    op.execute("GRANT SELECT ON incident.chat_taps TO sre_incident_reader")
    op.execute("GRANT SELECT, INSERT, UPDATE ON incident.chat_taps TO sre_incident_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE incident.chat_taps")
