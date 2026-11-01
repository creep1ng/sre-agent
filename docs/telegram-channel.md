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
   unknown code is rejected. A chat that is not linked gets one "not linked" reply, once.

4. List the linked chats (chat id and link time, no codes) or revoke one; a revoked chat gets no
   further incident messages, including those still queued. These commands are not audited yet.

   ```sh
   docker compose --profile telegram run --rm telegram-gateway python -m sre_agent.chat.telegram links
   docker compose --profile telegram run --rm telegram-gateway python -m sre_agent.chat.telegram unlink CHAT_ID
   ```

## What leaves your host

Messages carry the incident id, the alert summary and the model's conclusion, which may quote
logs. They travel to Telegram's servers unredacted, and bot chats are not end-to-end encrypted:
link only a chat you would trust with that content.

## How messages are delivered

- `incident.chat_links` is the allow list. Only the SHA-256 of each code is stored.
- `incident.chat_outbox` holds one row per message and chat. `(chat_id, dedup_key)` is unique, so
  replaying a producer never queues the same message twice.
- The `run_events_chat_outbox` trigger queues `investigation_ack` when a dispatch writes its
  intent receipt and `investigation_conclusion` when it writes its outcome receipt, in the same
  transaction. Any dispatch path that writes the dispatch receipts, which #765 (Grafana alerts) is
  expected to use, therefore notifies without chat-specific code.
- The gateway sends the oldest due message of each chat, keeping the row locked until the send
  is recorded. A failed send is retried with exponential backoff (up to 60 s, 10 attempts, or the
  wait a 429 asks for); a 400 or 403 is final and logged. `last_error` keeps the method, the HTTP
  status and Telegram's error text. Texts over 3900 characters are cut and point to the console.
- Delivery is at least once; a send interrupted mid-flight may repeat. A stop (20 s grace) lets
  the current send finish, but a send that times out or a gateway killed before its commit is
  sent again, because Telegram has no idempotency key. The dedup key makes duplicates rare.

## Extending

Other producers call `sre_agent.chat.outbox.enqueue(session, chat_id=..., kind=...,
dedup_key=...)` inside their own transaction. A new message kind is one renderer in `RENDERERS`;
the text is rendered when the message is sent. Approval buttons (#767) and the interruption
budget (#771, digest versus interrupt) build on this table.

## Verify

`scripts/run_telegram_e2e.sh` runs the channel against the real API and Postgres with a fake Bot
API (`tests/fake_telegram.py`, compose profile `telegram-e2e`) and writes `telegram-e2e.json`,
`summary.txt` and `transcript.png`.
