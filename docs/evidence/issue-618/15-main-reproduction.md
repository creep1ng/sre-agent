# Integrated main reproduction

Tested SHA: `220cd4625f1e7c9f719aedab71d0232e6ee40e73`.
See [actual output](15-main-aws.txt) and [actual capture](15-main-aws.png).
This is automated real AWS verification, not independent human execution.

## Prerequisites

Use one clean standalone checkout of the main SHA above. Follow
[the setup guide](../../setup-sre.md): host Git/Python/local Docker, initial
owner-only `.env` from the current `.env.example`, four unique random API keys,
valid database/model assignments, paid disabled. Do not copy worktree files.

OTel is independently prepared via the integrated owner CLI using expressly
approved `otel-demo`/`us-east-1` credentials and expected account configuration.
Native `connect-mcp` remains an explicit independent prerequisite. This run
used private `/tmp/sre618-final-private` (0700, contract/token0600), internal
network `sre-aws-mcp-final-main`, free176/28 boundary,192/28 runtime and208/28
consumer under10.253.161/24, ports18648/18649/18650, project `sre-618-final-main`.
Adjust only initial private configuration if the host differs; select unused
CIDRs, never prune unrelated projects. No additional grants or database edits.

The optional real fail/reset E2E requires a temporary0700 owner holder with
credentials/config/settings0600 as [documented](13-container-reproduction.md).
Only its separate owner child mounts this holder; the API runner receives a path,
not credentials. The observed holder was deleted after reset, including on the
first aborted attempt; new runs require authorized fresh provision. No AWS or
MCP credential goes to the harness/checks. Local Docker control is explicit.

## Container commands

Run from the clean checkout, with local Unix Docker selected. API Dockerfile and
uv.lock pin runtime dependencies; the owner Dockerfile pins AWS CLI2.36.49.
`OTEL_OWNER_PRIVATE_DIR` is an explicit host path, never credential contents.

```sh
docker build --target runtime -f docker/api.Dockerfile -t sre618-main-api:220cd462 .
docker build -f docker/otel-owner.Dockerfile -t sre618-owner:2.36.49 .
docker run --rm --network host --user "$(id -u):$(id -g)" --group-add 967 \
  -e HOME=/tmp -e "SRE_OWNER_PRIVATE_DIR=$OTEL_OWNER_PRIVATE_DIR" --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=$PWD,readonly" \
  --mount type=bind,source=/tmp/sre618-final-private,target=/tmp/sre618-final-private \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
  --mount type=bind,source=/usr/bin/docker,target=/usr/bin/docker,readonly \
  --mount type=bind,source=/usr/lib/docker/cli-plugins/docker-compose,target=/usr/lib/docker/cli-plugins/docker-compose,readonly \
  --mount type=bind,source=/usr/lib/docker/cli-plugins/docker-buildx,target=/usr/lib/docker/cli-plugins/docker-buildx,readonly \
  -w "$PWD" sre618-main-api:220cd462 "$PWD/scripts/verify_setup_aws_journey.py" "$PWD/.env"
docker run --rm --network none --user "$(id -u):$(id -g)" --entrypoint python \
  --mount "type=bind,source=$PWD/scripts,target=/work/scripts,readonly" \
  --mount "type=bind,source=$PWD/.env.example,target=/work/.env.example,readonly" \
  sre618-main-api:220cd462 /work/scripts/verify_setup_preflight.py
```

The E2E invokes exactly the canonical setup on first/repeated start, then queries
actual governed metrics/logs and current workflow APIs. Expect exit0, nonempty
healthy baseline, failed checkout after owner fail, successful recovery after
owner reset, workflow200/201, restricted403 and retained domain/audit state.
The main report records observed values, initial input error, stop/recovery and
remaining local-real/human/hosted-CI gates; no successful paid inference is claimed.
Normal operators use `python scripts/setup_sre.py`, not this E2E as a prerequisite.

## Separate controlled local check

[Report16](16-main-local-controlled.txt) used the **same main SHA** and existing
`verify_setup_repeat.py`, with a prepared `tests/setup_mcp_fixture.py` container
aliased `grafana-mcp` on a new internal network. The synthetic private token is
provided only to that owned fixture and API tooling. This is test preparation,
never an operator prerequisite or real OTel/signals claim. Its private initial
config follows the setup guide, local mode, ports18658/59/60, project
`sre-618-main-local`, state `/tmp/sre618-main-local-private`, CIDRs0/16/32 under
10.253.162/24, and `SRE_618_FIXTURE_CONTAINER=sre-618-fixture-main-local`.
Use the same API `docker run` mounts above, omit the owner-holder environment,
replace the state mount with `/tmp/sre618-main-local-private`, and invoke
`$PWD/scripts/verify_setup_repeat.py /tmp/sre618-main-local-private/sre.env`.
Expected/actual exit0, retained domain/audit; occupied-port and fixture-outage
nonzero, bounded correction converges. The script stops only its explicit
fixture and scoped SRE; it never deletes volumes or resets real OTel.
