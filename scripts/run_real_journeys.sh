#!/usr/bin/env bash
# Real-stack browser journeys that CI runs on every pull request, run the same way locally:
#
#   COMPOSE_PROJECT_NAME=<unique> scripts/run_real_journeys.sh incidents|executor
#
# incidents: builds (or reuses) the production-browser stack (compose.yaml + compose.e2e.yaml),
#   seeds the demo grants and one stamped incident per journey, then runs war-room-runs-real,
#   war-room-reasoning-real, review-mitigation-real, war-room-follow-real, postmortem-journey and
#   change-events-real, and last the #758 consumption-limit and #719 provider-retry E2Es, which
#   restart the API against the local OpenRouter stand-in of compose.consumption-e2e.yaml, then the
#   Grafana alert intake journey (scripts/alert_intake_journey.py, #765).
# executor: the deploy-executor journey (#720/#743), the rollback recorded as a change event
#   (change-events-real, #770) by the deploy-executor principal that provision_demo.py creates
#   from DEPLOY_EXECUTOR_CHANGES_API_KEY, the socket-down case, and its journal cut mid-write,
#   damaged in the middle and cut short by a full disk (#762).
# Compose reads the untracked .env (from .env.example). The OpenRouter keys are forced empty, so
# no investigation reaches a model provider. Remove the project afterwards with
#   docker compose -f compose.yaml -f compose.e2e.yaml --project-name <unique> --profile e2e \
#     --profile executor-e2e --profile telegram --profile telegram-e2e down -v --remove-orphans
# One log per journey, the Playwright artifacts and summary.txt land in JOURNEY_ARTIFACTS
# (default: a new temporary directory). A journey passes only when Playwright exits 0 and
# reports passed tests and no skipped one: a self-skipped journey is not coverage.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${COMPOSE_PROJECT_NAME:?set a unique COMPOSE_PROJECT_NAME; this script never uses the default}"
export COMPOSE_PROJECT_NAME OPENROUTER_API_KEY="" OPENROUTER_MANAGEMENT_API_KEY=""
# A fresh intake secret per run; the .env placeholder never reaches the API.
ALERT_INTAKE_GRAFANA_SECRET="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
export ALERT_INTAKE_GRAFANA_SECRET
# The intake journey's chat goes through the fake Bot API (tests/fake_telegram.py) only.
export TELEGRAM_BOT_TOKEN="7000001:fake-e2e-token" TELEGRAM_API_URL="http://fake-telegram:8081"
export TELEGRAM_POLL_TIMEOUT_SECONDS=5
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

# run_check NAME COMMAND...: a journey outside the browser; it passes when the command exits 0.
run_check() {
  local name=$1 rc=0 start=$SECONDS verdict=PASS
  shift
  "$@" > "$ARTIFACTS/$name.log" 2>&1 || rc=$?
  cat "$ARTIFACTS/$name.log"
  if ((rc != 0)); then
    verdict=FAIL
    failed=1
  fi
  printf '%-20s %s rc=%s %ss\n' "$name" "$verdict" "$rc" "$((SECONDS - start))" \
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
  consumption
  # Last: intake declares incidents of its own, which no journey above expects.
  alert_intake
}

# consumption: scripts/consumption_limits_e2e.py, after the browser journeys because it points
# the API at the stand-in (the forced-empty OpenRouter keys are replaced by the overlay's fakes);
# then scripts/provider_retry_e2e.py (#719), with the API restarted on short provider and tool
# timeouts.
consumption() {
  stand_in consumption consumption-e2e issue-758-e2e.txt compose.consumption-e2e.yaml
  stand_in provider-retry provider-retry-e2e issue-719-e2e.txt compose.consumption-e2e.yaml \
    compose.provider-retry-e2e.yaml
}

