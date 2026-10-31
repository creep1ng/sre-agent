#!/usr/bin/env bash
# Real-stack browser journeys that CI runs on every pull request, run the same way locally:
#
#   COMPOSE_PROJECT_NAME=<unique> scripts/run_real_journeys.sh incidents|executor
#
# incidents: builds (or reuses) the production-browser stack (compose.yaml + compose.e2e.yaml),
#   seeds the demo grants and one stamped incident per journey, then runs war-room-runs-real,
#   war-room-reasoning-real, review-mitigation-real, war-room-follow-real, postmortem-journey and
#   change-events-real.
# executor: the deploy-executor journey (#720/#743), the rollback recorded as a change event
#   (change-events-real, #770) by the deploy-executor principal that provision_demo.py creates
#   from DEPLOY_EXECUTOR_CHANGES_API_KEY, and the socket-down case.
# Compose reads the untracked .env (from .env.example). The OpenRouter keys are forced empty, so
# no investigation reaches a model provider. Remove the project afterwards with
#   docker compose -f compose.yaml -f compose.e2e.yaml --project-name <unique> --profile e2e \
#     --profile executor-e2e down -v --remove-orphans
# One log per journey, the Playwright artifacts and summary.txt land in JOURNEY_ARTIFACTS
# (default: a new temporary directory). A journey passes only when Playwright exits 0 and
# reports passed tests and no skipped one: a self-skipped journey is not coverage.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COMPOSE_PROJECT_NAME:?set a unique COMPOSE_PROJECT_NAME; this script never uses the default}"
export COMPOSE_PROJECT_NAME OPENROUTER_API_KEY="" OPENROUTER_MANAGEMENT_API_KEY=""
ARTIFACTS="${JOURNEY_ARTIFACTS:-$(mktemp -d "${TMPDIR:-/tmp}/real-journeys.XXXXXX")}"
mkdir -p "$ARTIFACTS"
COMPOSE=(docker compose --project-directory "$ROOT" -f "$ROOT/compose.yaml" -f "$ROOT/compose.e2e.yaml")
# Fresh per run, so a rerun on the same database never meets an incident a journey already moved.
# Ten characters per stamp: run ids need 8+ after `run_`, idempotency keys 16+ in total.
STAMP="$(od -An -N4 -tx4 /dev/urandom | tr -d ' \n')"
failed=0

# run_journey NAME SERVICE [compose run options] -- [playwright arguments]
run_journey() {
  local name=$1 service=$2 opts=() rc=0 start=$SECONDS counts verdict
  shift 2
  while [[ $1 != -- ]]; do opts+=("$1"); shift; done
  shift
  mkdir -p "$ARTIFACTS/$name"
  "${COMPOSE[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e PLAYWRIGHT_OUTPUT_DIR=/artifacts/test-results -v "$ARTIFACTS/$name:/artifacts" "${opts[@]}" \
    "$service" npx playwright test --config=playwright.production.config.js --workers=1 "$@" \
    > "$ARTIFACTS/$name.log" 2>&1 || rc=$?
  cat "$ARTIFACTS/$name.log"
  counts="$(grep -Eo '^ +[0-9]+ (passed|failed|flaky|skipped|interrupted|did not run)' \
    "$ARTIFACTS/$name.log" | xargs || true)"
  if ((rc == 0)) && [[ $counts == *passed* && $counts != *skipped* ]]; then
    verdict=PASS
  else
    verdict=FAIL
    failed=1
  fi
  printf '%-20s %s rc=%s [%s] %ss\n' "$name" "$verdict" "$rc" "$counts" "$((SECONDS - start))" \
    | tee -a "$ARTIFACTS/summary.txt"
}

seed_incident() {  # seed_incident STAMP [SEED_UNTIL]
  "${SEED[@]}" -e SEED_STAMP="$1" -e SEED_UNTIL="${2:-}" seed python scripts/seed_verification_close_demo.py
}

# postmortem-journey starts from a resolved incident: the approval and the verification go
# through the HTTP API as demo-human, as the operator sends them.
resolve_incident() {
  "${SEED[@]}" -e INCIDENT="inc-vc-$1" -e RUN="run_vc$1" seed python - <<'PY'
import json, os, urllib.request

base, run = f"http://api:8000/v1/incidents/{os.environ['INCIDENT']}", os.environ["RUN"]
headers = {"Authorization": "Bearer " + os.environ["DEMO_HUMAN_API_KEY"], "Content-Type": "application/json"}
for command in ("approve_mitigation", "verification_passed"):
    with urllib.request.urlopen(urllib.request.Request(base, headers=headers), timeout=30) as reply:
        version = json.load(reply)["version"]
    body = {"command": command, "expected_incident_version": version, "actor": "human",
            "actor_reference": {"reference_version": "1.0.0", "principal_id": "demo-human"}}
    sent = urllib.request.Request(f"{base}/runs/{run}/commands", json.dumps(body).encode(),
                                  headers | {"Idempotency-Key": f"journey-{command}-{run}"}, method="POST")
    with urllib.request.urlopen(sent, timeout=30) as reply:
        print(f"{command}: HTTP {reply.status}")
PY
}

