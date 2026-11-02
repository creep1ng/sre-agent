"""Bind each linked chat to the human principal and Telegram user it decides as (issue #767)."""

from alembic import op

revision = "20261030_06"
down_revision = "20261030_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The human named when the code is issued, copied on linking, and the Telegram user who
    # opened it. Chats linked before this revision have neither and can read but never decide.
    op.execute("ALTER TABLE incident.chat_link_codes ADD COLUMN principal_id varchar(64)")
    op.execute("ALTER TABLE incident.chat_links ADD COLUMN principal_id varchar(64)")
    op.execute("ALTER TABLE incident.chat_links ADD COLUMN telegram_user_id bigint")


def downgrade() -> None:
    op.execute("ALTER TABLE incident.chat_links DROP COLUMN telegram_user_id")
    op.execute("ALTER TABLE incident.chat_links DROP COLUMN principal_id")
    op.execute("ALTER TABLE incident.chat_link_codes DROP COLUMN principal_id")