# stand_in NAME SERVICE SUMMARY OVERLAY...: restarts the API with the overlays, then runs SERVICE.
stand_in() {
  local name=$1 service=$2 summary=$3 compose=("${COMPOSE[@]}") overlay
  local rc=0 start=$SECONDS verdict=PASS
  shift 3
  for overlay; do compose+=(-f "$ROOT/$overlay"); done
  compose+=(--profile "$service")
  mkdir -p "$ARTIFACTS/$name"
  "${compose[@]}" up --build --wait api fake-openrouter
  "${compose[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e ARTIFACT_DIR=/artifacts -v "$ARTIFACTS/$name:/artifacts" "$service" \
    > "$ARTIFACTS/$name.log" 2>&1 || rc=$?
  cat "$ARTIFACTS/$name.log"
  if ((rc != 0)); then
    verdict=FAIL
    failed=1
  fi
  printf '%-20s %s rc=%s [%s] %ss\n' "$name" "$verdict" "$rc" \
    "$(tail -n 1 "$ARTIFACTS/$name/$summary" 2> /dev/null || echo no summary)" \
    "$((SECONDS - start))" | tee -a "$ARTIFACTS/summary.txt"
}

# alert_intake: scripts/alert_intake_journey.py (#765), Grafana's deliveries against the API, with
# a Telegram gateway on the fake Bot API so the automatic investigation's acknowledgment is seen.
alert_intake() {
  local telegram=("${COMPOSE[@]}" --profile telegram --profile telegram-e2e) code
  mkdir -p "$ARTIFACTS/alert-intake"
  "${telegram[@]}" up --build --wait fake-telegram telegram-gateway
  code="$("${telegram[@]}" run --rm --no-deps -T telegram-gateway python -m sre_agent.chat.telegram \
    link | grep -o 'start=[A-Za-z0-9_-]*' | cut -d= -f2)"
  run_check alert-intake "${SEED[@]}" --user "$(id -u):$(id -g)" -e ALERT_INTAKE_GRAFANA_SECRET \
    -e TELEGRAM_LINK_CODE="$code" -v "$ARTIFACTS/alert-intake:/artifacts" seed \
    python scripts/alert_intake_journey.py
}

executor() {
  local compose=("${COMPOSE[@]}" --profile executor-e2e)
  start_seeded_stack
  "${compose[@]}" build deploy-executor probe probe-previous executor-e2e
  "${compose[@]}" up -d --wait docker-socket-proxy deploy-executor probe
  run_journey executor executor-e2e -- deploy-executor-real --reporter=line,json \
    --grep-invert "socket proxy stopped|journal:"
  run_journey executor-changes executor-e2e -e DEPLOY_EXECUTOR_CHANGES_E2E=1 \
    -e CHANGE_EVENTS_ARTIFACT_DIR=/artifacts -- change-events-real --grep deploy-executor
  "${compose[@]}" stop docker-socket-proxy
  run_journey executor-socket-down executor-e2e -e DEPLOY_EXECUTOR_SOCKET_DOWN=1 -- \
    deploy-executor-real --reporter=line,json --grep "socket proxy stopped"
  "${compose[@]}" start docker-socket-proxy
  executor_journal "${compose[@]}"
  executor_journal_volume "${compose[@]}"
}

# #762: cut a restart intent mid-write, as a crash or a full disk would, then damage a middle line.
executor_journal() {
  local compose=("$@") cut key
  cut="$("${compose[@]}" exec -T deploy-executor python - << 'EOF'
import hashlib, json, uuid
key, execution_id = str(uuid.uuid4()), "exe_" + uuid.uuid4().hex[:16]
line = json.dumps({
    "kind": "intent",
    "binding": "deployment.restart:" + hashlib.sha256(key.encode()).hexdigest(),
    "payload_digest": hashlib.sha256(json.dumps({"service": "probe"}).encode()).hexdigest(),
    "execution_id": execution_id, "operation": "deployment.restart", "service": "probe",
    "parameters": {}, "requested_at": "2026-10-30T00:00:00.000Z"}, separators=(",", ":"))
with open("/var/lib/deploy-executor/executions.jsonl", "a") as journal:
    journal.write(line[: line.index(',"service"') + 8])
print(key, execution_id)
EOF
)"
  read -r key cut <<< "$cut"
  "${compose[@]}" restart deploy-executor
  "${compose[@]}" up -d --wait deploy-executor
  run_journey executor-journal-tail executor-e2e -e DEPLOY_EXECUTOR_JOURNAL=tail \
    -e JOURNAL_KEY="$key" -e JOURNAL_EXECUTION_ID="$cut" -- \
    deploy-executor-real --reporter=line,json --grep "journal: a last line"
  "${compose[@]}" exec -T deploy-executor python -c '
