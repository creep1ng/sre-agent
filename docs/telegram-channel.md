# Telegram channel

The operator links a Telegram chat once and then receives, in that chat, an acknowledgment when
an investigation is dispatched and its conclusion when it ends (issue #766). The gateway uses
long polling, so it needs no public URL and works behind NAT. When a run waits for a human
decision on a proposed mitigation, the chat also gets one decision message with «Aprobar» and
«Rechazar» buttons (#767). Webhook mode and other channels are out of scope.

## Set up

1. Create a bot with BotFather and put its token in the ignored `.env` as `TELEGRAM_BOT_TOKEN`.
   Never commit, print or attach it. The gateway keeps the `httpx` logger at `WARNING`, because
   that logger would print request URLs, and the token travels in the URL path.
2. Start the gateway with the rest of the stack:

   ```sh
   docker compose --profile telegram up -d --wait telegram-gateway
   ```

3. Create a one-time link (15 minutes by default, `--ttl-seconds` from 1 to 86400) for the
   operator's human principal and open it from the operator's Telegram account:

   ```sh
   docker compose --profile telegram run --rm telegram-gateway \
     python -m sre_agent.chat.telegram link --principal demo-human
   ```

   The code records the principal and the link copies it: the chat decides as that human, under
   that human's grants. Only an active human principal is accepted. Whoever can run this command
   already holds the database and the bot token, so naming the principal here grants nothing
   they did not have. Chats linked before #767 have no principal: they receive messages but a
   tap decides nothing until the chat is linked again.

   Telegram sends `/start <code>`. A valid code links the chat and is spent; a used, expired or
   unknown code is rejected. A chat that is not linked gets one "not linked" reply, once.

4. List the linked chats (chat id, link time and principal, no codes) or revoke one; a revoked
   chat gets no further incident messages, including those still queued, and its taps decide
   nothing. These commands are not audited yet.

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

## Deciding from the chat

- The deferred constraint trigger `run_events_chat_decision` queues one `mitigation_decision`
  message per linked chat when a `propose_mitigation` transition commits, after the dispatch
  conclusion of the same transaction. Its payload binds the incident, the run, the proposal
  (`mitigation_id`), the incident version the human reviews and a random 32-hex token.
- The message names the incident, the service, the cause (the hypothesis the proposal is based
  on), the suspect change (the service's last deploy within 24 h before the alert), the proposal
  in plain language, its risk and, as a detail, the catalog operation when the proposal has one.
  It is the only message that carries the amber marker 🟠, and only while it waits.
- The callback data is `a:` or `r:` and the token: no incident or run id. A tap looks the token
  up for the tapping chat only, so a chat that is not linked, or not the one the message went
  to, decides nothing.
- A tap sends `approve_mitigation` or `reject_mitigation` through the same
  `RunCommandService` as `POST /v1/incidents/{id}/runs/{run}/commands`: the link's principal
  replaces the bearer key, and the `run.approve` grant, the attribution check and the runtime
  are unchanged. The decision record names the human and adds `"channel": "telegram"`.
- The idempotency key is `telegram-<choice>-<token>`, so a repeated tap replays its first
  result; any other tap carries the reviewed incident version, which is stale once anyone
  decided. Either way the gateway answers the tap with the current state and edits the message
  to say who decided, from where and when, without buttons.
- Executing an approved operation and the result message belong to #723 and #722.

## Extending

Other producers call `sre_agent.chat.outbox.enqueue(session, chat_id=..., kind=...,
dedup_key=...)` inside their own transaction. A new message kind is one renderer in `RENDERERS`;
the text is rendered when the message is sent, and a renderer may return an inline keyboard with
it. The interruption budget (#771, digest versus interrupt) builds on this table.

## Verify

`scripts/run_telegram_e2e.sh` runs the channel against the real API and Postgres with a fake Bot
API (`tests/fake_telegram.py`, compose profile `telegram-e2e`) and writes `telegram-e2e.json`,
`summary.txt` and `transcript.png`. Since #767 it also approves, double-taps, taps from a
stranger, taps after a console rejection, rejects, and taps after unlinking.
