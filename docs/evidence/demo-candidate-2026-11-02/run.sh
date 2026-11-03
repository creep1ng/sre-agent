#!/usr/bin/env bash
# The 2026-11-04 demo path on the local stand-in (README.md): fault → incident → flag.set proposal
# → one tap in the fake Bot API → the API's tap worker runs flag.set → receipt → message edited →
# alert resolved → verification → recovery edit. Usage, from the checkout root with a filled .env:
#   OUT=/tmp/demo-candidate docs/evidence/demo-candidate-2026-11-02/run.sh
# Scripted model, no EC2. The project is removed on exit.
set -euo pipefail
HERE=docs/evidence/demo-candidate-2026-11-02
OUT="${OUT:?set OUT to an empty directory}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-demo-candidate}" LOCAL_FLOW_MODEL=scripted
export API_PORT="${API_PORT:-18200}" WEB_PORT="${WEB_PORT:-18201}" POSTGRES_PORT="${POSTGRES_PORT:-18202}"
export FAKE_TELEGRAM_PORT="${FAKE_TELEGRAM_PORT:-18203}" LOCAL_FLOW_DIR="$OUT/flow"
dc() {
  docker compose -f compose.yaml -f compose.local-flow.yaml -f compose.local-flow-flags.yaml \
    --profile telegram --profile telegram-e2e "$@"
}
trap 'dc --profile e2e down -v --remove-orphans >/dev/null 2>&1' EXIT
stamp() { echo "$(date -u +%H:%M:%S) $*" | tee -a "$OUT/timings.txt"; }
mkdir -p "$LOCAL_FLOW_DIR/otel-state" "$OUT/shots"
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro" -v "$LOCAL_FLOW_DIR/otel-state:/state" \
  python:3.12-slim python -I /repo/scripts/local_flow_flags.py /state
stamp "start"
dc up --build --wait db api web incident-console otel-flags flagd deploy-executor fake-telegram \
  telegram-gateway
dc run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
dc run --rm --no-deps -T seed python scripts/provision_demo.py
code=$(dc run --rm --no-deps -T telegram-gateway python -m sre_agent.chat.telegram link \
  --principal demo-human | grep -o 'start=[A-Za-z0-9_-]*' | cut -d= -f2)
dc exec -T fake-telegram python -c "import json, sys, urllib.request as u; u.urlopen(u.Request(
  'http://127.0.0.1:8081/_test/messages', json.dumps({'chat_id': 424242,
  'text': '/start ' + sys.argv[1]}).encode(), {'Content-Type': 'application/json'}))" "$code"
K=$(grep ^DEMO_HUMAN_API_KEY= .env | cut -d= -f2)
stamp "stack ready, chat linked"
dc exec -T -e DEMO_HUMAN_API_KEY="$K" api python - checks < scripts/flag_set_e2e.py > "$OUT/checks.json"
stamp "boundaries checked"
dc exec -T otel-flags python /guest/mcp_guest.py fail --flag paymentUnreachable
echo flag:paymentUnreachable > "$LOCAL_FLOW_DIR/checkout-payment-error-rate"
stamp "fault injected: paymentUnreachable on"
dc exec -T -e DEMO_HUMAN_API_KEY="$K" -e DECIDE=telegram -e FLAGD_ADDRESS=flagd:8013 api \
  python - flow < scripts/flag_set_e2e.py > "$OUT/flow.json"
stamp "flow done: approved in Telegram, flag.set ran, alert resolved"
INCIDENT=$(grep -o '"incident_id": "[^"]*"' "$OUT/flow.json" | head -1 | cut -d'"' -f4)
dc exec -T -e DEMO_HUMAN_API_KEY="$K" -e INCIDENT_ID="$INCIDENT" api python - < "$HERE/verify.py" \
  > "$OUT/verification.json"
stamp "verification_passed recorded on $INCIDENT"
dc --profile e2e run --build --rm --no-deps -e DEMO_HUMAN_API_KEY="$K" -e INCIDENT_ID="$INCIDENT" \
  -e SHOTS=/shots -v "$PWD/$HERE/capture.spec.ts:/e2e/e2e/demo-candidate.capture.spec.ts:ro" \
  -v "$OUT/shots:/shots" incident-console-e2e \
  sh -c 'npx playwright test e2e/demo-candidate.capture.spec.ts --reporter=list; s=$?; chown -R '"$(id -u):$(id -g)"' /shots; exit $s'
stamp "captured: incident page, /app/acciones, chat transcript, Bot API calls"