path = "/var/lib/deploy-executor/executions.jsonl"
lines = open(path).read().splitlines(keepends=True)
open(path, "w").writelines(lines[:-1] + ["{\"kind\n"] + lines[-1:])'
  "${compose[@]}" restart deploy-executor
  run_journey executor-journal-damaged executor-e2e -e DEPLOY_EXECUTOR_JOURNAL=damaged -- \
    deploy-executor-real --reporter=line,json --grep "journal: a damaged"
  docker inspect -f 'restarts={{.RestartCount}} state={{.State.Status}}' \
    "$("${compose[@]}" ps -q deploy-executor)" | tee "$ARTIFACTS/executor-journal-damaged.state"
  # Repair as an operator would (drop the damaged line), so the stack is left as found.
  "${compose[@]}" exec -T deploy-executor python -c '
path = "/var/lib/deploy-executor/executions.jsonl"
lines = open(path).read().splitlines(keepends=True)
open(path, "w").writelines(lines[:-2] + lines[-1:])'
  "${compose[@]}" restart deploy-executor
  "${compose[@]}" up -d --wait deploy-executor
}

# #762: a full disk while the executor stays up.
executor_journal_volume() {
  local compose=("$@") key full=("$@" -f "$ARTIFACTS/compose.disk-full.yaml")
  key="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
  # A 64 KiB tmpfs journal: the next intent is written in part, then the write fails (ENOSPC).
  cat > "$ARTIFACTS/compose.disk-full.yaml" << 'EOF'
services:
  deploy-executor:
    environment: {DEPLOY_EXECUTOR_JOURNAL: /var/lib/deploy-executor-full/executions.jsonl}
    tmpfs: ["/tmp", "/var/lib/deploy-executor-full:size=64k,uid=65532,gid=65532,mode=0700"]
EOF
  "${full[@]}" up -d --wait deploy-executor
  "${full[@]}" exec -T deploy-executor python -c '
directory = "/var/lib/deploy-executor-full"
with open(f"{directory}/executions.jsonl", "w") as journal:
    journal.write("\n" * 3996)  # blank lines, skipped at load: 100 bytes left in its page
try:
    with open(f"{directory}/filler", "wb", buffering=0) as filler:
        while True:
            filler.write(bytes(4096))
except OSError as error:
    print("filled:", error.strerror)'
  run_journey executor-journal-disk-full executor-e2e -e DEPLOY_EXECUTOR_JOURNAL=full \
    -e JOURNAL_KEY="$key" -- deploy-executor-real --reporter=line,json --grep "journal: a full disk"
  "${full[@]}" exec -T deploy-executor python -c '
import os
path = "/var/lib/deploy-executor-full/executions.jsonl"
raw = open(path, "rb").read()
print(f"after the failed append: size={len(raw)} ends_with_newline={raw.endswith(bytes([10]))}")
os.remove("/var/lib/deploy-executor-full/filler")' | tee "$ARTIFACTS/executor-journal-disk-full.journal"
  run_journey executor-journal-freed executor-e2e -e DEPLOY_EXECUTOR_JOURNAL=freed \
    -e JOURNAL_KEY="$key" -- deploy-executor-real --reporter=line,json --grep "journal: a full disk"
  # What the next start reads: the same file, no damaged line, the retried key bound once.
  "${full[@]}" exec -T deploy-executor python -c '
from pathlib import Path
from sre_agent.executor.app import Journal
journal = Journal(Path("/var/lib/deploy-executor-full/executions.jsonl"))
print(f"reloaded: problem={journal.problem} records={len(journal.records)}")' \
    | tee -a "$ARTIFACTS/executor-journal-disk-full.journal"
  "${compose[@]}" up -d --wait deploy-executor
}

case "${1:-}" in
  incidents) incidents ;;
  executor) executor ;;
  *) echo "usage: COMPOSE_PROJECT_NAME=<unique> $0 incidents|executor" >&2; exit 2 ;;
esac
echo "Artifacts: $ARTIFACTS"
cat "$ARTIFACTS/summary.txt"
exit "$failed"
