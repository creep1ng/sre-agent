#!/bin/bash
set -Eeuo pipefail
cd /opt/sre-agent
export DEMO_STATE_DIR=/opt/sre-agent/.demo-state
set -a; source .env; set +a
install -d -m 0700 /opt/issue45-evidence
stage=initial
trap 'rc=$?; if test "$rc" -ne 0; then printf "failed_stage=%s exit=%s\n" "$stage" "$rc"; fi; python3 scripts/demo_env.py reset >/var/log/issue45-cycle-final-reset.log 2>&1 || true' EXIT
capture() {
  local cycle="$1" phase="$2" since="$3" file="/opt/issue45-evidence/cycle-$1-$2.json"
  stage="capture-$cycle-$phase"
  docker compose --env-file .env -p issue45-gateway -f compose.yaml -f compose.mcp.yaml \
    run --pull never --rm --no-deps -e DEMO_HUMAN_API_KEY harness \
    node /source/scripts/demo_signal_capture.mjs capture --cycle "$cycle" --phase "$phase" --settled-since "$since" \
    > "$file" 2> "/var/log/issue45-cycle-$cycle-$phase.stderr.log"
  printf '%s=' "$cycle-$phase"; cat "$file"
}
transition() {
  local state="$1" cycle="$2"
  stage="$state-$cycle"
  python3 scripts/demo_env.py "$state" > "/var/log/issue45-cycle-$cycle-$state.log" 2>&1
  date -u +%Y-%m-%dT%H:%M:%SZ
}
settle() {
  stage="settle-$1"
  sleep 155
}
base1="$(transition reset 1)"
settle 1-baseline
capture 1 baseline "$base1"
fail1="$(transition fail 1)"
settle 1-failure
capture 1 failure "$fail1"
reset1="$(transition reset 1)"
settle 1-reset
capture 1 reset "$reset1"
capture 2 baseline "$reset1"
fail2="$(transition fail 2)"
settle 2-failure
capture 2 failure "$fail2"
reset2="$(transition reset 2)"
settle 2-reset
capture 2 reset "$reset2"
stage=verify
stage_dir="$(mktemp -d /opt/issue45-evidence/cycle-verify.XXXXXX)"
chmod 0755 "$stage_dir"
for cycle in 1 2; do for phase in baseline failure reset; do
  install -m 0644 "/opt/issue45-evidence/cycle-$cycle-$phase.json" "$stage_dir/cycle-$cycle-$phase.json"
done; done
docker compose --env-file .env -p issue45-gateway -f compose.yaml -f compose.mcp.yaml \
  run --pull never --rm --no-deps -v "$stage_dir:/source/evidence:ro" harness \
  node /source/scripts/demo_signal_verify.mjs verify \
  /source/evidence/cycle-1-baseline.json /source/evidence/cycle-1-failure.json /source/evidence/cycle-1-reset.json \
  /source/evidence/cycle-2-baseline.json /source/evidence/cycle-2-failure.json /source/evidence/cycle-2-reset.json \
  > /opt/issue45-evidence/cycles-current-main-verified.json 2> /var/log/issue45-cycles-verify.stderr.log
rm -rf "$stage_dir"
printf 'verification='; cat /opt/issue45-evidence/cycles-current-main-verified.json
printf 'candidate='; git rev-parse HEAD
