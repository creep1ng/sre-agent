#!/usr/bin/env bash
# Browser journeys of the RC-2 action catalog (/app/acciones, #870, #722) against the composed stack:
#
#   COMPOSE_PROJECT_NAME=<unique> scripts/run_action_catalog_e2e.sh
#
# Starts db, api, web, the deploy-executor and this project's sre-checkout (1.5.0, with 1.4.0 in
# the image store) with compose.incident-console-e2e.yaml and compose.action-catalog-e2e.yaml,
# seeds the demo grants and runs web/incident-console/e2e/catalog-live.spec.ts: the catalog before
# any fault, a real approval on the incident page that rolls sre-checkout back, and the run on the
# catalog. Then it stops the executor and runs the unavailable journey. Compose reads the untracked
# .env; without one, .env.example with synthetic keys for this run only. Screenshots and the
# verification JSON land in web/incident-console/e2e/artifacts/action-catalog, the images before
# and after in checkout-images.txt. The project is removed on exit.
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
  -f "$ROOT/compose.e2e.yaml" -f "$ROOT/compose.incident-console-e2e.yaml"
  -f "$ROOT/compose.action-catalog-e2e.yaml" --profile action-catalog-e2e)
trap '"${COMPOSE[@]}" --profile e2e down -v --remove-orphans; [[ $ENV_FILE == "$ROOT/.env" ]] || rm -f "$ENV_FILE"' EXIT
ARTIFACTS="$ROOT/web/incident-console/e2e/artifacts/action-catalog"
LOG="$ARTIFACTS/journeys.log"
mkdir -p "$ARTIFACTS"
: > "$LOG"
# The image sre-checkout runs, read from the host: the runner has no Docker access.
checkout_image() {
  docker ps --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" \
    --filter "label=com.docker.compose.service=sre-checkout" --format '{{.Image}}'
}
journey() {
  # The runner expands HOST_UID and HOST_GID, which it receives with -e.
  # shellcheck disable=SC2016
  "${COMPOSE[@]}" --profile e2e run --rm --no-deps -T -e HOST_UID -e HOST_GID -e GREP="$1" \
    incident-console-e2e sh -c \
    'npx playwright test catalog-live -g "$GREP"; rc=$?; chown -R "$HOST_UID:$HOST_GID" e2e/artifacts; exit $rc' \
    >> "$LOG" 2>&1
}

# The db healthcheck answers on the socket while a fresh volume still initialises; migrate needs TCP.
"${COMPOSE[@]}" up --wait db
"${COMPOSE[@]}" exec -T db sh -c 'for _ in $(seq 60); do pg_isready -h 127.0.0.1 -q && exit 0; sleep 1; done; exit 1'
"${COMPOSE[@]}" build sre-checkout-previous
"${COMPOSE[@]}" up --build --wait db api web deploy-executor sre-checkout
"${COMPOSE[@]}" run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
"${COMPOSE[@]}" run --rm --no-deps -T seed python scripts/provision_demo.py
"${COMPOSE[@]}" --profile e2e build incident-console-e2e
rc=0
before="$(checkout_image)"
journey "ejecución en el catálogo" || rc=$?
after="$(checkout_image)"
printf 'sre-checkout image before the approval: %s\nsre-checkout image after the approval: %s\n' \
  "$before" "$after" | tee "$ARTIFACTS/checkout-images.txt"
[[ $before == demo/checkout:1.5.0 && $after == demo/checkout:1.4.0 ]] || rc=1
"${COMPOSE[@]}" stop deploy-executor
journey "ejecutor detenido" || rc=$?
cat "$LOG"
counts="$(grep -Eo '^ +[0-9]+ (passed|failed|flaky|skipped|interrupted|did not run)' "$LOG" | xargs || true)"
if ((rc == 0)) && [[ $counts == *passed* && $counts != *skipped* && $counts != *failed* ]]; then
  echo "action catalog journeys PASS [$counts]"
else
  echo "action catalog journeys FAIL rc=$rc [$counts]"
  exit 1
fi
