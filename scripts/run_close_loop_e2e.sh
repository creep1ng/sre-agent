#!/usr/bin/env bash
# The close-the-loop journey (#723) against the composed stack:
#
#   COMPOSE_PROJECT_NAME=<unique> scripts/run_close_loop_e2e.sh
#
# Starts db, api, web, the deploy-executor and this project's sre-checkout (1.5.0 runs, 1.4.0 waits
# in the image store), seeds the demo grants and runs web/incident-console/e2e/close-loop.spec.ts.
# Keys are synthetic, from .env.example for this run only: .env is never read. Screenshots,
# report.json and checkout-images.txt land in web/incident-console/e2e/artifacts/close-loop.
# The project and its volumes are removed on exit; nothing outside it is touched.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COMPOSE_PROJECT_NAME:?set a unique COMPOSE_PROJECT_NAME; this script never uses the default}"
export COMPOSE_PROJECT_NAME HOST_UID HOST_GID
HOST_UID="$(id -u)" HOST_GID="$(id -g)"
hex() { od -An -N32 -tx1 /dev/urandom | tr -d ' \n'; }
env="$(<"$ROOT/.env.example")"
for role in admn demo inci rest chng; do
  env="${env/<set-unique-sre_-prefixed-key-with-32-plus-characters>/sre_${role}_$(hex)}"
done
env="${env//<set-long-random-audit-hmac-key>/$(hex)}"
env="${env//<set-long-random-executor-signing-key>/$(hex)}"
env="${env//<set-long-random-grafana-intake-secret>/$(hex)}"
env="${env//<lab\/model>/openai/gpt-4o-mini}"
env="${env//<provider>/openai}"
ENV_FILE="$(mktemp)"
printf '%s\n' "$env" > "$ENV_FILE"
COMPOSE=(docker compose --project-directory "$ROOT" --env-file "$ENV_FILE" -f "$ROOT/compose.yaml"
  -f "$ROOT/compose.e2e.yaml" -f "$ROOT/compose.incident-console-e2e.yaml"
  -f "$ROOT/compose.close-loop-e2e.yaml")
trap '"${COMPOSE[@]}" --profile e2e down -v --remove-orphans; rm -f "$ENV_FILE"' EXIT
ARTIFACTS="$ROOT/web/incident-console/e2e/artifacts/close-loop"
LOG="$ARTIFACTS/journey.log"
mkdir -p "$ARTIFACTS"
# The image sre-checkout runs, read from the host: the runner has no Docker access.
checkout_image() {
  docker ps --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" \
    --filter "label=com.docker.compose.service=sre-checkout" --format '{{.Image}}'
}

# The db healthcheck answers on the socket while a fresh volume still initialises; migrate needs TCP.
"${COMPOSE[@]}" up --wait db
"${COMPOSE[@]}" exec -T db sh -c 'for _ in $(seq 60); do pg_isready -h 127.0.0.1 -q && exit 0; sleep 1; done; exit 1'
"${COMPOSE[@]}" up --build --wait db api web deploy-executor sre-checkout
# The rollback target only has to be in the image store; it never runs.
"${COMPOSE[@]}" --profile e2e build sre-checkout-previous
"${COMPOSE[@]}" run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
"${COMPOSE[@]}" run --rm --no-deps -T seed python scripts/provision_demo.py
"${COMPOSE[@]}" --profile e2e build incident-console-e2e
rc=0
before="$(checkout_image)"
# The runner expands HOST_UID and HOST_GID, which it receives with -e.
# shellcheck disable=SC2016
"${COMPOSE[@]}" --profile e2e run --rm --no-deps -T -e HOST_UID -e HOST_GID incident-console-e2e sh -c \
  'npx playwright test close-loop; rc=$?; chown -R "$HOST_UID:$HOST_GID" e2e/artifacts; exit $rc' \
  > "$LOG" 2>&1 || rc=$?
after="$(checkout_image)"
printf 'sre-checkout before the journey: %s\nsre-checkout after the journey: %s\n' "$before" "$after" |
  tee "$ARTIFACTS/checkout-images.txt"
[[ $before == midnight-e2e/checkout:1.5.0 && $after == midnight-e2e/checkout:1.4.0 ]] || rc=1
cat "$LOG"
counts="$(grep -Eo '^ +[0-9]+ (passed|failed|flaky|skipped|interrupted|did not run)' "$LOG" | xargs || true)"
if ((rc == 0)) && [[ $counts == *passed* && $counts != *skipped* && $counts != *failed* ]]; then
  echo "close-the-loop journey PASS [$counts]"
else
  echo "close-the-loop journey FAIL rc=$rc [$counts]"
  exit 1
fi
