#!/bin/sh
set -eu

# The schema authority is mounted read-only. Dependencies come from the image and
# are copied into a fresh parent-level tmpfs that Node's module resolver can use.
cp -a /opt/tooling/node_modules/. /workspace/node_modules/
exec "$@"
