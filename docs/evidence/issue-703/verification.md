# Issue 703 live verification: declare, dismiss and conflict from the live card

Browser runs of the new console (`/app`) against the real stack: the pinned OpenTelemetry demo
with the checkout payment failure injected, the SRE stack from `scripts/setup_sre.py` (web proxy,
FastAPI, PostgreSQL, governed Grafana MCP), and Playwright in the `incident-console-e2e` runner.
No route is answered by the test. Every alert came from `GET /v1/alerts`; no row was written by
hand. Each scenario ran on its own fresh SRE project and was taken down without `-v`.

## Results per scenario

| Scenario | PR | Tested SHA | Date (UTC) | SRE project | Result |
|---|---|---|---|---|---|
| declare | PR-A `feat/703a-declare-from-card` | `1063551043932e556bcd2b3d99b419c85b336dc1` | 2026-10-31 22:44–22:46 | `sre-r2-703a-declare` | 1 passed, 0 skipped (56.4 s) |
| declare | PR-B `feat/703b-dismiss-link-from-card` | `40492aae9df1485f991f0b940aaf6105a3d943e7` | 2026-10-31 22:48–22:49 | `sre-r2-703b-declare` | 1 passed, 0 skipped (21.9 s) |
| dismiss | PR-B | `40492aae9df1485f991f0b940aaf6105a3d943e7` | 2026-10-31 22:51–22:52 | `sre-r2-703b-dismiss` | 1 passed, 0 skipped (17.8 s) |
| conflict | PR-B | `40492aae9df1485f991f0b940aaf6105a3d943e7` | 2026-11-02 16:35–16:40 | `sre-r5-703b-conflict` | 1 passed, 0 skipped (2.1 min) |

### declare (PR-A and PR-B)

Files: [`pr-a-declare/`](pr-a-declare/) and [`pr-b-declare/`](pr-b-declare/), each with
`verification.json` (written by `e2e/declare-live.spec.ts`) and four captures:
`1-inbox-before.png` (live card, `Nueva`), `2-dialog-prefilled.png` (dialog prefilled from the
alert, asks only severity and impact), `3-incident-route.png` (landing route after declaring) and
`4-card-declared.png` (card shows `Declarada` with `Ver incidente`).

| | PR-A | PR-B |
|---|---|---|
| Alert (from `GET /v1/alerts`) | `alt-checkout-dc19e4c9ddc1` | `alt-checkout-7b8a31ffec9f` |
| Declared incident | `inc-9e38e398b5479dfd1dac5b5d824f940c` | `inc-cd5e7b98d003c0061971f012bc1e9788` |
| Version read by the dialog | 1 | 1 |
| First `triage_declare` | 409 `stale_version` (expected_version 1) | 409 `stale_version` (expected_version 1) |
| Single retry | 201 (expected_version 2) | 201 (expected_version 2) |
| Actor | `demo-human` | `demo-human` |

While the dialog was open, the spec sent two `open_triage` commands through the same API (the
first creates the triage row at version 1, the second moves it past the version the dialog read),
so the 409 is a real stale version, not a simulated one.

The landing route shows «No encontramos ese incidente»: in live mode `/incidentes/{id}` still
reads the mock store and makes no `/api/` request. Reading the real incident is issue 708; this
is recorded as pending, not as a pass.

### dismiss (PR-B)

Files: [`pr-b-dismiss/`](pr-b-dismiss/). Alert `alt-checkout-641900eaa462`. Another tab bumped
the triage version twice while the popover was open; the console's `triage_dismiss` got 409
`stale_version`, retried once with the new version and got 200. `2-card-dismissed.png` shows the
card as `Descartada` with the toast «Alerta descartada · Falsa alarma».

### conflict (PR-B)

