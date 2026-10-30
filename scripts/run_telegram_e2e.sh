#!/usr/bin/env bash
# Telegram channel E2E (#766) against the real API, Postgres and a fake Bot API:
#
#   COMPOSE_PROJECT_NAME=<unique> TELEGRAM_E2E_ARTIFACTS=<dir> scripts/run_telegram_e2e.sh
#
# Links a chat with a one-time code, rejects a used and an expired code, measures the time from
# dispatch to acknowledgment, then stops the gateway, dispatches again, fails the first send and
# restarts the gateway twice: each pending message must arrive exactly once. Writes
# telegram-e2e.json, transcript.png and summary.txt. Remove the project afterwards with
#   docker compose --project-name <unique> --profile telegram --profile telegram-e2e down -v
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COMPOSE_PROJECT_NAME:?set a unique COMPOSE_PROJECT_NAME; this script never uses the default}"
# A synthetic token for the fake: a real one never leaves the ignored .env of a real install.
export COMPOSE_PROJECT_NAME OPENROUTER_API_KEY="" OPENROUTER_MANAGEMENT_API_KEY=""
export TELEGRAM_BOT_TOKEN="7000001:fake-e2e-token" TELEGRAM_API_URL="http://fake-telegram:8081"
export TELEGRAM_POLL_TIMEOUT_SECONDS=5
ARTIFACTS="${TELEGRAM_E2E_ARTIFACTS:-$(mktemp -d "${TMPDIR:-/tmp}/telegram-e2e.XXXXXX")}"
mkdir -p "$ARTIFACTS"
COMPOSE=(docker compose --project-directory "$ROOT" -f "$ROOT/compose.yaml" -f "$ROOT/compose.e2e.yaml"
  --profile telegram --profile telegram-e2e)
STAMP="$(od -An -N4 -tx4 /dev/urandom | tr -d ' \n')"
overlay="$ARTIFACTS/compose.seed.yaml"
cat > "$overlay" <<EOF
services:
  seed:
    volumes: ["$ROOT/scripts:/app/scripts:ro", "$ARTIFACTS:/artifacts"]
    environment: {AUDIT_HMAC_KEY: "\${AUDIT_HMAC_KEY:?AUDIT_HMAC_KEY is required}"}
EOF
SEED=("${COMPOSE[@]}" -f "$overlay" run --rm --no-deps -T --user "$(id -u):$(id -g)")
phase() { "${SEED[@]}" seed python scripts/telegram_e2e.py "$@" | tee -a "$ARTIFACTS/summary.txt"; }
link() {
  "${COMPOSE[@]}" run --rm --no-deps -T telegram-gateway \
    python -m sre_agent.chat.telegram link "$@" | grep -o 'start=[A-Za-z0-9_-]*' | cut -d= -f2
}

rm -f "$ARTIFACTS/telegram-e2e.json" "$ARTIFACTS/summary.txt"
"${COMPOSE[@]}" up --build --wait db api fake-telegram telegram-gateway
"${SEED[@]}" seed python -m sre_agent.persistence.seeds --seed-mcp > /dev/null
"${SEED[@]}" seed python scripts/provision_demo.py > /dev/null
"${SEED[@]}" -e SEED_STAMP="tga$STAMP" seed python scripts/seed_war_room_runs.py > /dev/null
"${SEED[@]}" -e SEED_STAMP="tgb$STAMP" seed python scripts/seed_war_room_runs.py > /dev/null

code="$(link)"
expired="$(link --ttl-seconds 1)"
sleep 2
phase linking "$code" "$expired"
phase dispatch "inc-37-start-tga$STAMP"
"${COMPOSE[@]}" stop telegram-gateway
phase pending "inc-37-start-tgb$STAMP"
"${COMPOSE[@]}" start telegram-gateway
phase delivered after_first_restart
"${COMPOSE[@]}" restart telegram-gateway
phase delivered after_second_restart
"${COMPOSE[@]}" logs --no-color telegram-gateway > "$ARTIFACTS/telegram-gateway.log"
if grep -q "$TELEGRAM_BOT_TOKEN" "$ARTIFACTS/telegram-gateway.log"; then
  echo "FAIL the gateway log contains the bot token" | tee -a "$ARTIFACTS/summary.txt"
  exit 1
fi
echo "PASS the gateway log never contains the bot token" | tee -a "$ARTIFACTS/summary.txt"
"${COMPOSE[@]}" --profile e2e run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$ARTIFACTS:/artifacts" e2e \
  npx playwright screenshot --full-page http://fake-telegram:8081/_test/transcript /artifacts/transcript.png
echo "Artifacts: $ARTIFACTS"
