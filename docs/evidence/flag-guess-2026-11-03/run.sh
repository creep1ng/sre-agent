#!/usr/bin/env bash
# The 2026-11-03 walkthrough's first run on the local stand-in (README.md): the scripted model
# guesses the wrong fault flag, the runtime refuses it as already off, and the steps the refusal
# leaves go to the BoK and one more query. Usage, from the checkout root with a filled .env:
#   OUT=/tmp/flag-guess SCENARIO=fault docs/evidence/flag-guess-2026-11-03/run.sh
# SCENARIO=fault turns paymentUnreachable on: the run proposes it, the API approves, the alert
# resolves. SCENARIO=no-flag fires the alert with every flag off: the run ends with a person.
# Scripted model, no EC2. The project is removed on exit.
set -euo pipefail
HERE=docs/evidence/flag-guess-2026-11-03 SCENARIO="${SCENARIO:-fault}"
OUT="${OUT:?set OUT to an empty directory}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-flag-guess}" LOCAL_FLOW_MODEL=scripted
export API_PORT="${API_PORT:-18210}" WEB_PORT="${WEB_PORT:-18211}" POSTGRES_PORT="${POSTGRES_PORT:-18212}"
export LOCAL_FLOW_DIR="$OUT/flow"
dc() { docker compose -f compose.yaml -f compose.local-flow.yaml -f compose.local-flow-flags.yaml "$@"; }
trap 'dc --profile e2e down -v --remove-orphans >/dev/null 2>&1' EXIT
mkdir -p "$LOCAL_FLOW_DIR/otel-state" "$OUT/shots"
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" -v "$LOCAL_FLOW_DIR/otel-state:/state" \
  python:3.12-slim python -I /repo/scripts/local_flow_flags.py /state
dc up --build --wait db api web otel-flags flagd deploy-executor
dc run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
dc run --rm --no-deps -T seed python scripts/provision_demo.py
K=$(grep ^DEMO_HUMAN_API_KEY= .env | cut -d= -f2)
if [ "$SCENARIO" = fault ]; then
  dc exec -T otel-flags python /guest/mcp_guest.py fail --flag paymentUnreachable
  echo flag:paymentUnreachable > "$LOCAL_FLOW_DIR/checkout-payment-error-rate"
  dc exec -T -e DEMO_HUMAN_API_KEY="$K" -e DECIDE=api -e EXPECT_REFUSED=paymentFailure api \
    python - flow < scripts/flag_set_e2e.py > "$OUT/flow.json"
  expect=resolved
else
  echo firing > "$LOCAL_FLOW_DIR/checkout-payment-error-rate"
  expect=needs_human
fi
dc exec -T -e DEMO_HUMAN_API_KEY="$K" -e EXPECT="$expect" api python - < "$HERE/trace.py" \
  > "$OUT/trace.json"
INCIDENT=$(grep -o '"incident_id": "[^"]*"' "$OUT/trace.json" | head -1 | cut -d'"' -f4)
dc --profile e2e run --build --rm --no-deps -e DEMO_HUMAN_API_KEY="$K" -e INCIDENT_ID="$INCIDENT" \
  -e SHOTS=/shots -v "$PWD/$HERE/capture.spec.ts:/e2e/e2e/flag-guess.capture.spec.ts:ro" \
  -v "$OUT/shots:/shots" incident-console-e2e \
  sh -c 'npx playwright test e2e/flag-guess.capture.spec.ts --reporter=list; s=$?; chown -R '"$(id -u):$(id -g)"' /shots; exit $s'
