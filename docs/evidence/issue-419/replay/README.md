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
browser script rejects a missing/malformed source SHA; the generated Compose
revision is the same revision embedded in the packaged API image.

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
