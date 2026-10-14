# Authorized current-main AWS verification

Tested SHA `ca15e7ad27bf4577506631e1a4b117976b61541c`; see
[report17](17-resume-aws.txt) and [actual Chromium capture](17-resume-aws.png).
No runtime/E2E implementation changed. Observed API tooling reused the pinned
runtime image from220cd462: scripts/src/Compose/Dockerfile/uv.lock trees were
compared against ca15e7ad and unchanged. Compose services built from ca15e7ad.

Use a standalone clean checkout and the [operator guide](../../setup-sre.md).
Host/initial secret prerequisites are not recurring SRE grants/setup steps.
This run uses independent authorized `otel-demo`/`us-east-1` owner `up`/MCP
preparation and native SSM `connect-mcp`, private state0600 outside checkout.
Owner deadline is2026-10-14T13:44:28UTC; no further extension is implied.
Initial configuration from public `.env.example`, paid0, project
`sre-618-resume`, ports18678/79/80, internal boundary/runtime/consumer
0/16/32 all/28 under10.253.163/24, verified unused. Owner connection used
network `sre-aws-mcp-resume`, local18096; no worktree file copying/manual SQL.

For optional automated fail/reset, independently authorize and prepare the
0700 owner holder with credentials/config/settings0600 as described in
[container reproduction](13-container-reproduction.md). Only its owner child
mounts it; the API runner receives only its path. The observed holders were
removed after each operation/journey. New runs require fresh authorized provision.

```sh
docker build --target runtime -f docker/api.Dockerfile -t sre618-review-api:ca15e7ad .
docker build -f docker/otel-owner.Dockerfile -t sre618-owner:2.36.49 .
docker run --rm --network host --user "$(id -u):$(id -g)" --group-add 967 \
  -e HOME=/tmp -e "SRE_OWNER_PRIVATE_DIR=$OTEL_OWNER_PRIVATE_DIR" --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=$PWD,readonly" \
  --mount type=bind,source=/tmp/sre618-resume-private,target=/tmp/sre618-resume-private \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
  --mount type=bind,source=/usr/bin/docker,target=/usr/bin/docker,readonly \
  --mount type=bind,source=/usr/lib/docker/cli-plugins/docker-compose,target=/usr/lib/docker/cli-plugins/docker-compose,readonly \
  --mount type=bind,source=/usr/lib/docker/cli-plugins/docker-buildx,target=/usr/lib/docker/cli-plugins/docker-buildx,readonly \
  -w "$PWD" sre618-review-api:ca15e7ad "$PWD/scripts/verify_setup_aws_journey.py" \
  /tmp/sre618-resume-private/sre.env
```

Actual exit0, nonempty healthy baseline, real failed checkout after owner fail,
recovery after owner reset, allowed200/201/restricted403, stable domain/key digest,
audit retained. No paid model inference. API runner live mounts did not include
the owner credential holder. Actual harness secret absence/direct transport
isolation passed; owner ingress0/enabled targeted termination verified.

The same-demo reconnect check uses the same API container mounts, no owner
credential mount/environment, with `scripts/setup_sre.py --env-file` as the
container command: owner disconnect => actual canonical exit1, owner reconnect
=> governed up/traffic/log queries200 before any API restart, canonical exit0.
Token and SRE data retained. It did not reproduce the prior session's502;
that is not a root-cause/fix claim. Operator reconnect is documented recovery,
never implicit SRE redeployment. Long-idle observation is separately recorded.

Independent reviewer prerequisites were prepared in another clean main clone,
with its own private initial configuration/new project/ports. Assistant did not
execute that reviewer's setup or journey. Actual human CA7 results remain pending;
real local OTel remains not executed and report16 remains explicitly controlled.
