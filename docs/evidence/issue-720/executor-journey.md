# Issue #720: the deploy-executor journey on the real stack

Local Compose project `sre-720` on this host (Docker Engine 29.9.2, Compose 5.6.1), 2026-10-22
18:32-18:34Z: `docker-socket-proxy` (tecnativa v0.5.0, digest-pinned), `deploy-executor` (the API
image, `uvicorn sre_agent.executor.app:app`), `demo/probe:1.1.0` running as `probe`,
`demo/probe:1.0.0` in the image store, and the Playwright runner `executor-e2e` from
`docker/e2e.Dockerfile`. No fixture replaces a dependency: the executor talks to the real daemon
through the proxy and the probe is a real container whose image changes.

## `deploy-executor-real.spec.js`: 1 passed (41.4 s), `report.json`

Transcript `transcript.json`, 26 steps. The proxy answered 403 to `/info`, `/networks`,
`/volumes`, `/version`, `/events` and `POST /exec/any/start`, and 200 to `/containers/json` and
`/images/json` (`proxy-denies-info.png`). Every negative fixture of
`schemas/executor/1.0.0/fixtures/negative/` was rejected as declared, and
`GET /v1/services/probe` kept the same container id, image and start time afterwards:

| Fixture | Status | `error.code` |
| --- | --- | --- |
| extra-field | 422 | contract_validation_failed |
| missing-idempotency-key | 400 | invalid_idempotency_key |
| missing-to-tag | 422 | contract_validation_failed |
| operation-not-enrolled (`web`) | 404 | operation_not_enrolled |
| tag-with-repository | 422 | contract_validation_failed |
| unknown-service | 404 | service_not_enrolled |
| unknown-tag (`9.9.9`) | 422 | image_tag_unknown |
| key-reused-with-other-payload | 409 | idempotency_conflict |

The executions, as `GET /v1/executions` lists them (`executions.png`):

| Step | Outcome | Replayed | Duration | Image before → after | Container |
| --- | --- | --- | --- | --- | --- |
| rollback 1.0.0 | rolled_back | no | 13.6 s | 1.1.0 → 1.0.0 | 9fa39981a635 → 9249952cd155 |
| same key, same body | rolled_back | yes | (stored) | same | same |
| rollback 1.0.0, new key | already_at_target | no | 31 ms | 1.0.0 → 1.0.0 | unchanged |
| restart | restarted | no | 13.0 s | 1.0.0 → 1.0.0 | unchanged, new `started_at` |
| same key | restarted | yes | (stored) | same | same |
| rollback 1.1.0 | rolled_back | no | 13.5 s | 1.0.0 → 1.1.0 | 9249952cd155 → ba749423c366 |

After the first rollback the probe answered `{"service": "probe", "version": "1.0.0"}`
(`probe-after-rollback.png`), and `1.1.0` again after the roll-forward. The 13 s of a rollback are
the 10 s stop grace of the old container plus the new one's healthcheck; the restart is the same.

## Socket proxy stopped: 1 passed (6.6 s), `report-socket-down.json`

With `docker compose stop docker-socket-proxy`: `GET /health/ready` 503
`{"status":"unavailable","dependency":"docker"}` and `POST deployment.rollback` 503
`docker_unavailable`, `retryable: true` (`socket-down.json`). Nothing ran.

## `curl` (`curl-rollback.txt`)

From a one-off container on the `runtime` network: rollback to 1.0.0 → 200 `rolled_back`; the
probe answers 1.0.0; the same `Idempotency-Key` and body → 200 `replayed: true` with the same
`execution_id`; `to_tag` 9.9.9 → 422 `image_tag_unknown`; roll forward to 1.1.0 → 200; the probe
answers 1.1.0.

## What the rolled-forward container looks like

`docker inspect sre-720-probe-1` after the journey: image `demo/probe:1.1.0`, `PROBE_VERSION=1.1.0`
and the healthcheck from that image, the Compose labels of the `probe` service, the label
`io.sre-agent.deploy-executor.execution=exe_10b19214c8ed16d4`, and the `probe` alias on
`sre-720_runtime`. The first run of this journey found the defect that made this rule explicit:
cloning the container's merged configuration carried the old image's `PROBE_VERSION`, so the
executor now clones only what the container added over its image.
