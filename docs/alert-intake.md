# Alert intake from Grafana

Midnight builds no detection. The user's Grafana evaluates the alert rules and sends what fires
to Midnight by webhook; Midnight records the alert, opens or joins an incident and starts the
investigation, with nobody looking at the console. Issue: #765.

## How it works

- `POST /v1/alert-intake/grafana` receives Grafana Alerting's webhook payload. The contact point
  sends the integration's secret as `Authorization: Bearer <secret>`. The secret is checked
  before the body is read: a missing or wrong one gets `401` and leaves one audit event
  (`credentials.authenticate`, stage `authentication`), nothing else.
- Limits: a body over 512 KiB (by `Content-Length` or by the bytes read), more than 100 alerts,
  more than 64 labels on an alert, a label key over 128 characters or a value over 1024 get
  `413 payload_too_large`; a body that is not a Grafana payload gets `422 invalid_payload`.
- Each alert is an **episode**, keyed by Grafana's `fingerprint` (its label set) and `startsAt`.
  A repeated delivery adds to the same episode (`received_count`); `resolved` closes it, and a
  `firing` that arrives after its `resolved` does not reopen it.
- A new `firing` episode joins the oldest open incident of the **same service** (`triage_link`),
  whoever declared it and even if the episode that opened it already resolved, so a flapping
  rule does not pay for a second investigation. Otherwise it declares an incident through the
  triage command (`triage_declare`), which starts the investigation run (#704); the dispatch runs
  after the response. A redelivery replays the same command and re-dispatches a run still
  pending (the dispatch claim is idempotent).
- The integration acts for one operator principal (`ALERT_INTAKE_PRINCIPAL_ID`, default
  `demo-human`), which needs the triage and run grants the console uses (`scripts/provision_demo.py`
  gives them). The triage decision records `decision_origin: external_automatic` and
  `responsible_system: grafana`, never a manual decision. With `ALERT_INTAKE_PRINCIPAL_ID=`
  (empty), an unknown or inactive operator, or without the grants, the episode is still recorded
  and stays in the inbox as `new` for the console; the journeys that triage a new card by hand
  run that way.
- Severity comes from the alert's `severity` label: `critical` → `sev1`, `warning` → `sev2`,
  `info` → `sev3`; `sev1`–`sev4` pass through; anything else is `sev3`.
- `GET /v1/alerts` (`alert.read`) lists the episodes as canonical alerts with their triage status
  and incident: firing ones in `alerts`, the live view of the console, and those resolved in the
  last day in `resolved`. Midnight evaluates no rule of its own.

Configuration: `ALERT_INTAKE_GRAFANA_SECRET` (empty leaves the route unmounted) and
`AUDIT_HMAC_KEY` on the API; `ALERT_INTAKE_URL` and the same secret in Grafana's environment.

## Episode model

`incident.alert_episodes` (migration `20261030_01`), one row per episode, for consumers such as
the chat channel (#766) and the interruption budget (#771):

| Column | Meaning |
| --- | --- |
| `episode_id` | The alert id the inbox and triage use, `alt-<service>-<hash>` |
| `source`, `fingerprint`, `starts_at` | Unique identity of the episode |
| `rule`, `service`, `severity`, `labels` | `alertname`, `service_name`, the mapped severity and every label |
| `status`, `resolved_at` | `firing` or `resolved`; a resolved episode never fires again, the next firing is a new episode |
| `summary` | The rule's `summary` and `description` annotations at the first delivery |
| `group_key`, `received_count`, `first_received_at`, `last_received_at` | Delivery bookkeeping |
| `incident_id`, `investigation_run_id` | The incident it opened or joined, and the run it started (null when it joined) |

Whether it declared or joined is the triage decision in `alert_triage` (same id).

## Rules

`demo/grafana/alerting/midnight.yaml` provisions the `midnight-intake` contact point and three
generic rules. Each holds for 1 min before it fires; notifications group by
`[alertname, service_name]`, so one service's alert never travels with another's.

| Rule | Signal | Severity | Covers |
| --- | --- | --- | --- |
| `service-error-rate` | span error ratio per `service_name` over 2 min > 5% | critical | `paymentFailure`, `paymentUnreachable`, `cartFailure`, `productCatalogFailure`, `adFailure`, `recommendationCacheFailure`, `failedReadinessProbe` |
| `service-latency-p95` | p95 of server spans per `service_name` over 2 min > 2000 ms | warning | `imageSlowLoad`, `intlShippingSlowdown`, `adHighCpu`, `adManualGc`, `emailMemoryLeak` |
| `sre-checkout-orders-error-rate` | 5xx share of `sre-checkout` orders over 30 s > 10% | warning | the broken `sre-checkout` 1.5.0 release (#721) |

The flag list is the scenario bank of `docs/product-direction-2026-10-28.md`; which flags each
rule actually catches is verified only for the runs recorded in the PR evidence. How the
generic span-error rule behaves on the store's normal traffic has not been measured yet.

## Where the rules run

- **Local demo** (`scripts/demo_env.py` + `compose.demo.yaml`): `up` generates
  `.demo-state/alert-intake.env`; Grafana provisions the rules from `/etc/midnight-provisioning`
  and posts to `http://api:8000` over `sre-mcp-boundary`; `scripts/setup_sre.py` gives the API the
  same secret. See [demo-env](demo-env.md#alert-intake-765).
- **EC2 demo** (`scripts/otel_ec2.py`): `prepare-mcp` provisions the same rules on the instance;
  `connect-mcp` relays the deliveries to the local API. See
  [OTel Demo on EC2](otel-demo-ec2.md#alerts-from-the-instances-grafana-765).
- **Runs for evidence**: `compose.alert-intake.yaml` (below) and the CI journey.

## Runs

Non-interactive, in CI: `scripts/run_real_journeys.sh incidents` ends with
`scripts/alert_intake_journey.py`, which posts Grafana-shaped payloads to the composed API and
checks 401, replay, joining, a grouped payload, resolved before firing, the limits and
`GET /v1/alerts` with its 403.

Real Grafana, by hand: `compose.alert-intake.yaml` adds Grafana 13.1.0 with the same file, a
Prometheus 3.13.1 that receives OTLP with the store's labels, `sre-checkout`, and the runner
`scripts/alert_intake_e2e.py`, which relays Grafana's deliveries to the API and checks intake,
replay, `401`, `resolved` and the time from injection to dispatch. From a worktree with `.env`
from `.env.example`:

```sh
C="docker compose --env-file .env --env-file .env.worktree -f compose.yaml -f compose.alert-intake.yaml -f compose.alert-intake.seed.yaml --profile alert-intake"
$C up -d --build --wait db api web
$C run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
$C run --rm --no-deps -T seed python scripts/provision_demo.py
$C up -d --build prometheus sre-checkout grafana
ALERT_INTAKE_E2E_USER="$(id -u):$(id -g)" ALERT_INTAKE_ARTIFACTS=/tmp/765 $C up -d --build --no-deps alert-intake-e2e
# when the runner logs READY:
DEMO_CHECKOUT_VERSION=1.5.0 $C up -d --build --no-deps sre-checkout
# when it logs RESET:
DEMO_CHECKOUT_VERSION=1.4.0 $C up -d --build --no-deps sre-checkout
$C logs -f alert-intake-e2e   # ends in PASS or FAIL; /tmp/765/alert-intake-e2e.json
$C down -v --remove-orphans
```

## Known limits

- The demo's Grafana grants its anonymous user Admin (upstream), so anyone who reaches Grafana
  can read the contact point and its secret. The secret guards only the demo's intake.
- Every rejected request writes an audit row; there is no rate limit on them yet.
