#!/usr/bin/env bash
# Portable, guarded real HTTP/PostgreSQL probe; run from private evidence checkout.
# Example: SOURCE_CHECKOUT=/path/to/exact/candidate OUTPUT_DIR=/safe/evidence/captures/json ./capture-slice.sh 409
set -euo pipefail
[[ $# -eq 1 ]] || { echo 'usage: capture-slice.sh SLICE_ID' >&2; exit 64; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source_root=${SOURCE_CHECKOUT:-$(git rev-parse --show-toplevel)}
source_root=$(cd -- "$source_root" && pwd -P)
out=${OUTPUT_DIR:?set OUTPUT_DIR outside the source checkout}
out=$(mkdir -p "$out" && cd "$out" && pwd -P)
case "$1" in
  387) expected=402ff6e580fa15e765bedc89ae5a6f889202e640 ;;
  388) expected=c0d8076908dbe425f8dbb7b4ff7d717a39ae2117 ;;
  397) expected=7327ca0ef8a4d810afe2376aec2ce5bd0959677e ;;
  403) expected=025476049fa094c852c48565f45d1e32f472bb3d ;;
  402) expected=6eb618906ff846f202ab6d43fca4fa7ae7523fd8 ;;
  404) expected=4b82922bef24bd455c41283b98409d1af5886830 ;;
  405) expected=3b525e0a305e8b44bdcd54495284950393a7b415 ;;
  331-validation-child) expected=94d14d9e37c5b456b441201b4d98a13bacc056d1 ;;
  406) expected=2e9b24004043d830b911c15cea6fb10d1da7a9cc ;;
  407) expected=c56f32eeed1e07d230f4de402c263075c5191809 ;;
  409) expected=e5ec78a0b0e60363af1ac674c2ce8d3a6627d094 ;;
  *) echo 'unsupported slice; no command run' >&2; exit 64 ;;
esac
actual=$(git -C "$source_root" rev-parse HEAD)
[[ "$actual" == "$expected" ]] || { echo "refusing source SHA $actual; expected $expected" >&2; exit 78; }
[[ "$out/" != "$source_root/"* ]] || { echo 'refusing output directory inside source checkout' >&2; exit 78; }
for f in .env .env.worktree; do
  [[ -f "$source_root/$f" ]] || { echo "missing safe clone-local $f" >&2; exit 78; }
  mode=$(stat -c '%a' "$source_root/$f")
  [[ "$mode" == 600 ]] || { echo "refusing: $f must be mode 0600" >&2; exit 78; }
done
probe="$script_dir/test_r9_capture.py"
[[ -f "$probe" ]] || { echo 'missing co-located, reviewed R9 probe source' >&2; exit 78; }
project=${CAPTURE_PROJECT:?set a unique disposable Compose project name}
# The DB-isolation assertion is the first command inside the checks container.
docker compose --project-directory "$source_root" \
  --env-file "$source_root/.env" --env-file "$source_root/.env.worktree" -p "$project" \
  --profile checks run --build --rm --user "$(id -u):$(id -g)" \
  -v "$probe:/app/tests/test_r9_capture.py:ro" -v "$out:/r9out" \
  -e "R9_SLICE=$1" -e "R9_HEAD=$expected" python-checks \
  sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_r9_capture.py'
