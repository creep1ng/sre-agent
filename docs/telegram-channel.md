# Telegram channel

The operator links a Telegram chat once and then receives, in that chat, an acknowledgment when
an investigation is dispatched and its conclusion when it ends (issue #766). The gateway uses
long polling, so it needs no public URL and works behind NAT. Webhook mode, other channels and
decision buttons (#767) are out of scope.

## Set up

1. Create a bot with BotFather and put its token in the ignored `.env` as `TELEGRAM_BOT_TOKEN`.
   Never commit, print or attach it. The gateway keeps the `httpx` logger at `WARNING`, because
   that logger would print request URLs, and the token travels in the URL path.
2. Start the gateway with the rest of the stack:

   ```sh
   docker compose --profile telegram up -d --wait telegram-gateway
   ```

3. Create a one-time link (15 minutes by default, `--ttl-seconds` from 1 to 86400) and open it
   from the operator's Telegram account:

   ```sh
   docker compose --profile telegram run --rm telegram-gateway \
     python -m sre_agent.chat.telegram link
   ```

   Telegram sends `/start <code>`. A valid code links the chat and is spent; a used, expired or
   unknown code is rejected. A chat that is not linked only gets a "not linked" reply.

## How messages are delivered

- `incident.chat_links` is the allow list. Only the SHA-256 of each code is stored.
- `incident.chat_outbox` holds one row per message and chat. `(chat_id, dedup_key)` is unique, so
  replaying a producer never queues the same message twice.
- The `run_events_chat_outbox` trigger queues `investigation_ack` when a dispatch writes its
  intent receipt and `investigation_conclusion` when it writes its outcome receipt, in the same
  transaction. Any code path that dispatches an investigation, including Grafana alerts (#765),
  therefore notifies without chat-specific code.
- The gateway sends the oldest due message of each chat, keeping the row locked until the send
  is recorded. A failed send is retried with exponential backoff (up to 60 s, 10 attempts) and
  `last_error` keeps the method and HTTP status only. Stopping the gateway lets it finish the
  current send, so a restart delivers each pending message once. A gateway killed between a
  send and its commit sends that message again: delivery is at least once in that window.

## Extending

Other producers call `sre_agent.chat.outbox.enqueue(session, chat_id=..., kind=...,
dedup_key=...)` inside their own transaction. A new message kind is one renderer in `RENDERERS`;
the text is rendered when the message is sent. Approval buttons (#767) and the interruption
budget (#771, digest versus interrupt) build on this table.

## Verify

`scripts/run_telegram_e2e.sh` runs the channel against the real API and Postgres with a fake Bot
API (`tests/fake_telegram.py`, compose profile `telegram-e2e`) and writes `telegram-e2e.json`,
`summary.txt` and `transcript.png`.
