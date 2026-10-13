#!/bin/sh
# Host uses Git, Docker and safe configuration; tooling stays containerized.
set -eu
ISSUE567_OUTPUT=${1:?Provide an absolute persistent output directory outside the checkout}
case "$ISSUE567_OUTPUT" in /*) ;; *) echo 'Output path must be absolute' >&2; exit 2 ;; esac
cd "$(git rev-parse --show-toplevel)"
checkout=$(pwd -P)
mkdir -p "$ISSUE567_OUTPUT"
ISSUE567_OUTPUT=$(cd "$ISSUE567_OUTPUT" && pwd -P)
case "$ISSUE567_OUTPUT/" in "$checkout/"*) echo 'Output must be outside the checkout' >&2; exit 2 ;; esac
test -z "$(ls -A "$ISSUE567_OUTPUT")" || { echo 'Use a new empty output directory' >&2; exit 2; }
test -z "$(git status --porcelain)" || { echo 'A clean candidate is required' >&2; exit 2; }
ISSUE567_TESTED_SHA=$(git rev-parse HEAD)
ISSUE567_BASE_SHA=763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9
git merge-base --is-ancestor "$ISSUE567_BASE_SHA" "$ISSUE567_TESTED_SHA"
export ISSUE567_OUTPUT ISSUE567_TESTED_SHA ISSUE567_BASE_SHA
project=${ISSUE567_PROJECT:-e567-ca-01a1331e}
attempt=$(mktemp "$ISSUE567_OUTPUT/attempt.XXXXXXXX")
container="$project-verify-$(git rev-parse --short=12 HEAD)-${attempt##*/}"
printf 'Tested SHA: %s\nBase SHA: %s\nSource clean: yes\nContainer: %s\n' \
  "$ISSUE567_TESTED_SHA" "$ISSUE567_BASE_SHA" "$container" > "$ISSUE567_OUTPUT/identity.txt"
git ls-tree -r HEAD -- src scripts tests docker docs/evidence/issue-567 \
  docs/design/issue-567-controlled-effects.md uv.lock package-lock.json > "$ISSUE567_OUTPUT/source-tree.txt"
set -- --env-file .env.example -f compose.yaml -f docs/evidence/issue-567/compose.yaml -p "$project"
docker compose "$@" --profile checks run --build -d --name "$container" \
  --user "$(id -u):$(id -g)" -e ISSUE567_OUTPUT=/proof -e ISSUE567_TESTED_SHA -e ISSUE567_BASE_SHA \
  -v "$ISSUE567_OUTPUT:/proof" python-checks sh -c '
    python scripts/assert_test_database_isolated.py &&
    pytest -q -s -p no:cacheprovider tests/test_external_effects_e2e.py &&
    python scripts/inspect_issue567_evidence.py /proof &&
    shellcheck docker/harness-entrypoint.sh scripts/worktree-compose scripts/reproduce_issue567_evidence.sh &&
    ruff check --no-cache . && ruff format --check --no-cache . && uv lock --check --no-cache &&
    lint-imports --no-cache &&
    mypy --cache-dir=/tmp/mypy src/sre_agent/incident/commands.py src/sre_agent/incident/persistence.py src/sre_agent/incident/runtime.py src/sre_agent/governance/dto.py src/sre_agent/investigator &&
    python scripts/validate_run_api.py &&
    pytest -q -p no:cacheprovider tests/test_incident*.py tests/test_investigator*.py tests/test_mcp*.py tests/test_import_boundaries.py tests/test_run_api_contract.py &&
    alembic check'
status=$(docker wait "$container")
docker logs "$container" > "$ISSUE567_OUTPUT/verification.log" 2>&1
printf 'Exit code: %s\n' "$status" >> "$ISSUE567_OUTPUT/identity.txt"
test "$status" = 0 || exit 1
docker compose "$@" --profile e2e run --build --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$ISSUE567_OUTPUT:/proof" -v "$PWD/scripts/capture_issue567_evidence.cjs:/e2e/capture-issue567.cjs:ro" \
  e2e node /e2e/capture-issue567.cjs /proof
test "$(git rev-parse HEAD)" = "$ISSUE567_TESTED_SHA"
test -z "$(git status --porcelain)"
