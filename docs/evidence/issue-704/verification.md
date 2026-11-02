# Issue 704 verification: HTTP checks and identifier reproduction

**Neither file set here was produced at the current #704 head `89c8bf10449f60febf1bbcf287e5f7a47bb2347e`.**
Both are earlier HTTP runs against the real FastAPI process (no TestClient, no stubbed route),
kept as recorded on 2026-10-29. The browser scenarios at the current head (granted, no-grant)
were not run; see Pending.

## Results per file

| File | Tested SHA | Date (UTC) | Stack | Result |
|---|---|---|---|---|
| [`verify_704_http.py`](verify_704_http.py) → [`verify_704_http.out.json`](verify_704_http.out.json) | `ba803afbaf3b8dab6942280f6f0b0b321d0ee8f1` (earlier branch `feat/704-auto-investigate-declare`, before the rebase onto the #703 stack) | 2026-10-29 01:11 | `sre-704`, API, PostgreSQL, no OTel demo | 9 of 9 checks true |
| [`repro_ids.py`](repro_ids.py) → [`repro_ids.out.json`](repro_ids.out.json) | API image built from `745cd0b4498411c72be09aba4fb0441ff0fa8d5d` (`main` at the time) | 2026-10-29 00:58 | `sre-703`, API, PostgreSQL, no OTel demo | declaration identifiers do not match the published patterns |

### HTTP checks (`verify_704_http.out.json`)

Direct calls to the gateway inside the `api` container with synthetic alert identifiers
(`al-v704-…`), not alerts from `GET /v1/alerts`:

- Granted declarant: `triage_declare` answered 201 in 132 ms; the `investigate` run
  `run_121a9a4f7670d2dd` was `running`/`investigating` (not `pending`) 220 ms after the request,
  with one «Investigation started.» event whose actor is `demo-human`.
- Replay with the same `Idempotency-Key`: 201 with an identical body; two runs before and after
  the replay, one start event.
- Declarant with `incident.declare` but no `run.start`: 201, the incident is declared, no
  investigating run, and the timeline holds one event with `reason_code: run_start_not_authorized`
  and «Investigation did not start: the declarant lacks the run.start grant.».

Since `ba803afb` the product code changed: the branch was rebuilt on the #703 stack and
`e1c58516` makes `start_run` join the caller's unit of work. These numbers therefore describe the
earlier commit only. The 220 ms is a quiet-stack figure; the 5 s criterion from the operator's
click at the current head is unmeasured (see Pending).

### Identifier reproduction (`repro_ids.out.json`)

A declaration publishes `evt-87f727a3a84e3c1b9096eb04` and `snap-87f727a3a84e3c1b9096eb04`,
which do not match `^evt_[a-z0-9]{8,32}$` (`agent/schemas/run-event.schema.yaml`) and
`^snap_[a-z0-9]{8,32}$` (`agent/schemas/incident-snapshot.schema.yaml`). The defect predates
#704 and is tracked in issue 763. #704 keeps the existing format on purpose: at `89c8bf10` the
declaration still builds identifiers as `f"{prefix}-{digest[:24]}"`
(`src/sre_agent/triage/service.py:574`); only the new blocked-start event uses `evt_…`
(`service.py:581`). Both formats appear in the no-grant timeline above.

## Commands

From the checkout of the tested SHA, with this directory's two scripts copied beside it and the untracked `.env` (created from `.env.example`, local
keys); keys reach the container through the environment and are never printed:

```sh
docker compose -p sre-704 up -d --build --wait api
docker compose -p sre-704 run --rm seed python -m sre_agent.persistence.seeds --seed-mcp
docker compose -p sre-704 run --rm -e AUDIT_HMAC_KEY -v "$PWD/scripts:/setup:ro" seed python /setup/provision_demo.py
docker compose -p sre-704 exec -T -e DEMO_KEY -e ADMIN_KEY api python - \
  < docs/evidence/issue-704/verify_704_http.py > verify_704_http.out.json
docker compose -p sre-703 exec -T -e ADMIN_KEY api python - \
  < docs/evidence/issue-704/repro_ids.py > repro_ids.out.json
```

`DEMO_KEY` and `ADMIN_KEY` hold `DEMO_HUMAN_API_KEY` and `ADMIN_HUMAN_API_KEY` from `.env`. The
scripts print sanitized JSON only and exit 1 on a failed check.

## Pending (not run at `89c8bf10`)

- **granted** (`AUTO_INVESTIGATE=granted`, `e2e/auto-investigate-live.spec.ts`): declare a live
  alert from the card and find the `investigate` run not `pending` within 5 s of the click. The
  last run, at the earlier commit `edcbaf4f`, failed that bound: `GET /v1/incidents/{id}` did not
  answer within 5 s while the dispatch ran. The cause is not established (see the latency risk
  below); the instrumented rerun was stopped by the environment stop rule.
- **no-grant** (`AUTO_INVESTIGATE=no-grant`): passed at `edcbaf4f` only.
- **link** (issue 703, PR-B): not run at `40492aae`.

Open latency risk, not a measured fact: the API runs one uvicorn worker
(`docker/api.Dockerfile:68`); every authenticated request verifies its key with synchronous
`hashlib.scrypt` on the event loop (`src/sre_agent/persistence/api_keys.py:44-60`, called from
`persistence/repositories.py:213`); and the dispatch calls back into the same process
(`INVESTIGATOR_GATEWAY_URL: http://api:8000`, `compose.yaml:34`). `GET /v1/incidents/{id}` takes
no row or advisory lock (`gateway/incidents.py:232-255`), so a slow answer during a dispatch would
come from a busy event loop or host, not from database locks. This needs the instrumented granted
run to confirm or refute.

## Environment deviation

The two files above ran without the OpenTelemetry demo, so no deviation applies to them. The
pending browser scenarios need the demo; the local Compose memory override used for issue 703
(checkout and product-catalog 64M, Grafana 512M authorized on 2026-10-31 21:04Z, Prometheus 512M
on 2026-11-02 16:08Z) is listed in full, with its reasons and the outputs that motivated it, in
[issue 703 verification](../issue-703/verification.md#environment-deviation). Its content:

```yaml
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

Even with it, Prometheus logged `context canceled` remote-write errors on 2026-11-02 at 16:38:37Z
and 16:38:44Z, so the local runs stopped and the pending scenarios move to another environment.

## Sanitization

The JSON outputs hold identifiers, statuses, timings, summaries and reason codes only; the
scripts read keys from the environment and never print them. Files were scanned for every secret
value of the env files used and for key, token and header patterns.
