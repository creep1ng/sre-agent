#!/usr/bin/env bash
# Portable, guarded contributor reproduction helper. Uses only disposable local configuration.
# Caller must be in the exact candidate checkout, after independent R9 dispatch.
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "usage: $0 SLICE_ID" >&2; exit 64; fi
repo=$(git rev-parse --show-toplevel)
head=$(git -C "$repo" rev-parse HEAD)
case "$1" in
  387) expected=402ff6e580fa15e765bedc89ae5a6f889202e640; tests='tests/test_migrations.py tests/test_demo_seeds.py tests/test_health.py tests/test_persistence_repositories.py' ;;
  388) expected=c0d8076908dbe425f8dbb7b4ff7d717a39ae2117; tests='tests/test_control_plane.py tests/test_control_acceptance.py tests/test_persistence_repositories.py' ;;
  397) expected=7327ca0ef8a4d810afe2376aec2ce5bd0959677e; tests='tests/test_skill_publication.py tests/test_control_acceptance.py tests/test_control_plane.py tests/test_migrations.py' ;;
  403) expected=025476049fa094c852c48565f45d1e32f472bb3d; tests='tests/test_skill_migration_compatibility.py tests/test_migrations.py tests/test_demo_seeds.py tests/test_health.py' ;;
  402) expected=6eb618906ff846f202ab6d43fca4fa7ae7523fd8; tests='tests/test_skill_activation.py tests/test_skill_publication.py tests/test_control_acceptance.py tests/test_control_plane.py' ;;
  404) expected=4b82922bef24bd455c41283b98409d1af5886830; tests='tests/test_audit.py tests/test_persistence_repositories.py tests/test_skill_migration_compatibility.py tests/test_migrations.py tests/test_health.py' ;;
  405) expected=3b525e0a305e8b44bdcd54495284950393a7b415; tests='tests/test_skill_resolution.py tests/test_governed_authorization.py' ;;
  331-validation-child) expected=94d14d9e37c5b456b441201b4d98a13bacc056d1; tests='tests/test_skill_resolution.py' ;;
  406) expected=2e9b24004043d830b911c15cea6fb10d1da7a9cc; tests='tests/test_skill_resolution.py tests/test_governed_authorization.py' ;;
  407) expected=c56f32eeed1e07d230f4de402c263075c5191809; tests='tests/test_skill_lifecycle_proof.py' ;;
  409) expected=e5ec78a0b0e60363af1ac674c2ce8d3a6627d094; tests='tests/test_skill_demo.py tests/test_skill_resolution.py' ;;
  *) echo "unsupported slice; no command run" >&2; exit 64 ;;
esac
if [[ "$head" != "$expected" ]]; then echo "refusing stale/incorrect candidate: found $head expected $expected" >&2; exit 78; fi
if [[ ! -f .env || ! -f .env.worktree ]]; then echo "refusing: provide ignored safe clone-local .env and .env.worktree; do not print/upload them" >&2; exit 78; fi
# Verify mode only; never read or print local secret configuration.
for f in .env .env.worktree; do mode=$(stat -c '%a' "$f"); if [[ "$mode" != 600 ]]; then echo "refusing: $f must be mode 0600 (mode was $mode)" >&2; exit 78; fi; done
# Path list is fixed above, then executed in the isolated checks container after DB guard.
docker compose --env-file .env --env-file .env.worktree --profile checks run --build --rm python-checks \
  sh -c "python scripts/assert_test_database_isolated.py && pytest -q $tests"