Files: [`pr-b-conflict/`](pr-b-conflict/). Alert `alt-checkout-420db47b1e17`. Another tab
dismissed the alert first; the console's command got 409 `terminal_decision`, which it does not
retry. `2-refusal.png` shows the Spanish message «Alguien más decidió sobre esta alerta. Revisa la
bandeja antes de volver a intentarlo.» with no status code, version or operation.

## Pending (not run at the current SHAs)

- **link** (PR-B, `LIVE_TRIAGE=link`): needs two real episodes of the same stack. It passed only
  at the earlier PR-B commit `a92f1c46`, not at `40492aae`, so no link evidence is committed here.
- **granted** and **no-grant** (issue 704, `e2e/auto-investigate-live.spec.ts` at `89c8bf10`):
  not run; see [issue 704 verification](../issue-704/verification.md).
- **Landing on the real incident**: the route exists but shows the mock-store message (issue 708).
- **403 recoverable message**: no browser scenario covers a missing grant on the card.

## Environment

- Host: macOS 26.6.2 arm64, Docker Desktop (engine 29.8.0, linux/arm64, 8 CPU, 4.8 GiB VM
  memory), Docker Compose 5.5.1.
- Images: console build `node:22.14-alpine` and runner `mcr.microsoft.com/playwright:v1.63.0-noble`
  (pinned by digest in `web/incident-console/Dockerfile`); API `python:3.12-slim` (pinned in
  `docker/api.Dockerfile`); lockfiles `uv.lock`, `web/incident-console/package-lock.json`.
- OpenTelemetry demo `3.0.0` (commit `1755859a9de82c2e5e225be68abc401a5ebf2b4f`, `demo/manifest.yaml`).
- Configuration: one untracked env file per SRE project, created from `.env.example` with locally
  generated keys, `TRIAGE_AGENT_PROVIDER=local-capture`, `SRE_ENABLE_PAID_LLM=0`,
  `SRE_OTEL_MODE=local`. No model call is needed by these scenarios. The file is never printed.

## Environment deviation

The pinned demo did not stay healthy on this 4.8 GiB arm64 Docker VM, so a local Compose
override raised four memory limits. The file lives in `.demo-state/memory-override.yaml`
(git-ignored, never committed) and changes nothing else: no retention, scrape, remote-write,
healthcheck, flag or load-generator setting. Its full content:

```yaml
# Local deviation from the pinned demo, never committed. Upstream 3.0.0 limits checkout and
# product-catalog to 20M; on this arm64 Docker Desktop both sit at the limit and their gRPC
# health probes time out, so frontend, frontend-proxy and load-generator never start. Grafana's
# 175M limit leaves it oscillating at the limit and its HTTP health probe times out, so the MCP
# query_prometheus probe gets 502; it is raised to 512M after the maintainer approved it.
# Prometheus's 200M limit leaves its readiness timing out and its OTLP writes failing with
# "context canceled", so the alert rule sees no data; it is raised to 512M as the last local try.
services:
  prometheus:
    deploy:
      resources:
        limits:
          memory: 512M
  grafana:
    deploy:
      resources:
        limits:
          memory: 512M
  checkout:
    deploy:
      resources:
        limits:
          memory: 64M
  product-catalog:
    deploy:
      resources:
        limits:
          memory: 64M
```

| Service | Upstream | Local | Authorized | Observed output that motivated it |
|---|---|---|---|---|
| checkout, product-catalog | 20M | 64M | 2026-10-31 17:04Z, in the working session: «Sí, override local», limited to these two services (128M allowed once if 64M failed; not needed) | `docker stats`: `checkout 15.71MiB / 20MiB`, `product-catalog 20MiB / 20MiB`; exporters logged `context deadline exceeded`; frontend, frontend-proxy and load-generator never started |
| grafana | 175M | 512M | 2026-10-31 21:04Z, in the working session: «Grafana a 512M», answering whether to extend the override to Grafana or move to AWS; a separate, explicit authorization | `grafana 175MiB / 175MiB`, health probe `download timed out` / `Connection refused`, `restarts=1 health=fail`; the MCP `query_prometheus` probe got 502 |
| prometheus | 200M | 512M | 2026-11-02 16:08Z, in the working session: «Prometheus a 512M, como ÚLTIMO intento local», with a stop rule | `prometheus 156.4MiB / 200MiB … wget: download timed out` (readiness at 23:02:10Z and 23:02:41Z on 2026-10-31); 50 `Error appending remote write … err="context canceled"` from 22:37:17Z |

