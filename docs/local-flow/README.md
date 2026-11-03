# Local full flow: from a Grafana alert to the decision, on one machine

Everything runs in Docker on one machine, from a checkout of `main`, with no EC2 and no real
Telegram bot:

| Piece | What runs |
| --- | --- |
| API, database, investigator, interrupt policy, intake | real (`api`, `db`) |
| Landing at `/`, RC-2 console at `/app/` | real (`web`, `incident-console`) |
| Telegram gateway | real (`telegram-gateway`), talking to a fake Bot API (`fake-telegram`) |
| Grafana alert rules and Grafana MCP | stand-ins in the API process (`scripts/local_flow_upstreams.py`) |
| Model | scripted (default) or real: `anthropic/claude-haiku-5.5` on provider `anthropic` |

`compose.local-flow.yaml` wires it. Two rules exist: `checkout-orders-error-rate` (service
`sre-checkout`, `critical` → SEV1) and `checkout-payment-error-rate` (service `checkout`). A rule
fires while the file named after it in `$LOCAL_FLOW_DIR` reads `firing`; writing anything else
sends one `resolved`. The stand-in delivers to the API's real `POST /v1/alert-intake/grafana`
every 2 s, as Grafana's webhook contact point does. Its Grafana MCP answers every Prometheus query
with 42 server errors for each firing service; log searches return nothing.

The scripted model always does the same thing: one Prometheus query, a hypothesis citing it, then
the proposal «Revertir el último despliegue de sre-checkout». The real model investigates for real
(recent changes, logs, metrics, the knowledge base of the store) against those stand-in answers.

## 0. One-time setup

From a checkout of `main` (a separate clone or `git worktree` is fine):

```sh
git fetch origin && git switch main
cp .env.example .env
# Fill every <placeholder> in .env with local random values and set the demo model:
docker run --rm -v "$PWD/.env:/env" python:3.13-alpine python -c "
from pathlib import Path; from secrets import token_hex
p = Path('/env'); c = p.read_text()
for role in ('admn', 'demo', 'inci', 'rest', 'exec'):
    c = c.replace('<set-unique-sre_-prefixed-key-with-32-plus-characters>', f'sre_{role}_{token_hex(16)}', 1)
c = c.replace('<lab/model>', 'anthropic/claude-haiku-5.5').replace('<provider>', 'anthropic')
for k in ('audit-hmac-key', 'grafana-intake-secret', 'executor-signing-key'):
    c = c.replace(f'<set-long-random-{k}>', token_hex(32))
p.write_text(c)"
```

`.env` then has `OPENROUTER_TIMEOUT_SECONDS=30` (from `.env.example`) and an empty
`OPENROUTER_API_KEY`. Leave it empty for the scripted model. For the real model, put your
OpenRouter key there (never commit `.env`).

Every command below runs from the checkout root in the same shell, with these variables. The ports
avoid the demo environment's (`188xx`) and the defaults (`8000`, `8080`):

```sh
export COMPOSE_PROJECT_NAME=midnight-local API_PORT=18100 WEB_PORT=18101 POSTGRES_PORT=18102 \
  FAKE_TELEGRAM_PORT=18103 LOCAL_FLOW_DIR=/tmp/midnight-local-flow LOCAL_FLOW_MODEL=scripted
# LOCAL_FLOW_MODEL=real uses OPENROUTER_API_KEY from .env instead of the scripted model.
mkdir -p "$LOCAL_FLOW_DIR"
alias dc='docker compose -f compose.yaml -f compose.local-flow.yaml --profile telegram --profile telegram-e2e'
```

## 1. Start

```sh
dc up --build --wait db api web incident-console fake-telegram telegram-gateway
dc run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
dc run --rm --no-deps -T seed python scripts/provision_demo.py
```

