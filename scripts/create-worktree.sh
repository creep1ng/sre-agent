#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

if [ -x "${PWD}/.venv/bin/python" ]; then
  exec "${PWD}/.venv/bin/python" "${SCRIPT_DIR}/create-worktree.py" "$@"
fi

exec python3 "${SCRIPT_DIR}/create-worktree.py" "$@"
