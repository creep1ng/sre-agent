#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/triage23-${RUN_ID}.XXXXXX")"
chmod 700 "$RUN_DIR"
ARTIFACTS="$RUN_DIR/artifacts"
mkdir -m 700 "$ARTIFACTS"
touch "$ARTIFACTS/credentials.env"
chmod 600 "$ARTIFACTS/credentials.env"
PROJECT="triage23-${RUN_ID,,}"
cat > "$RUN_DIR/compose.env" <<EOF
COMPOSE_PROJECT_NAME=$PROJECT
T23_ARTIFACTS_DIR=$ARTIFACTS
T23_CREDENTIALS_FILE=$ARTIFACTS/credentials.env
EOF
chmod 600 "$RUN_DIR/compose.env"
COMPOSE=(docker compose --env-file "$RUN_DIR/compose.env" -f "$ROOT/compose.triage23.yaml")
if [[ -n "${T23_NETWORK_SUBNET:-}" ]]; then
  printf 'T23_NETWORK_SUBNET=%s\n' "$T23_NETWORK_SUBNET" >> "$RUN_DIR/compose.env"
  COMPOSE+=(-f "$ROOT/compose.triage23.network.yaml")
fi
cleanup() {
  rc=$?
  "${COMPOSE[@]}" down --remove-orphans > "$RUN_DIR/cleanup.log" 2>&1 || true
  printf 'Evidence directory: %s\n' "$RUN_DIR"
  exit "$rc"
}
trap cleanup EXIT

echo "Candidate: $(git -C "$ROOT" rev-parse HEAD)"
echo "Building pinned repository services. Logs: $RUN_DIR/build.log"
"${COMPOSE[@]}" build db seed api web e2e 2>&1 | tee "$RUN_DIR/build.log"
"${COMPOSE[@]}" up -d db 2>&1 | tee "$RUN_DIR/db.log"
"${COMPOSE[@]}" run --build --rm --user "$(id -u):$(id -g)" seed 2>&1 | tee "$RUN_DIR/seed.log"
test "$(stat -c '%a' "$ARTIFACTS/credentials.env")" = 600
"${COMPOSE[@]}" up -d api web 2>&1 | tee "$RUN_DIR/services.log"
echo "Running all eight selected suites (46 tests) with one worker; logs: $RUN_DIR/browser.log"
set +e
"${COMPOSE[@]}" run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp e2e sh /run/triage23-browser.sh \
  > "$RUN_DIR/browser.log" 2>&1
rc=$?
set -e
if (( rc != 0 )); then cat "$RUN_DIR/browser.log" >&2; exit "$rc"; fi
cat "$RUN_DIR/browser.log"
echo "Real screenshots: $ARTIFACTS/external-origin.png, $ARTIFACTS/recovery.png, $ARTIFACTS/c3a-session-isolation.png, $ARTIFACTS/c3e-ca5-forbidden.png"
