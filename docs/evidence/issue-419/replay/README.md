# Reproduce Issue 419 identity evidence

This helper runs the repository's production API and web Dockerfiles against an
isolated PostgreSQL volume, then drives the packaged review UI with synthetic
credentials. It also runs the existing 12-case browser review suite against its
mock HTTP seam. It never calls an external model provider.

## Requirements and safe local inputs

Use Git, Python 3, and Docker Compose 2.24.4 or newer. Start from a clean
checkout. Choose fresh temporary paths and a unique Compose project name; do not
reuse a prior project's database:

```sh
export REPLAY_DIR="$(mktemp -d)"
chmod 700 "$REPLAY_DIR"
export ENV_FILE="$REPLAY_DIR/compose.env"
export OUTPUT_DIR="$REPLAY_DIR/output"
mkdir -m 777 "$OUTPUT_DIR"
export PROJECT="issue419replay-$(date +%s)"
python3 docs/evidence/issue-419/replay/prepare_env.py --output "$ENV_FILE" --source-sha "$(git rev-parse HEAD)"
```

The preparation script writes non-production random API keys, database
password, and audit key with mode 0600. It does not display or source the file.
Pass it only to Compose through `--env-file`; never print it, commit it, or
attach it. The test stack has no external API credentials.

## Packaged API/web replay

Run from the repository root. The overlay removes host-published ports and maps
provisioning values only into containers. All commands use the existing Compose
services. The unique project name owns this replay's database and network.

```sh
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile e2e up --build -d web
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile checks run --build --rm --no-deps -v "$PWD/docs/evidence/issue-419/replay/seed.py:/tmp/issue419-seed.py:ro" -v "$PWD/agent/fixtures/incidents/otel-payment-failure/initial-state.yaml:/fixtures/initial-state.yaml:ro" python-checks python /tmp/issue419-seed.py
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile checks run --build --rm --no-deps python-checks python scripts/provision_incident_workflow.py
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile e2e run --build --rm --no-deps -v "$PWD/docs/evidence/issue-419/replay:/e2e/issue419-replay:ro" -v "$OUTPUT_DIR:/evidence" e2e npx playwright test --config=/e2e/issue419-replay/replay.config.js
```

The replay records sanitized HTTP responses in `$OUTPUT_DIR/final-replay.json`
and a real browser capture in `$OUTPUT_DIR/final-review-receipt.png`. The
browser requires OpenAPI `x-sre-agent-build-revision` to equal `SOURCE_SHA`
before the command POST. It checks the packaged Nginx response for a semantic
`no-store` directive and separately calls `http://api:8000/v1/whoami` from the
Compose network for each credential, requiring the API response header to be
exactly `Cache-Control: no-store`. This direct request prevents Nginx's own
header from masking an API regression.

Read back grant scope and decisions without credentials or authorization
headers:

```sh
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" exec -T db psql -U sre_agent -d sre_agent -Atc "SELECT principal_id || '|' || action || '|' || resource_type || '|' || resource_id || '|' || effect || '|' || status FROM grants WHERE principal_id='demo-human' ORDER BY action; SELECT i.incident_id || '|' || r.run_id || '|' || count(d.decision_id)::text || '|' || coalesce((jsonb_agg(d.document)->0)::text, 'null') FROM incident.incidents i JOIN incident.runs r USING (incident_id) LEFT JOIN incident.decisions d USING (incident_id, run_id) WHERE i.incident_id IN ('inc-issue419-final-browser','inc-issue419-final-mismatch') GROUP BY i.incident_id,r.run_id ORDER BY i.incident_id"
```

Expect only the four `run.*` grants for `demo-human` (no `admin.read`), one
accepted decision attributed to `demo-human`, and zero decisions for the
mismatched-principal run. Save both output files before removing the owned
stack. After evidence is saved, remove only this unique project's containers,
network, and test volume with the same Compose arguments and
`down --volumes --remove-orphans`.

## Focused browser review suite (mock HTTP seam)

This is UI contract evidence, not packaged API evidence. It requires no running
API. Run its existing browser tests against a local static view served inside
the e2e container:

```sh
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile e2e run --build --rm --no-deps -v "$PWD:/workspace:ro" -v "$PWD/tests/browser:/e2e/tests/browser:ro" -v "$PWD/docs/evidence/issue-419/replay/review.config.js:/e2e/playwright-review.config.js:ro" e2e npx playwright test --config=/e2e/playwright-review.config.js
```

The configuration serves the checkout read-only and writes Playwright output
outside the source tree. The suite covers credential changes/clears, reason
recovery, action stability, and the pending-command Refresh lock when those
changes are present in the checked-out source.

## Captured result for this helper candidate

Replayed from a clean detached checkout of source `31bef8da3d177c4bb54bbe145abbf13a270a1db2`, based on main `31b4d2f8ba3dc292ea9bce59c069ffa21ebfc02f`. The product tree is main-only; no #489 Refresh-lock change is included. Compose was 5.6.0; Playwright was 1.63.0.

This captured run predates the direct-API header assertion described above; its
recorded `no-store` result is from the packaged Nginx path only. The helper's
behavior/test tree was independently replayed at `a05015582301183b937be0f9a2ab2799da60ac0c`; its only change from the tested `31bef8d` helper was this README. That exact-head replay passed the packaged case, 12 mock-seam browser cases, and SQL checks (one attributed decision, zero mismatched decisions). The helper was then merged to main at `9c5c1765e4c39538609ad8e3d55009dfaee1b155` with an identical tree. These helper runs are not evidence that the final #489 source SHA was served; the separate #489 evidence is recorded in its report.

- Packaged replay: **1 passed**. Both credentials returned only their own identity (200); each Cache-Control contained `no-store` (`no-store, no-store` on the packaged path). Invalid credentials returned generic 401. OpenAPI exposed Bearer security, only `principal_id`, 401, and the exact `SOURCE_SHA` build revision.
- The revision assertion runs before the command POST. A wrong, valid-format SHA control against the same test bytes at `ddb8273` failed there; no replay artifacts or decisions were produced.
- Valid approval returned 202 with `actor_reference: demo-human`; SQL recorded one attributed decision. A mismatched `admin-human` claim returned 403 and persisted zero decisions.
- SQL confirmed only four active demo-human `run.*` grants (`run.read`, `run.start`, `run.command`, `run.approve`), with no `admin.read`.
- Fresh packaged UI capture: [final-review-receipt.png](final-review-receipt.png), SHA-256 `c16bb747ea194b9ab59fa1521bb5458bd9bda59ed2b18b9da3951aee193c756a`.
- Focused browser suite: **12 passed in 14.8 seconds** on its mock HTTP seam, separate from packaged API evidence.
- Full Python checks: **1,575 passed, 1 skipped**; lint/format, contracts, typing, isolation and migration checks passed.
- Packaged image IDs: API `sha256:4a844554f64c76b3d9b4c3de3924a071e5f47b9aaed232c9b1826bea5f8e2a43`; web `sha256:74701394e2ff0204a29bba34929ca5f1c1958b0dc37cec6a71f01ccb82d4eb83`; e2e `sha256:37132d45f0f8083fe44c00f786a15957c5fb772004ef0fd85e83c4cbd36a2c56`.

This is a reproducibility helper/evidence slice only. It does not close issue #419 or claim the final #489 Refresh behavior.