Which limits applied to which run:

- declare (PR-A, PR-B) and dismiss, 2026-10-31: checkout, product-catalog and Grafana overrides;
  Prometheus at its upstream 200M. Prometheus was already logging `context canceled` remote-write
  errors during these runs (first at 22:37:17Z); the alert rule still fired and each spec passed.
- conflict, 2026-11-02: all four overrides. Pre-checks before it: `demo_env.py verify` exit 0;
  Prometheus readiness 200 at 16:18:14Z, 16:18:47Z and 16:19:20Z (77–82 MiB of 512); the rule
  query returned `0.0603` at 16:20:05Z; `GET /v1/alerts` answered 200 in 2.10 s at 16:35:37Z.
  During the run Prometheus logged two `context canceled` remote-write errors (16:38:37Z and
  16:38:44Z) at 166 MiB of 512, with readiness 200 and no restart or OOM. The scenario passed;
  under the stop rule the remaining local scenarios were not run.

The demo was started with its own CLI plus the override as one extra `-f`:

```sh
python3 scripts/demo_env.py up      # pinned demo, then stopped and re-created with the override:
DEMO_FLAGS_DIR=.demo-state/flagd DEMO_STATE_DIR=.demo-state docker compose -p otel-demo \
  --project-directory otel-demo --env-file otel-demo/.env --env-file demo/demo.env \
  -f otel-demo/compose.yaml -f otel-demo/compose.observability.yaml -f compose.demo.yaml \
  -f .demo-state/memory-override.yaml up -d --wait
python3 scripts/demo_env.py verify
python3 scripts/demo_env.py fail    # inject the checkout payment failure (restarts flagd only)
```

## Commands per scenario

Run from the checkout of the tested SHA. `ENV_FILE` is the untracked env file of a fresh SRE
project `P`; the runner gets `ADMIN_HUMAN_API_KEY` from the environment, never from argv.

```sh
python3 scripts/setup_sre.py --env-file "$ENV_FILE"   # writes .demo-state/sre-setup/$P.json
DC="docker compose --project-directory . --env-file $ENV_FILE -p $P -f compose.yaml -f compose.mcp.yaml -f .demo-state/sre-setup/$P.json"
export ADMIN_HUMAN_API_KEY   # read from $ENV_FILE into the shell, never typed or printed
run() {  # $1 spec, $2 switch; artifacts land in web/incident-console/e2e/artifacts/
  $DC --profile e2e run --build --rm -e "$2" -e ADMIN_HUMAN_API_KEY \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" incident-console-e2e \
    sh -c "npx playwright test $1 --reporter=line; s=\$?; chown -R \$HOST_UID:\$HOST_GID e2e/artifacts; exit \$s"
}
run declare-live.spec.ts LIVE_DECLARE=1          # declare (PR-A, PR-B)
run triage-live.spec.ts LIVE_TRIAGE=dismiss      # dismiss (PR-B)
run triage-live.spec.ts LIVE_TRIAGE=conflict     # conflict (PR-B)
$DC down                                         # volumes kept
```

Each scenario consumes its alert, so each one used a new project `P`. Before `conflict`,
`GET /v1/alerts` was required to answer 200 in under 5 s.

## Sanitization

Captures were reviewed by eye: no key, token, header or personal data. The JSON files hold
alert, incident and actor identifiers, paths, statuses and error codes only. The committed files
were scanned for every secret value of the env files used and for key, token and header patterns.
