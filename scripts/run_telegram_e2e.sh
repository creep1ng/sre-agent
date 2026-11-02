#!/usr/bin/env bash
# Telegram channel E2E (#766, #767) against the real API, Postgres and a fake Bot API:
#
#   COMPOSE_PROJECT_NAME=<unique> [TELEGRAM_E2E_ARTIFACTS=<dir>] scripts/run_telegram_e2e.sh
#
# Links a chat with a one-time code, rejects a used and an expired code and a group chat,
# measures the time from dispatch to acknowledgment, then stops the gateway, dispatches again,
# fails the first send and restarts the gateway twice: each pending message must arrive once.
# Then it proposes five mitigations: each must reach the chat as one decision message with
# buttons, and the taps decide them: approve, a double tap, taps from a stranger, a second linked
# chat and another user, a human without run.approve and then deactivated, a console rejection
# (which edits the message with no tap), a reject and a tap after the incident changed. Then a
# passed and a failed verification edit their decision messages again. Finally it unlinks the chat, dispatches a third
# time and taps, before and after linking again: nothing may reach the chat or be decided. Writes
# telegram-e2e.json, transcript.png, summary.txt and migrate.log, and always removes the project
# (`down -v --remove-orphans`) on exit. Uses the repository's .env or, when there is none,
# .env.example with synthetic keys for this run only.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COMPOSE_PROJECT_NAME:?set a unique COMPOSE_PROJECT_NAME; this script never uses the default}"
# The fake's synthetic token (tests/fake_telegram.py): a real one stays in a real install's .env.
export COMPOSE_PROJECT_NAME OPENROUTER_API_KEY="" OPENROUTER_MANAGEMENT_API_KEY=""
export TELEGRAM_BOT_TOKEN="7000001:fake-e2e-token" TELEGRAM_API_URL="http://fake-telegram:8081"
export TELEGRAM_POLL_TIMEOUT_SECONDS=5
# Chat times in Bogotá and a console link on a host the fake accepts link buttons for.
export TELEGRAM_TIMEZONE="America/Bogota" CONSOLE_PUBLIC_URL="http://midnight.example:8080/app/"
ARTIFACTS="${TELEGRAM_E2E_ARTIFACTS:-$(mktemp -d "${TMPDIR:-/tmp}/telegram-e2e.XXXXXX")}"
mkdir -p "$ARTIFACTS"
ARTIFACTS="$(cd "$ARTIFACTS" && pwd)"
export TELEGRAM_E2E_ARTIFACTS="$ARTIFACTS"  # mounted by compose.telegram-e2e.yaml
ENV_FILE="$ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  hex() { od -An -N32 -tx1 /dev/urandom | tr -d ' \n'; }
  env="$(<"$ROOT/.env.example")"
  for role in admn demo inci rest exec; do
    env="${env/<set-unique-sre_-prefixed-key-with-32-plus-characters>/sre_${role}_$(hex)}"
  done
  env="${env//<set-long-random-audit-hmac-key>/$(hex)}"
  env="${env//<set-long-random-executor-signing-key>/$(hex)}"
  env="${env//<lab\/model>/openai/gpt-4o-mini}"
  env="${env//<provider>/openai}"
  ENV_FILE="$(mktemp)"
  printf '%s\n' "$env" > "$ENV_FILE"
fi
COMPOSE=(docker compose --project-directory "$ROOT" --env-file "$ENV_FILE" -f "$ROOT/compose.yaml"
  -f "$ROOT/compose.e2e.yaml" --profile telegram --profile telegram-e2e)
trap '"${COMPOSE[@]}" logs --no-color migrate > "$ARTIFACTS/migrate.log" 2>&1
  "${COMPOSE[@]}" --profile e2e down -v --remove-orphans; [[ $ENV_FILE == "$ROOT/.env" ]] || rm -f "$ENV_FILE"' EXIT
STAMP="$(od -An -N4 -tx4 /dev/urandom | tr -d ' \n')"
SEED=("${COMPOSE[@]}" -f "$ROOT/compose.telegram-e2e.yaml" run --rm --no-deps -T
  --user "$(id -u):$(id -g)" -e CONSOLE_PUBLIC_URL)
phase() { "${SEED[@]}" seed python scripts/telegram_e2e.py "$@" | tee -a "$ARTIFACTS/summary.txt"; }
chat() { "${COMPOSE[@]}" run --rm --no-deps -T telegram-gateway python -m sre_agent.chat.telegram "$@"; }
link() { chat link "$@" | grep -o 'start=[A-Za-z0-9_-]*' | cut -d= -f2; }

rm -f "$ARTIFACTS/telegram-e2e.json" "$ARTIFACTS/summary.txt"
"${COMPOSE[@]}" up --build --wait db api fake-telegram telegram-gateway
"${SEED[@]}" seed python -m sre_agent.persistence.seeds --seed-mcp > /dev/null
"${SEED[@]}" seed python scripts/provision_demo.py > /dev/null
for run in a b c; do
  "${SEED[@]}" -e SEED_STAMP="tg$run$STAMP" seed python scripts/seed_war_room_runs.py > /dev/null
done

code="$(link --principal demo-human)"
expired="$(link --principal demo-human --ttl-seconds 1)"
group="$(link --principal demo-human)"
sleep 2
phase linking "$code" "$expired" "$group"
phase dispatch "inc-37-start-tga$STAMP"
"${COMPOSE[@]}" stop telegram-gateway
phase pending "inc-37-start-tgb$STAMP"
"${COMPOSE[@]}" start telegram-gateway
phase delivered after_first_restart
"${COMPOSE[@]}" restart telegram-gateway
phase delivered after_second_restart
phase enlist
phase proposals "$STAMP" "$(link --principal demo-human)"
for step in approve double_tap stranger second viewer console reject stale recovery; do
  phase "$step"
done
chat links > "$ARTIFACTS/links-before.txt"
for extra in 777 555 666; do chat unlink "$extra" > /dev/null; done
chat unlink 222 > "$ARTIFACTS/unlink.txt"
chat links > "$ARTIFACTS/links-after.txt"
phase unlinked "inc-37-start-tgc$STAMP"
phase unlinked_tap "$(link --principal demo-human)"
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
