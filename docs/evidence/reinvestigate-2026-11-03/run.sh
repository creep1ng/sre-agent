#!/usr/bin/env bash
# The automatic re-investigation after a failed verification (#710) on the local stand-in, with
# the scripted model and the fake Bot API. Usage, from the checkout root with a filled .env:
#   OUT=/tmp/reinvestigate SCENARIO=retry docs/evidence/reinvestigate-2026-11-03/run.sh
# SCENARIO=retry: checkout with both payment flags on; SCENARIO=exhausted: sre-checkout's alert
# firing, with simulated rollbacks a person says still fail (drive.py). The project is removed
# on exit.
set -euo pipefail
HERE=docs/evidence/reinvestigate-2026-11-03 SCENARIO="${SCENARIO:-retry}"
OUT="${OUT:?set OUT to an empty directory}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-reinvestigate}" LOCAL_FLOW_MODEL=scripted
export API_PORT="${API_PORT:-18220}" WEB_PORT="${WEB_PORT:-18221}" POSTGRES_PORT="${POSTGRES_PORT:-18222}"
export FAKE_TELEGRAM_PORT="${FAKE_TELEGRAM_PORT:-18223}" LOCAL_FLOW_DIR="$OUT/flow"
# The agent verifies 10 s after an approval instead of the demo's 150 s.
export VERIFICATION_DELAY_SECONDS="${VERIFICATION_DELAY_SECONDS:-10}"
# EXTRA_COMPOSE: an optional override, such as explicit subnets on a host whose pools are full.
dc() {
  docker compose -f compose.yaml -f compose.local-flow.yaml -f compose.local-flow-flags.yaml \
    ${EXTRA_COMPOSE:+-f "$EXTRA_COMPOSE"} --profile telegram --profile telegram-e2e "$@"
}
trap 'dc logs --no-color api > "$OUT/api.log" 2>&1; dc --profile e2e down -v --remove-orphans >/dev/null 2>&1' EXIT
mkdir -p "$LOCAL_FLOW_DIR/otel-state" "$OUT/shots"
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" -v "$LOCAL_FLOW_DIR/otel-state:/state" \
  python:3.12-slim python -I /repo/scripts/local_flow_flags.py /state
dc up --build --wait db api web otel-flags flagd deploy-executor fake-telegram telegram-gateway
dc run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
dc run --rm --no-deps -T seed python scripts/provision_demo.py
code=$(dc run --rm --no-deps -T telegram-gateway python -m sre_agent.chat.telegram link \
  --principal demo-human | grep -o 'start=[A-Za-z0-9_-]*' | cut -d= -f2)
dc exec -T fake-telegram python -c "import json, sys, urllib.request as u; u.urlopen(u.Request(
  'http://127.0.0.1:8081/_test/messages', json.dumps({'chat_id': 424242,
  'text': '/start ' + sys.argv[1]}).encode(), {'Content-Type': 'application/json'}))" "$code"
K=$(grep ^DEMO_HUMAN_API_KEY= .env | cut -d= -f2)
if [ "$SCENARIO" = retry ]; then
  dc exec -T otel-flags python /guest/mcp_guest.py fail --flag paymentFailure
  dc exec -T otel-flags python /guest/mcp_guest.py fail --flag paymentUnreachable
  echo flag:paymentUnreachable > "$LOCAL_FLOW_DIR/checkout-payment-error-rate"
else
  echo firing > "$LOCAL_FLOW_DIR/checkout-orders-error-rate"
fi
dc exec -T -e DEMO_HUMAN_API_KEY="$K" -e SCENARIO="$SCENARIO" api python - < "$HERE/drive.py" \
  > "$OUT/drive.json"
INCIDENT=$(grep -o '"incident_id": "[^"]*"' "$OUT/drive.json" | head -1 | cut -d'"' -f4)
dc --profile e2e run --build --rm --no-deps -e DEMO_HUMAN_API_KEY="$K" -e INCIDENT_ID="$INCIDENT" \
  -e SHOTS=/shots -v "$PWD/$HERE/capture.spec.ts:/e2e/e2e/reinvestigate.capture.spec.ts:ro" \
  -v "$OUT/shots:/shots" incident-console-e2e \
  sh -c 'npx playwright test e2e/reinvestigate.capture.spec.ts --reporter=list; s=$?; chown -R '"$(id -u):$(id -g)"' /shots; exit $s'
