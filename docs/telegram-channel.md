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

   `scripts/setup_sre.py` starts it for you when `TELEGRAM_BOT_TOKEN` is set, with
   `CONSOLE_PUBLIC_URL` derived as `http://<SRE_PUBLIC_HOST, default 127.0.0.1>:<WEB_PORT>/app/`
   ([setup](setup-sre.md#configuration-contract)). Two optional settings shape the messages:
   - `TELEGRAM_TIMEZONE` (IANA zone, for example `America/Bogota`; default UTC, and the digest's
     zone when `TELEGRAM_DIGEST_TIMEZONE` is empty). Every time in a decision message and its
     edits is in this zone, labelled with its offset («13:46 UTC-5»).
   - `CONSOLE_PUBLIC_URL`, the RC-2 console's base URL. Decision messages and their edits then
     carry a «Ver incidente» button to `<CONSOLE_PUBLIC_URL>/incidentes/<id>`. If Telegram
     refuses the button (it rejects some hosts, such as `localhost`), the gateway sends the
     message again with the link as text, «Ver incidente: <url>».

3. Create a one-time link (15 minutes by default, `--ttl-seconds` from 1 to 86400) for the
   operator's human principal and open it, in a private chat with the bot, from the operator's
   Telegram account:

   ```sh
   docker compose --profile telegram run --rm telegram-gateway \
     python -m sre_agent.chat.telegram link --principal demo-human
   ```

   Telegram sends `/start <code>`. A valid code links the chat and is spent; a used, expired or
   unknown code is rejected. A chat that is not linked gets one "not linked" reply, once.
   Only a private chat links: in a group the code is refused and stays unused, because every
   member would act as one human. The link records the principal (only an active human is
   accepted) and the Telegram user who opened it, for deciding from the chat (#767). Whoever can
   run this command already holds the database and the bot token, so naming the principal grants
   nothing they did not have. Chats linked before #767 have neither and must be linked again.

4. List the linked chats (chat id, link time and principal, no codes) or revoke one; a revoked chat gets no
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
  expected to use, therefore notifies without chat-specific code. Since #771 the
  [interrupt policy](interrupt-policy.md) decides first: an automatic run sends no acknowledgment
  and its conclusion only when it interrupts; the rest goes to the daily digest.
- The gateway sends the oldest due message of each chat, keeping the row locked until the send
  is recorded. A failed send is retried with exponential backoff (up to 60 s, 10 attempts, or the
  wait a 429 asks for); a 400 or 403 is final and logged. `last_error` keeps the method, the HTTP
  status and Telegram's error text. Texts over 3900 characters are cut and point to the console.
- Delivery is at least once; a send interrupted mid-flight may repeat. A stop (20 s grace) lets
  the current send finish, but a send that times out or a gateway killed before its commit is
  sent again, because Telegram has no idempotency key. The dedup key makes duplicates rare.

## Decision messages

- The deferred constraint trigger `run_events_chat_decision` queues one `mitigation_decision`
  message per linked chat when a `propose_mitigation` transition commits, after the dispatch
  conclusion of the same transaction. Its payload binds the incident, the run, the proposal
  (`mitigation_id`), when it was proposed, the incident version the human reviews, the link the
  message went to and a random 32-hex token.
- The message names the incident, the service, the cause (the hypothesis the proposal is based
  on), the suspect change (the service's last deploy within 24 h before the alert), the proposal
  in plain language, its risk and, as a detail, the catalog operation when the proposal has one.
  It is the only message that carries the amber marker 🟠, and only while it waits.
- The callback data is `a:` or `r:` and the token: no incident or run id. A chat linked before
  #767 has no principal, so it gets the message without buttons and a hint to link again.
- Once the proposal is decided, the message says who decided it (the principal's display name),
  from where and when, without buttons and without the marker.

## Editing the decision message

- The gateway keeps the Telegram id of every message it sends (`chat_outbox.telegram_message_id`,
  migration `20261102_01`).
- The trigger `decisions_chat_update` on `incident.decisions` queues one `decision_update` per
  decision message of the incident whenever `apply_mitigation`, `reject_mitigation`,
  `verification_passed` or `verification_failed` is recorded, from any channel: a tap, the
  console or the API. A chat unlinked since gets no edit.
- The gateway renders it when it sends it, as the decision message reads at that moment, and
  sends it as `editMessageText` on the original message, without buttons. A message that was
  never sent is skipped; an edit that changes nothing (the tap already showed it) counts as done.
- After an approval, the stability check adds one line:
  «Resuelto a las 09:33 UTC-5 · 95 s tras la mitigación que aprobaste · ver incidente.» (or
  «aprobada» when another human approved it; «ver la consola» without `CONSOLE_PUBLIC_URL`), or
  «La verificación falló a las 09:33 UTC-5: el incidente vuelve a investigarse.». The elapsed
  time runs from the approval to the check.
- The edit keeps the «Ver incidente» link and drops only the decision buttons.
- The chat writes this recovery text; #723's verifier only moves the incident through
  `verifying` to `resolved` or back to `investigating` (maintainer decision of 2026-11-02).

## Deciding from the chat

- A tap sends `approve_mitigation` or `reject_mitigation` through the same `RunCommandService`
  as `POST /v1/incidents/{id}/runs/{run}/commands`: the link's principal replaces the bearer
  key, and the `run.approve` grant, the attribution check and the runtime are unchanged. The
  decision record names the human and adds `"channel": "telegram"`.
- A tap counts only from the chat and the Telegram user of the link the message was sent to.
  Another chat, another user in the chat, or the same chat after unlinking, even if linked again,
  decides nothing.
- The idempotency key is `telegram-<choice>-<token>`, so a repeated tap replays its first result;
  any other tap carries the reviewed incident version, which is stale once anyone decided. The
  gateway edits the message to say who decided, from where and when, then answers the tap.
- If the incident changed while the proposal still waits, the tap decides nothing: the old
  message loses its buttons and the chat gets the proposal again, bound to the current version.
- Executing an approved operation belongs to #722 and #723; the result is the edit above.

### What stops a chat from deciding

The link is a standing credential for its human, used without an API key:

- It stops: `unlink CHAT_ID` (immediately, and its buttons never come back), deactivating the
  principal (`PUT /v1/principals/{id}/status`, the tap answers that the user is not active) and
  revoking the principal's `run.approve` grant (the tap answers that there is no permission).
- It does not stop: revoking or expiring the principal's API keys. Unlink the chat as well.

## Extending

Other producers call `sre_agent.chat.outbox.enqueue(session, chat_id=..., kind=...,
dedup_key=...)` inside their own transaction. A new message kind is one renderer in `RENDERERS`;
the text is rendered when the message is sent, and a renderer may return an inline keyboard with
it. The interruption budget (#771, digest versus interrupt) builds on this table.

## Verify

`scripts/run_telegram_e2e.sh` runs the channel against the real API and Postgres with a fake Bot
API (`tests/fake_telegram.py`, compose profile `telegram-e2e`) and writes `telegram-e2e.json`,
`summary.txt`, `transcript.png` and `migrate.log`.