The first build takes a few minutes. `provision_demo.py` creates the human `demo-human` (the
console's key is `DEMO_HUMAN_API_KEY` in `.env`), its grants, and the `deploy-executor`
integration that records deploys.

Link the fake chat (chat id `424242`) to `demo-human`, as tapping «Start» on a real bot link does:

```sh
code=$(dc run --rm --no-deps -T telegram-gateway python -m sre_agent.chat.telegram link \
  --principal demo-human | grep -o 'start=[A-Za-z0-9_-]*' | cut -d= -f2)
dc exec -T fake-telegram python -c "import json, sys, urllib.request as u; u.urlopen(u.Request(
  'http://127.0.0.1:8081/_test/messages', json.dumps({'chat_id': 424242,
  'text': '/start ' + sys.argv[1]}).encode(), {'Content-Type': 'application/json'}))" "$code"
```

The chat transcript, at <http://127.0.0.1:18103/_test/transcript>, shows «Chat vinculado. Te
escribo aquí cuando haga falta tu decisión y te mando un resumen diario de lo demás.»

## 2. Optional: record the deploy that breaks checkout

With the real model, record a deploy first. Without one, the model finds no recent change and
blames something else from the store's knowledge base: in our run it blamed a flagd flag. With
it, the model cites the deploy and proposes rolling it back. The scripted model ignores it. The
deploy goes to the daily digest; it sends no message.

```sh
dc run --rm --no-deps -T seed python -c "
import json, os, urllib.request as u; from datetime import UTC, datetime, timedelta
body = {'source': 'github-actions', 'external_id': 'local-deploy-' + datetime.now(UTC).strftime('%H%M%S'),
        'service': 'sre-checkout', 'kind': 'deploy', 'status': 'succeeded', 'version': '1.5.0',
        'occurred_at': (datetime.now(UTC) - timedelta(minutes=3)).isoformat()}
print(u.urlopen(u.Request('http://api:8000/v1/changes', json.dumps(body).encode(),
  {'Authorization': 'Bearer ' + os.environ['DEPLOY_EXECUTOR_CHANGES_API_KEY'],
   'Content-Type': 'application/json'}, method='POST')).status)"
```

## 3. Make the alert fire, and clear it

```sh
echo firing > "$LOCAL_FLOW_DIR/checkout-orders-error-rate"   # fire
echo ok     > "$LOCAL_FLOW_DIR/checkout-orders-error-rate"   # clear (sends one `resolved`)
```

Firing makes intake record an episode, declare an incident **as Grafana** (actor `system`,
reference `grafana`, never a person) and start the investigation at once. Nobody is messaged
yet: silence is the default.

## 4. Watch it

1. **Landing**: <http://127.0.0.1:18101/>. «Abrir la consola» opens the console.
2. **Console**: <http://127.0.0.1:18101/app/>. Click «Conectar API» and paste
   `DEMO_HUMAN_API_KEY` from `.env`. The key lives only in this tab and is gone after a reload.
   Then open incidents from the inbox, not by reloading.
3. **Inbox**: «Nada te espera.» until the investigation proposes something. About 15 s later with
   the scripted model, or 25 to 45 s with the real one, the amber card «Una decisión te espera.»
   appears with «Revisar y decidir».
4. **Incident page**: «Revisar y decidir» opens `/app/incidentes/<id>`: the hypothesis with its
   underlined claims (hover for the evidence), the timeline and the proposal card with
   «Aprobar» and «Rechazar».

## 5. The Telegram decision message

When the proposal lands while the alert still fires, the interrupt policy decides `interrupt`
and the chat receives **exactly one** message, the decision: «🟠 Decisión pendiente», the
service, the cause, the suspect change (when a deploy was recorded), the proposal, the risk and
two buttons, [Aprobar] and [Rechazar]. Read it at <http://127.0.0.1:18103/_test/transcript>.

If the alert clears before the investigation ends (a spike), the policy sends the result to the
daily digest instead, and no message goes out.

## 6. Decide

**In the console**: «Aprobar» or «Rechazar» on the proposal card. The card turns into
«Aprobada · Tú · hh:mm», and the Telegram message stays as it is.

**In Telegram**: tap a button. With the fake Bot API, this command taps «Aprobar» on the last
decision message (use `Rechazar` to reject):

```sh
dc exec -T fake-telegram python -c "import json, urllib.request as u
base = 'http://127.0.0.1:8081/_test/'
m = [m for m in json.load(u.urlopen(base + 'sent')) if m['buttons']][-1]
data = next(d for row in m['buttons'] for label, d in row if label == 'Aprobar')
u.urlopen(u.Request(base + 'taps', json.dumps({'chat_id': m['chat_id'], 'message_id': m['message_id'],
  'data': data}).encode(), {'Content-Type': 'application/json'}))"
```

The message is edited to «Decisión tomada … Aprobada por Demo human desde Telegram, <hora> UTC.»
and its buttons disappear. The console's card shows «Aprobada · Tú» on its next poll (the page
does not show the channel yet; see #914).

## 7. What happens next

- The approval moves the incident to `verifying` («Recuperación» in the stepper). This stack runs
  no deploy-executor (`DEPLOY_EXECUTOR_URL` is empty), so the investigator proposes no executor
  operation and the mitigation stays `execution_mode: simulated`: **nothing executes the
  rollback**. With an executor configured (#722, on `main`), an approval of a proposal that names
  an operation runs it through the executor, from the console and from Telegram alike.
- Clear the alert (step 3). The episode resolves, and the policy records the recovery
  (`remember`). The incident stays open: verification, resolution and closure have no RC-2 screen
  yet.
- **Postmortem, today**: the RC-1 page `http://127.0.0.1:18101/?view=postmortem&incident_id=<id>`,
  backed by `GET/PUT /v1/incidents/<id>/postmortem` and `POST …/postmortem/reviews`. It works
  only once the incident reaches the `postmortem` state, and getting there takes the verification
  and resolution commands, which the RC-2 console does not offer yet.
- **Daily digest**: the gateway queues it at 08:00 UTC. Queue it now with
  `dc run --rm --no-deps -T telegram-gateway python -m sre_agent.chat.telegram digest`.
  The decisions behind it are in `GET /v1/event-decisions`.

## 8. Reset

```sh
dc --profile e2e down -v --remove-orphans
rm -f "$LOCAL_FLOW_DIR"/*
```

Then start again from step 1. A new alert on a service whose incident is still open joins that
incident instead of opening another, so reset between rehearsals.

## Repeat the screenshots

`capture.spec.ts` (this directory) drives steps 3 to 6 in a browser against the running stack.
It writes the rule file itself, decides in Telegram (`LOCAL_FLOW_DECIDE=telegram`) or in the
console (`console`), and saves the screenshots and `local-flow.json` under
`web/incident-console/e2e/artifacts/local-flow/`:

```sh
dc --profile e2e run --build --rm --no-deps -e LOCAL_FLOW_DECIDE=telegram \
  -v "$PWD/docs/local-flow/capture.spec.ts:/e2e/e2e/local-flow.capture.spec.ts:ro" \
  -v "$LOCAL_FLOW_DIR:/flow" incident-console-e2e \
  sh -c 'npx playwright test e2e/local-flow.capture.spec.ts --reporter=list; s=$?; chown -R '"$(id -u):$(id -g)"' e2e/artifacts; exit $s'
```

## Runs recorded

Under `docs/evidence/local-flow/`, each with its screenshots and `local-flow.json`.

| Directory | Code | Model | Deploy recorded | Decided in | Result |
| --- | --- | --- | --- | --- | --- |
| `2026-11-02-scripted/` | `main` after the 2026-11-02 merge train, plus this tooling | scripted | no | Telegram | Passed in 43 s. 16 s from firing to the inbox card; one Telegram message, the decision; tap approved; inbox empty again after clearing. `decisions.txt`: `triage_declare` and `start_investigation` by `system`/`grafana`, `apply_mitigation` by `demo-human` on channel `telegram`; policy rows `alert remember` → `investigation interrupt (sustained_pending_decision)` → `resolution remember`. |
| `2026-11-01/scripted/` | integration branch (#924) | scripted | no | Telegram | Passed in 43 s. 15 s from firing to the inbox card; one Telegram message, the decision; tap approved; inbox empty again after clearing. |
| `2026-11-01/scripted-console/` | integration branch (#924) | scripted | no | console | Passed in 29 s. Card shows «Aprobada · Tú». |
| `2026-11-01/real-no-deploy/` | integration branch (#924) | real (`anthropic/claude-haiku-5.5`) | no | console | 45 s to the inbox card. The model checked recent changes (none), logs (empty) and metrics (42 errors), then blamed the `paymentUnreachable` flag from the knowledge base and proposed turning it off. One Telegram message. |
| `2026-11-01/real-with-deploy/` | integration branch (#924) | real | yes, `sre-checkout` 1.5.0 | Telegram | The hypothesis cites the deploy and the 42 errors and proposes reverting 1.5.0 (risk medium). The message names «Cambio sospechoso: despliegue 1.5.0». The tap approved it. The inbox card did not show in this run, because of the latest-run tie that #956 fixed. Its screenshots were taken afterwards from the stored incident; the model was not called again. |

The 2026-11-01 runs used two real-LLM runs, $0.00758 in total ($0.00173 and $0.00585, from OpenRouter's key usage before
and after). In every run: the triage decision and the `triage_declare` transition are
`system`/`grafana`, the policy rows are `alert remember` → `investigation interrupt
(sustained_pending_decision)` → `resolution remember`, and the outbox holds one
`mitigation_decision` and the link confirmation.