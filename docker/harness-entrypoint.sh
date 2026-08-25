#!/bin/sh
set -eu

# The repository inputs stay read-only. The harness copies them and its image-locked
# dependencies into a fresh tmpfs so tools can create bounded temporary artifacts.
cp -R /source/schemas /workspace/schemas
cp -R /source/scripts /workspace/scripts
cp -R /opt/tooling/node_modules/. /workspace/node_modules/
ln -s /workspace/node_modules /workspace/schemas/tooling/node_modules
cd /workspace
exec "$@"
