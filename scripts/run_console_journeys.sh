#!/usr/bin/env bash
# Browser journeys of the new console (/app) against the composed stack, run the same way in CI:
#
#   COMPOSE_PROJECT_NAME=<unique> scripts/run_console_journeys.sh
#
# Starts db, api and web with compose.console-e2e.yaml (real API, database, investigator and web
# proxy; scripted model and Grafana MCP), seeds the demo grants and runs
# web/incident-console/e2e/live-investigation.spec.ts in the incident-console-e2e runner.
# Compose reads the untracked .env (from .env.example). Screenshots and verification.json land in
# web/incident-console/e2e/artifacts/live-investigation. Remove the project afterwards with
#   docker compose -f compose.yaml -f compose.e2e.yaml -f compose.console-e2e.yaml \
#     --project-name <unique> --profile e2e down -v --remove-orphans
# It passes only when Playwright exits 0 and reports passed tests and no skipped one.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COMPOSE_PROJECT_NAME:?set a unique COMPOSE_PROJECT_NAME; this script never uses the default}"
export COMPOSE_PROJECT_NAME OPENROUTER_API_KEY="" OPENROUTER_MANAGEMENT_API_KEY=""
export HOST_UID HOST_GID
HOST_UID="$(id -u)" HOST_GID="$(id -g)"
COMPOSE=(docker compose --project-directory "$ROOT" -f "$ROOT/compose.yaml" -f "$ROOT/compose.e2e.yaml"
  -f "$ROOT/compose.console-e2e.yaml")
LOG="$ROOT/web/incident-console/e2e/artifacts/live-investigation.log"
mkdir -p "$(dirname "$LOG")"

"${COMPOSE[@]}" up --build --wait db api web
"${COMPOSE[@]}" run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
"${COMPOSE[@]}" run --rm --no-deps -T seed python scripts/provision_demo.py
"${COMPOSE[@]}" --profile e2e build incident-console-e2e
rc=0
# The runner expands HOST_UID and HOST_GID, which it receives with -e.
# shellcheck disable=SC2016
"${COMPOSE[@]}" --profile e2e run --rm --no-deps -T -e HOST_UID -e HOST_GID incident-console-e2e sh -c \
  'npx playwright test live-investigation; rc=$?; chown -R "$HOST_UID:$HOST_GID" e2e/artifacts; exit $rc' \
  > "$LOG" 2>&1 || rc=$?
cat "$LOG"
counts="$(grep -Eo '^ +[0-9]+ (passed|failed|flaky|skipped|interrupted|did not run)' "$LOG" | xargs || true)"
if ((rc == 0)) && [[ $counts == *passed* && $counts != *skipped* ]]; then
  echo "console journeys PASS [$counts]"
else
  echo "console journeys FAIL rc=$rc [$counts]"
  exit 1
fi
