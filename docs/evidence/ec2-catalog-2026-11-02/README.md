# flag.set on the OTel demo on EC2, 2026-11-02 (#724)

The registered action catalog working on the EC2 instance: the agent proposes a catalog
operation, a person approves it, the deploy-executor turns the fault off with no operator
shell, and the signal recovers. Design and limits:
[the deploy-executor](../../deploy-executor.md#flagset-on-the-otel-demo-724).

Branch `t3/724-ec2-catalog-*` on top of `t3/724-base`: the 2026-11-01 integration branch (#924)
merged locally with Camilo's #722 stack (#919–#923), with `20261030_05` re-chained onto
`20261031_01` as the merge train does.

## Local, with the stand-in (`local/`)

`compose.yaml` + `compose.local-flow.yaml` + `compose.local-flow-flags.yaml`: the real API,
console and deploy-executor with the EC2 catalog; the instance's own `mcp_guest.py serve-flags`
as the stand-in listener; a scripted model. The rule `checkout-payment-error-rate` fires while
the stand-in's `paymentUnreachable` is not `off`.

- `checks.json`: the api cannot resolve `otel-flags`; an unsigned `flag.set` gets 401;
  `paymentUnreachable=on` and `loadGeneratorTraffic=off` get 422 `flag_not_allowed`; no flag
  moved. With the listener's token, the listener itself answered 401 to a wrong token and 403
  to `paymentUnreachable=on`, `loadGeneratorTraffic=off` and `paymentFailure=50%`.
- `flow.json`: fault → incident → proposal `flag.set {flag: paymentUnreachable, variant: off}`
  on `checkout` → API approval → receipt `exe_07d6bb70ca42f783` (`flag_set`, `on → off`,
  41 ms) → incident `verifying` → alert resolved 2 s later → timeline «Mitigation approved; the
  deploy-executor ran flag.set on checkout: flag_set (paymentUnreachable → off).»
- `incident.png`: the RC-2 incident page afterwards, captured by `capture.spec.ts` in
  `incident-console-e2e` (`INCIDENT_ID=<id>`, the spec mounted as in
  [the local flow](../integration-2026-11-01/local-flow.md#repeat-the-screenshots)).

## EC2 (`ec2/`)

Instance `i-076cafd377fb62573`, up 19:00:05Z, down 19:30:40Z (30.5 min; the budget guard
accepted `up`). `SRE_OTEL_MODE=aws`, project `sre-ec2cat`, model `anthropic/claude-haiku-5.5` on
provider `anthropic`, fake Telegram not started, approvals through the API as `demo-human`.

| Step | UTC |
| --- | --- |
| `up` | 19:00:05 |
| Store answers through `connect` | 19:06:38 |
| `prepare-mcp` (listener installed) | 19:06:46–19:07:28 |
| `connect-mcp` ready on the first try, subnets `10.231.0.0/24` and `10.231.1.0/24` picked | 19:07:58 |
| `setup_sre.py` (executor and console started; `/app/` answers 200) | 19:08:03–19:09:14 |
| `checks` against the real listener: all pass (`checks.json`) | 19:09:20 |
| **`fail`** (`paymentUnreachable`) | **19:09:31** |
| Incident on `checkout` declared by Grafana's alert | 19:14:36 (+5 min 05 s) |
| Proposal `flag.set paymentUnreachable=off` on `checkout` (real model) | 19:15:08 (+5 min 37 s) |
| API approval → executor receipt `exe_1b7fe1966b715f68` (`flag_set`), incident `verifying` | 19:15:15–19:15:16 |
| `checkout` alert resolved by Grafana | 19:16:30 (74 s after the approval) |
| **`fail --flag paymentFailure`** | **19:17:11** |
| `payment` and `checkout` episodes start | 19:19:30 |
| New investigation of the `payment` incident (see below) | 19:27:41 |
| Proposal `flag.set paymentFailure=off` on `payment` (real model) | 19:28:02 |
| API approval → receipt `exe_ce58c642f38c2bed` (`flag_set`), incident `verifying` | 19:28:10 |
| `payment` and `checkout` episodes resolved (`alerts-after-paymentFailure.txt`) | 19:29:30 (80 s after the approval) |
| `down` | 19:30:40 |

Files: `flow-paymentUnreachable.json`, `flow-paymentFailure.json` (the driver's steps),
`reasoning-paymentUnreachable.json` (hypothesis and evidence: `PaymentService/Charge` errors
inside checkout, mechanism `paymentUnreachable`), `incident.png` (the RC-2 page of the
`checkout` incident), `checks.json`.

**Read `flow-paymentFailure.json`'s step «the alert resolved» with care.** It matched the
19:09 `payment` episode, which had already resolved. The driver now only accepts episodes that
start with the fault. The real resolution is `alerts-after-paymentFailure.txt`.

### What the second fault showed

- `fail` restarted flagd (fixed since: see the next section), and `payment`'s flagd `EventStream` errors fired `service-error-rate`
  for `payment` at 19:09:30. The real model investigated it and asked for a human
  (`request_human`: payment's errors were in `flagd.evaluation.v2.Service/EventStream` and
  `tcp.connect`, and `paymentFailure` was already `off`). That was the right answer.
- That incident stayed open, so the `paymentFailure` alerts at 19:19:30 joined the existing
  incidents instead of opening new ones. Joining starts no investigation. A new run was started
  on the `payment` incident through the API (`POST /v1/incidents/{id}/runs`), and it proposed
  the right flag.

### Cost

14 model calls across the 3 investigations, USD 0.013667 billed, 94 046 tokens, from
`audit_events.consumption`. Two `mitigation.execute` audit events, both `success`/200.
Real-LLM runs: 3 of the 3 the brief allows. The EC2 instance ran 30.5 min of its 2 h TTL.

## flagd reloads; no write restarts it (`flagd-reload/`, `local-reload/`)

The 19:09 `payment` incident came from restarting flagd: `fail`, `reset` and the listener all
ran `docker compose restart flagd` after writing the file. That has been there since
`6469ebde` (2026-10-13), with no reason recorded. The only related finding, checkout's cached
evaluation, is handled by `FLAGD_CACHE=disabled` in the overlay.

The instance runs upstream's flagd service (OTel demo 3.0.0, commit `1755859a`):
`ghcr.io/open-feature/flagd:v0.16.0` (digest `32234e63…`, as `demo/digests.lock` pins it),
`start --uri file:./etc/flagd/demo.flagd.json`, with a directory mounted on `/etc/flagd`.
Upstream mounts `./src/flagd`, which `flagd-ui` writes in place, and our overlay mounts the
guest's working copy instead. `flagd-reload/run.sh` runs that exact image, command and directory
mount locally (`result.txt`):

- flagd 0.16.0's file source is `fileinfo` sync: it polls the file's metadata once a second
  (one `filepath event … WRITE` per change in the log) rather than holding an fsnotify watch.
  An atomic replace (temporary file and `os.replace`, the guest's way) and an in-place write
  (flagd-ui's way) each reach the served value within 0.2–1.0 s. The container keeps its start
  time, with 0 restarts.
- An `EventStream` held open, as the store's providers hold it, receives `configuration_change`
  on a write and stays open. On `docker restart flagd` it receives `provider_shutdown` and
  breaks (`IncompleteRead`). Those are the `flagd.evaluation.v2.Service/EventStream` and
  `tcp.connect` errors that fired `payment` at 19:09.

So `fail`, `reset` and the listener now only replace the file (`replace_flags` in
`mcp_guest.py`), and no warm-up is needed. The stand-in runs that same flagd image on the
listener's directory. `local-reload/flow.json` repeats the local flow with
`FLAGD_ADDRESS=flagd:8013`: flagd served `paymentUnreachable=on` after `fail`, the approved
`flag.set` (`exe_bf0b19b0c3fc9282`) reached flagd within the E2E's 2 s poll, the stream saw
`provider_ready` then `configuration_change` and never broke, and flagd stayed at 0 restarts
with two `WRITE` events (the fault, the fix). The EC2 run above predates this change; the
parent's EC2 rehearsal on `main` checks it on the instance.

Not changed: `scripts/demo_env.py fail`/`reset` (the local OTel demo, not the evaluated one)
still restart flagd.

## Repeat

Local (no AWS), from this branch, after `scripts/bootstrap-worktree.py` and filling `.env` as
in [the local flow](../integration-2026-11-01/local-flow.md#0-one-time-setup):

```sh
export LOCAL_FLOW_DIR=/tmp/724-flow
dc() { scripts/worktree-compose -f compose.local-flow.yaml -f compose.local-flow-flags.yaml "$@"; }
mkdir -p "$LOCAL_FLOW_DIR/otel-state"
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" -v "$LOCAL_FLOW_DIR/otel-state:/state" \
  python:3.12-slim python -I /repo/scripts/local_flow_flags.py /state
dc up --build --wait db api web incident-console otel-flags flagd deploy-executor
dc run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
dc run --rm --no-deps -T seed python scripts/provision_demo.py
K=$(grep ^DEMO_HUMAN_API_KEY .env | cut -d= -f2)
dc exec -T -e DEMO_HUMAN_API_KEY=$K api python - checks < scripts/flag_set_e2e.py > checks.json
dc exec -T otel-flags python /guest/mcp_guest.py fail --flag paymentUnreachable
echo flag:paymentUnreachable > "$LOCAL_FLOW_DIR/checkout-payment-error-rate"
dc exec -T -e DEMO_HUMAN_API_KEY=$K -e DECIDE=api -e FLAGD_ADDRESS=flagd:8013 api python - flow < scripts/flag_set_e2e.py > flow.json
dc --profile e2e down -v --remove-orphans
sh docs/evidence/ec2-catalog-2026-11-02/flagd-reload/run.sh   # flagd 0.16.0 alone
```

EC2: `otel_ec2.py up`, `prepare-mcp`, `connect-mcp --network <net> --intake-url
http://127.0.0.1:<API_PORT>/v1/alert-intake/grafana` (kept running), `setup_sre.py --env-file
<aws env>`, then the same `checks` and `flow` commands through
`docker compose -p <SRE_SETUP_PROJECT> -f compose.yaml -f compose.mcp.yaml -f
$DEMO_STATE_DIR/sre-setup/<project>.json exec api …`, `otel_ec2.py fail`, and `down`.
