#!/usr/bin/env bash
# The RC-2 inbox journey (#870) against the real stack, with no model provider:
#
#   COMPOSE_PROJECT_NAME=<unique> web/incident-console/e2e/run-inbox-real.sh
#
# Starts db, api and web (compose.yaml + compose.e2e.yaml, no host ports) with the demo grants,
# then, through the real runtime and API: an incident opened last night at 23:40 (Bogota) that
# waits for a mitigation decision, one opened at 22:05 that the operator approved and verified
# over HTTP, and two change events of last night recorded by the deploy-executor principal.
# Then e2e/inbox-real.spec.ts runs in incident-console-e2e; its screenshots stay in
# web/incident-console/e2e/artifacts/inbox/, which git ignores. Remove the project afterwards with
#   docker compose -f compose.yaml -f compose.e2e.yaml --project-name <unique> --profile e2e \
#     down -v --remove-orphans
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck source=../../../scripts/run_real_journeys.sh
source "$ROOT/scripts/run_real_journeys.sh"

# Yesterday's date in Bogota, the browser's time zone in playwright.config.ts: always last night.
yesterday="$(TZ=America/Bogota date -d yesterday +%F)"
night() { echo "${yesterday}T$1:00-05:00"; }

start_seeded_stack
"${SEED[@]}" -e SEED_STAMP="ip$STAMP" -e SEED_AT="$(night 23:40)" seed \
  python scripts/seed_verification_close_demo.py
"${SEED[@]}" -e SEED_STAMP="ir$STAMP" -e SEED_AT="$(night 22:05)" seed \
  python scripts/seed_verification_close_demo.py
resolve_incident "ir$STAMP"
"${SEED[@]}" -e DEPLOY="$(night 21:12)" -e CI="$(night 22:40)" -e STAMP="$STAMP" seed python - <<'PY'
import json, os, urllib.request

for kind, status, version, at in (("deploy", "succeeded", "checkout:1.5.0", os.environ["DEPLOY"]),
                                  ("ci", "failed", None, os.environ["CI"])):
    body = {"source": "github-actions", "external_id": f"inbox-{os.environ['STAMP']}-{kind}",
            "service": "checkout", "kind": kind, "status": status, "version": version,
            "occurred_at": at}
    sent = urllib.request.Request("http://api:8000/v1/changes", json.dumps(body).encode(), method="POST",
                                  headers={"Authorization": "Bearer " + os.environ["DEPLOY_EXECUTOR_CHANGES_API_KEY"],
                                           "Content-Type": "application/json"})
    with urllib.request.urlopen(sent, timeout=30) as reply:
        print(f"change {kind}: HTTP {reply.status}")
PY

rc=0 owner="$(id -u):$(id -g)"
"${COMPOSE[@]}" --profile e2e run --rm --build --no-deps -e INBOX_REAL=1 -e INBOX_STAMP="$STAMP" \
  incident-console-e2e sh -c \
  "npx playwright test e2e/inbox-real.spec.ts; s=\$?; chown -R $owner e2e/artifacts; exit \$s" || rc=$?
exit "$rc"
