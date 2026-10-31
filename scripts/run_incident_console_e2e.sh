#!/usr/bin/env bash
# Browser journeys of the RC-2 incident page (/app/incidentes/:id) against the composed stack:
#
#   COMPOSE_PROJECT_NAME=<unique> scripts/run_incident_console_e2e.sh
#
# Starts db, api and web with compose.incident-console-e2e.yaml (real API, database, investigator
# and web proxy; scripted model and Grafana MCP), seeds the demo grants and runs
# web/incident-console/e2e/incident-live.spec.ts in the incident-console-e2e runner. Compose reads
# the untracked .env; without one, .env.example with synthetic keys for this run only. API_PORT,
# WEB_PORT and POSTGRES_PORT override the published ports. Screenshots and verification.json land
# in web/incident-console/e2e/artifacts/incident-live. The project is removed on exit.
# It passes only when Playwright exits 0 and reports passed tests and no skipped one.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COMPOSE_PROJECT_NAME:?set a unique COMPOSE_PROJECT_NAME; this script never uses the default}"
export COMPOSE_PROJECT_NAME OPENROUTER_API_KEY="" OPENROUTER_MANAGEMENT_API_KEY=""
export HOST_UID HOST_GID
HOST_UID="$(id -u)" HOST_GID="$(id -g)"
ENV_FILE="$ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  hex() { od -An -N32 -tx1 /dev/urandom | tr -d ' \n'; }
  env="$(<"$ROOT/.env.example")"
  for role in admn demo inci rest chng; do
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
  -f "$ROOT/compose.e2e.yaml" -f "$ROOT/compose.incident-console-e2e.yaml")
trap '"${COMPOSE[@]}" --profile e2e down -v --remove-orphans; [[ $ENV_FILE == "$ROOT/.env" ]] || rm -f "$ENV_FILE"' EXIT
LOG="$ROOT/web/incident-console/e2e/artifacts/incident-live.log"
mkdir -p "$(dirname "$LOG")"

# The db healthcheck answers on the socket while a fresh volume still initialises; migrate needs TCP.
"${COMPOSE[@]}" up --wait db
"${COMPOSE[@]}" exec -T db sh -c 'for _ in $(seq 60); do pg_isready -h 127.0.0.1 -q && exit 0; sleep 1; done; exit 1'
"${COMPOSE[@]}" up --build --wait db api web
"${COMPOSE[@]}" run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
"${COMPOSE[@]}" run --rm --no-deps -T seed python scripts/provision_demo.py
"${COMPOSE[@]}" --profile e2e build incident-console-e2e
rc=0
# The runner expands HOST_UID and HOST_GID, which it receives with -e.
# shellcheck disable=SC2016
"${COMPOSE[@]}" --profile e2e run --rm --no-deps -T -e HOST_UID -e HOST_GID incident-console-e2e sh -c \
  'npx playwright test incident-live; rc=$?; chown -R "$HOST_UID:$HOST_GID" e2e/artifacts; exit $rc' \
  > "$LOG" 2>&1 || rc=$?
cat "$LOG"
counts="$(grep -Eo '^ +[0-9]+ (passed|failed|flaky|skipped|interrupted|did not run)' "$LOG" | xargs || true)"
if ((rc == 0)) && [[ $counts == *passed* && $counts != *skipped* ]]; then
  echo "incident console journeys PASS [$counts]"
else
  echo "incident console journeys FAIL rc=$rc [$counts]"
  exit 1
fi
