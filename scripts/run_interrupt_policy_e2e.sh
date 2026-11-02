#!/usr/bin/env bash
# Interrupt-policy E2E (#771) against the real API, Postgres, Telegram gateway and a fake Bot API:
#
#   [INTERRUPT_POLICY_ARTIFACTS=<dir>] scripts/run_interrupt_policy_e2e.sh
#
# Uses the worktree's .env and .env.worktree (scripts/bootstrap-worktree.py). Links the operator's
# chat, plays a quiet day (deploys and a CI run, no alert) and queues its digest, then a healthy
# deploy, a spike that recovers before its investigation ends and a broken sre-checkout deploy,
# and queues the next digest; finally reads GET /v1/event-decisions and opens every link. Writes
# interrupt-policy-e2e.json, event-decisions.json, summary.txt and transcript.png, and always
# removes the project (`down -v --remove-orphans`) on exit.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$ROOT/.env" && -f "$ROOT/.env.worktree" ]] || { echo "run scripts/bootstrap-worktree.py" >&2; exit 2; }
# The fake's synthetic token (tests/fake_telegram.py); no model key: the model is scripted.
export OPENROUTER_API_KEY="" OPENROUTER_MANAGEMENT_API_KEY=""
export TELEGRAM_BOT_TOKEN="7000001:fake-e2e-token" TELEGRAM_API_URL="http://fake-telegram:8081"
export TELEGRAM_POLL_TIMEOUT_SECONDS=5
ARTIFACTS="${INTERRUPT_POLICY_ARTIFACTS:-$(mktemp -d "${TMPDIR:-/tmp}/interrupt-policy.XXXXXX")}"
mkdir -p "$ARTIFACTS"
export INTERRUPT_POLICY_ARTIFACTS="$(cd "$ARTIFACTS" && pwd)"
COMPOSE=(docker compose --project-directory "$ROOT" --env-file "$ROOT/.env"
  --env-file "$ROOT/.env.worktree" -f "$ROOT/compose.yaml" -f "$ROOT/compose.e2e.yaml"
  -f "$ROOT/compose.interrupt-policy-e2e.yaml" --profile telegram --profile telegram-e2e)
trap '"${COMPOSE[@]}" --profile e2e down -v --remove-orphans' EXIT
SEED=("${COMPOSE[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" seed)
phase() { "${SEED[@]}" python scripts/interrupt_policy_e2e.py "$@" | tee -a "$INTERRUPT_POLICY_ARTIFACTS/summary.txt"; }

rm -f "$INTERRUPT_POLICY_ARTIFACTS"/{interrupt-policy-e2e.json,event-decisions.json,summary.txt}
"${COMPOSE[@]}" up --build --wait db api fake-telegram telegram-gateway
"${SEED[@]}" python -m sre_agent.persistence.seeds --seed-mcp > /dev/null
"${SEED[@]}" python scripts/provision_demo.py > /dev/null
code="$("${COMPOSE[@]}" run --rm --no-deps -T telegram-gateway python -m sre_agent.chat.telegram \
  link --principal demo-human | grep -o 'start=[A-Za-z0-9_-]*' | cut -d= -f2)"
phase link "$code"
phase quiet_day
phase three_events
"${COMPOSE[@]}" --profile e2e run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$INTERRUPT_POLICY_ARTIFACTS:/artifacts" e2e npx playwright screenshot --full-page \
  http://fake-telegram:8081/_test/transcript /artifacts/transcript.png
echo "Artifacts: $INTERRUPT_POLICY_ARTIFACTS"
