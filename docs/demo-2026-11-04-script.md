# Demo script for 2026-11-04

How to run the evaluated demo end to end on `main` against the OTel Demo on EC2: a fault opens an
incident with nobody at the console, the agent names the flag, a person approves in Telegram, the
executor turns the fault off, the agent verifies, a model drafts the postmortem and the person
closes it. The decisions behind this path are in
[the sixth and seventh rounds](product-direction-2026-10-28.md#sixth-round-of-decisions-2026-11-02-and-2026-11-03);
the path's last recorded runs are in [the demo candidate](evidence/demo-candidate-2026-11-02/README.md).

Run `mkdir -p /tmp/demo-reset` once; the commands below keep their private files there.

Placeholders: `$ENV` is the private env file, `$STATE` a fresh absolute state directory, `$NET`
the MCP network (`sre-` prefix), `$P` the Compose project (`SRE_SETUP_PROJECT`), `$MCP_PORT` the
`connect-mcp` local port (it also uses `+2` and `+3`), `$API_PORT` and `$WEB_PORT` the env file's
ports. Never paste their secret values, the instance's address, the account id or a chat id into
notes, captures or this doc.

## Setup

1. **The instance.** `export OTEL_DEMO_EXPECTED_ACCOUNT_ID=$(cat ~/.config/sre-agent/otel-account)`,
   then `python3 scripts/otel_ec2.py status`. If an instance is already up, someone else owns it.
   Otherwise `up`, then `prepare-mcp` (a new instance always needs it before `connect-mcp`). See
   [OTel Demo on EC2](otel-demo-ec2.md) for the TTL; `extend` keeps the session under 4 h in total.
2. **The env file.** Besides the keys of [the setup guide](setup-sre.md#prepared-aws-connection):

   ```text
   SRE_OTEL_MODE=aws
   DEMO_STATE_DIR=$STATE
   SRE_MCP_NETWORK=$NET
   SRE_SETUP_PROJECT=$P
   SRE_ENABLE_PAID_LLM=1
   OPENROUTER_API_KEY=<the model key, removed again at teardown>
   TELEGRAM_BOT_TOKEN=<the demo bot>
   ```

   `VERIFICATION_DELAY_SECONDS` (150) and `POSTMORTEM_DRAFT` (`agent`) keep compose's defaults.
3. **The MCP connection, before setup.** In its own terminal:

   ```sh
   python3 scripts/otel_ec2.py connect-mcp --state-dir "$STATE" --network "$NET" \
     --local-port "$MCP_PORT" --intake-url "http://127.0.0.1:$API_PORT/v1/alert-intake/grafana"
   ```

   `$STATE` must be a new directory for each new instance: an old `connection.json` from another
   instance or network stops it with "AWS contract conflict". Setup needs what it creates (the
   networks `$NET` and `$NET-flags`, `flag-write.env`, `connection.json`), so it runs first.
4. **SRE.** `python3 scripts/setup_sre.py --env-file "$ENV"`. It must print "paid LLM explicitly
   enabled" and start `telegram-gateway`. The first time, link the chat to `demo-human` as in
   [the Telegram channel](telegram-channel.md#set-up); the reset below keeps that link.
5. **The store tunnel.** In its own terminal:
   `python3 scripts/otel_ec2.py connect --local-port 18690 --remote-port 8090`. The store is
   `http://127.0.0.1:18690/`, Grafana `/grafana/`, the flags `/feature/`.
6. **One gateway.** Only one Telegram gateway may poll the bot. `docker ps --format '{{.Names}}' |
   grep telegram-gateway` must list only `$P`'s; stop any other that uses the same bot first.
7. **The store answers.** Before any fault, `curl -fsS -o /dev/null -w '%{http_code}\n'
   http://127.0.0.1:18690/` through `connect` must print `200`. See below if it does not.

### A partial boot

On a fresh instance the bootstrap's `docker compose up` can abort while `opensearch` is still
unhealthy ("dependency failed to start: container opensearch is unhealthy" in
`/var/log/cloud-init-output.log`). Only part of the store runs: `frontend`, `frontend-proxy`,
`payment`, `cart` and others never start, and the store tunnel answers "Connection to destination
port failed". Start only the missing services, with `--no-deps` so `prepare-mcp`'s Grafana and
MCP changes stay, through SSM with the operator profile. `AWS-RunShellScript` runs `sh`, so the
script calls `bash`:

```sh
INSTANCE=$(python3 scripts/otel_ec2.py status | python3 -c 'import json,sys; print(json.load(sys.stdin)["instance_id"])')
ssm_bash() {  # runs its argument with bash on the instance and prints what it wrote
  python3 -c 'import json,shlex,sys; print(json.dumps({"commands": ["bash -c " + shlex.quote(sys.argv[1])]}))' \
    "$1" > /tmp/demo-reset/ssm.json
  CMD=$(aws --profile otel-demo --region us-east-1 ssm send-command --instance-ids "$INSTANCE" \
    --document-name AWS-RunShellScript --parameters file:///tmp/demo-reset/ssm.json \
    --query Command.CommandId --output text)
  aws --profile otel-demo --region us-east-1 ssm wait command-executed --command-id "$CMD" --instance-id "$INSTANCE"
  aws --profile otel-demo --region us-east-1 ssm get-command-invocation --command-id "$CMD" \
    --instance-id "$INSTANCE" --query '[StandardOutputContent,StandardErrorContent]' --output text
}
C='cd /opt/otel-demo && docker compose -p otel-demo --env-file .env --env-file demo.env -f compose.yaml -f compose.observability.yaml'
ssm_bash "$C ps -a --format '{{.Service}} {{.State}}'"
# Name exactly the services the list shows as not running, for example:
ssm_bash "$C up -d --no-deps --pull never --no-build frontend frontend-proxy payment cart"
```

Then repeat the `curl` check. Keep `$INSTANCE` and the command output out of notes and captures.

### Keep the tunnels alive

SSM tunnels end after about 25 idle minutes. Run `connect` and `connect-mcp` under a small loop
that restarts each one when it exits, one loop per terminal, for example:

```sh
while :; do
  python3 scripts/otel_ec2.py connect-mcp --state-dir "$STATE" --network "$NET" \
    --local-port "$MCP_PORT" --intake-url "http://127.0.0.1:$API_PORT/v1/alert-intake/grafana"
  echo "$(date -u +%T) connect-mcp exited, restarting" >&2
  docker rm -f "$NET-link" "$NET-flags-link" 2>/dev/null
  sleep 5
done
```

The same loop with `connect --local-port 18690 --remote-port 8090` (no `docker rm`) keeps the
store tunnel. A restart reuses `$STATE` (same instance, same network). Ctrl-C stops a loop
(press it again if it restarted the command). The loop prints no secret; do not add `set -x`.

## Between runs

A new alert joins the oldest open incident of the same service, so each run starts from an empty
database. The reset keeps the Telegram link:

```sh
docker exec "$P-db-1" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --data-only \
  --table=incident.chat_link_codes --table=incident.chat_links' > /tmp/demo-reset/chat-links.sql
docker compose -p "$P" down -v
python3 scripts/setup_sre.py --env-file "$ENV"
docker exec -i "$P-db-1" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < /tmp/demo-reset/chat-links.sql
```

`down -v` acts on `$P` only, never on another project. The networks `$NET` and `$NET-flags` are
external to it and stay. The dump holds only code hashes, chat ids and principals: keep it out of
the repo and delete it after the demo. If the fault is still on, `python3 scripts/otel_ec2.py
reset` first.

## The walk

| # | Do | Expect | Plan B |
| --- | --- | --- | --- |
| 1 | Open `http://127.0.0.1:$WEB_PORT/app/acciones`. | `checkout · flag.set` with `flag ∈ {paymentFailure, paymentUnreachable}` and `variant = off`: nothing else may run, and nothing runs without approval. | |
| 2 | `python3 scripts/otel_ec2.py fail` (`paymentUnreachable`). Close the console. | On the store, Place Order leaves you on the cart. Grafana's rule fires and the incident opens with nobody at the console; on 2026-10-31 that took 103.5 s and 164.9 s after `paymentFailure` ([record](evidence/issue-765/ec2-paymentfailure.json)). | No incident: check that both loops run (the alert relay is `$MCP_PORT + 2`), then Grafana's Alerting → Alert rules. |
| 3 | Open the inbox, `/app/`, then the incident. | The agent's title (for example «Fallan los cobros en checkout») and its hypothesis with the evidence it measured. | Run stopped without a proposal: «Reintentar la investigación» on the incident page. |
| 4 | Telegram. | One decision message: proposal `flag.set paymentUnreachable=off` on `checkout`, with «Aprobar»; the same proposal in the inbox, in amber. | A wrong flag is refused and the run measures again (#996). No message: approve from the inbox. |
| 5 | Tap «Aprobar». | The message is edited: «Aprobada por … desde Telegram, HH:MM UTC.», buttons gone. The incident page shows the receipt, `paymentUnreachable` → `off`; the incident is verifying. | |
| 6 | Wait 150 s. | The agent verifies over the window after the mitigation ran: «Servicio verificado estable», «Resuelto», and the Telegram message is edited again: «Resuelto a las … · … tras la mitigación que aprobaste · ver la consola.» | No verdict, or the verifier asks for a person (in the 2026-11-03 rehearsal it lacked the current time; a fix is in progress): «El servicio está estable» on the incident page moves it to «Resuelto». It did at 16:04 UTC that day, and the model's draft appeared 9 s later. Verification failed: the system investigates again (twice at most), then Telegram says a person is needed. |
| 7 | Read the postmortem on the incident page. | The draft labelled «Borrador del agente», with the agent's title. | «Borrador desde el registro» means the model call failed and the record's draft stands in; it is labelled, continue. |
| 8 | «Aprobar y cerrar». | The closing timeline and «Cerrado». | The previous console's postmortem: `http://127.0.0.1:$WEB_PORT/?view=postmortem&incident_id=<id>`. |

Grafana's anonymous user is Admin upstream, so the contact point's secret is readable through the
store tunnel: show dashboards or alert rules, never Alerting → Contact points. Known limitations
of this demo: no inline editing or Markdown export of the postmortem, no "request changes" (#709),
and the title stays in Spanish when the console is in English.

## Teardown

1. Stop SRE: `python3 scripts/setup_sre.py --env-file "$ENV" --down` (keeps the volume and the
   chat link), or `docker compose -p "$P" down -v` to drop it.
2. Ctrl-C both loops. Check with `ps -eo pid,args | grep '[o]tel_ec2.py conn'`; do not `pkill -f`
   a pattern from a shell whose own command line contains it.
3. Remove the relays and their networks, which `docker network rm` refuses while a relay runs:
   `docker rm -f "$NET-link" "$NET-flags-link"`, then `docker network rm "$NET" "$NET-flags"`.
4. `python3 scripts/otel_ec2.py down`, then `status` to confirm the instance is gone.
5. Remove `OPENROUTER_API_KEY` from `$ENV` and set `SRE_ENABLE_PAID_LLM=0`. Delete
   `/tmp/demo-reset`. Restart any Telegram gateway you stopped in step 6 of the setup.