# war-room-follow-real watches a live run: once its first test has begun, a second seed of the
# live stamp records the hypothesis while the page waits for it (the spec allows 120 s).
finish_live_incident() {
  local _
  for _ in $(seq 180); do
    if grep -q "while the agent investigates" "$ARTIFACTS/war-room-follow.log" 2>/dev/null; then
      sleep 10
      seed_incident "lv$STAMP"
      return
    fi
    sleep 1
  done
  return 1
}

# Starts db, api and web, then seeds them with the demo grants and principals.
start_seeded_stack() {
  local overlay="$ARTIFACTS/compose.seed.yaml"
  # The seed image has no scripts/ and the compose seed service has no audit key.
  cat > "$overlay" <<EOF
services:
  seed:
    volumes: ["$ROOT/scripts:/app/scripts:ro"]
    environment: {AUDIT_HMAC_KEY: "\${AUDIT_HMAC_KEY:?AUDIT_HMAC_KEY is required}"}
EOF
  SEED=("${COMPOSE[@]}" -f "$overlay" run --rm --no-deps -T)
  "${COMPOSE[@]}" up --build --wait db api web
  "${SEED[@]}" seed python -m sre_agent.persistence.seeds --seed-mcp
  "${SEED[@]}" seed python scripts/provision_demo.py
}

incidents() {
  local follower
  start_seeded_stack
  "${COMPOSE[@]}" --profile e2e build e2e
  "${SEED[@]}" -e SEED_STAMP="wr$STAMP" seed python scripts/seed_war_room_runs.py
  # One incident per journey: review-mitigation and war-room-follow both approve theirs.
  for prefix in rs rv fw pm; do seed_incident "$prefix$STAMP"; done
  seed_incident "lv$STAMP" start_investigation
  resolve_incident "pm$STAMP"

  run_journey war-room-runs e2e -e SRE_REAL_BACKEND=1 -e SEED_STAMP="wr$STAMP" -- war-room-runs-real
  run_journey war-room-reasoning e2e -e SRE_REAL_BACKEND=1 -e SEED_STAMP="rs$STAMP" -- \
    war-room-reasoning-real
  run_journey review-mitigation e2e -e SRE_REAL_BACKEND=1 -e SEED_STAMP="rv$STAMP" -- \
    review-mitigation-real
  rm -f "$ARTIFACTS/war-room-follow.log"
  finish_live_incident > "$ARTIFACTS/war-room-follow-second-seed.log" 2>&1 &
  follower=$!
  run_journey war-room-follow e2e -e SRE_REAL_BACKEND=1 -e SEED_STAMP="fw$STAMP" \
    -e LIVE_STAMP="lv$STAMP" -- war-room-follow-real
  kill "$follower" 2> /dev/null || true
  wait "$follower" || echo "war-room-follow: the second seed did not finish (see its log)"
  run_journey postmortem e2e -e POSTMORTEM_INCIDENT="inc-vc-pm$STAMP" -- postmortem-journey
  run_journey change-events e2e -e SRE_REAL_BACKEND=1 -e SEED_STAMP="ch$STAMP" \
    -e CHANGE_EVENTS_ARTIFACT_DIR=/artifacts -- change-events-real --grep-invert deploy-executor
}

executor() {
  local compose=("${COMPOSE[@]}" --profile executor-e2e)
  start_seeded_stack
  "${compose[@]}" build deploy-executor probe probe-previous executor-e2e
  "${compose[@]}" up -d --wait docker-socket-proxy deploy-executor probe
  run_journey executor executor-e2e -- deploy-executor-real --reporter=line,json \
    --grep-invert "socket proxy stopped"
  run_journey executor-changes executor-e2e -e DEPLOY_EXECUTOR_CHANGES_E2E=1 \
    -e CHANGE_EVENTS_ARTIFACT_DIR=/artifacts -- change-events-real --grep deploy-executor
  "${compose[@]}" stop docker-socket-proxy
  run_journey executor-socket-down executor-e2e -e DEPLOY_EXECUTOR_SOCKET_DOWN=1 -- \
    deploy-executor-real --reporter=line,json --grep "socket proxy stopped"
  "${compose[@]}" start docker-socket-proxy
}

case "${1:-}" in
  incidents) incidents ;;
  executor) executor ;;
  *) echo "usage: COMPOSE_PROJECT_NAME=<unique> $0 incidents|executor" >&2; exit 2 ;;
esac
echo "Artifacts: $ARTIFACTS"
cat "$ARTIFACTS/summary.txt"
exit "$failed"
