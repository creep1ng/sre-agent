# Issue #743: the signed executor journey on the real stack

Local Compose project `sre-743` on this host (Docker Engine 29.9.2, Compose 5.6.1), 2026-10-23
00:16-00:19Z: the proxy, `deploy-executor` built from this branch (read-only root, no capabilities,
on `executor-call` and `executor-boundary` only), `demo/probe:1.1.0` running, `demo/probe:1.0.0`
in the image store, and `executor-e2e` holding the key the gateway will hold (#722). Nothing is
mocked; the key value appears in no file of this directory (checked with `grep -rl`).

## `deploy-executor-real.spec.js`: 1 passed (43.5 s), `report.json`

Transcript `transcript.json`, 31 steps. Every POST of the journey is signed as #722 will sign;
the thirteen negative fixtures of `schemas/executor/1.0.0/fixtures/negative/` answered as the
contract declares, and afterwards `GET /v1/services/probe` kept the same container id, image and
start time and `GET /v1/executions` listed exactly the executions it listed before them:

| Fixture | Signature variant | Status | `error.code` |
| --- | --- | --- | --- |
| signature-missing | no headers | 401 | signature_missing |
| signature-wrong-key | another secret | 401 | signature_invalid |
| signature-body-tampered | signed for `to_tag 1.1.0`, sent `1.0.0` | 401 | signature_invalid |
| signature-key-mismatch | signed for another `Idempotency-Key` | 401 | signature_invalid |
| signature-expired | timestamp one hour old | 401 | signature_expired |
| extra-field, missing-to-tag, tag-with-repository | valid | 422 | contract_validation_failed |
| missing-idempotency-key | valid | 400 | invalid_idempotency_key |
| operation-not-enrolled (`web`) | valid | 404 | operation_not_enrolled |
| unknown-service | valid | 404 | service_not_enrolled |
| unknown-tag (`9.9.9`) | valid | 422 | image_tag_unknown |
| key-reused-with-other-payload | valid | 409 | idempotency_conflict |

The executions, as `GET /v1/executions` lists them (`executions.png`):

| Step | Outcome | Replayed | Duration | Image before → after | Container |
| --- | --- | --- | --- | --- | --- |
| rollback 1.0.0 | rolled_back | no | 13.4 s | 1.1.0 → 1.0.0 | 1f2cb3f7aff3 → bb441d4b9fc5 |
| same key, same body | rolled_back | yes | (stored) | same | same |
| rollback 1.0.0, new key | already_at_target | no | 29 ms | 1.0.0 → 1.0.0 | unchanged |
| restart | restarted | no | 13.2 s | 1.0.0 → 1.0.0 | unchanged, new `started_at` |
| same key | restarted | yes | (stored) | same | same |
| rollback 1.1.0 | rolled_back | no | 14.6 s | 1.0.0 → 1.1.0 | bb441d4b9fc5 → a301cf3cbc96 |

After the first rollback the probe answered `{"service": "probe", "version": "1.0.0"}`
(`probe-after-rollback.png`), and `1.1.0` again after the roll-forward.

## Socket proxy stopped (1 passed, 0.5 s) and no key: `socket-down.json`, `signing-key-unconfigured.txt`

With the proxy stopped and a signed request: readiness 503 `dependency: docker`, rollback 503
`docker_unavailable`; the signature was accepted and nothing ran. A one-off executor with
`DEPLOY_EXECUTOR_SIGNING_KEY` emptied, driven by `fastapi.testclient` inside its own container:
readiness 503 `dependency: signing_key`, restart 503 `signing_key_unconfigured`.

## Network and an unsigned caller: `network-isolation.txt`, `unsigned-curl.txt`

From `probe`, which is only on `runtime`, `gethostbyname('deploy-executor')` raises
`socket.gaierror` (exit 1); from `executor-e2e`, on `executor-call`, `getent hosts` resolves it
(exit 0). From that network, an unsigned `POST deployment.restart` with an `Idempotency-Key`
answers `HTTP/1.1 401` `signature_missing`, and the probe container is untouched afterwards.
`contract-validation.txt`: examples and the thirteen fixtures checked against the schemas in the
`python-checks` container; 19 failure scenarios and 17 public errors in `deploy-executor.yaml`.
