# Real containerized AWS/SRE reproduction

Tested source: `5e48ef4d0ec769615f2e332a7111c6607e1cd4ec`.
See [actual output](13-container-aws-journey.txt) and
[actual Chromium report capture](13-container-aws-journey.png).

## Explicit prerequisites and boundaries

- Linux amd64, Docker29.9.0/Compose5.6.0, reviewed checkout. Public Docker CLI
  `/usr/bin/docker`, plugins in `/usr/lib/docker/cli-plugins`, socket group967
  are this host's prerequisites; adjust safe host configuration if different.
- Separately authorized owned OTel Demo in `otel-demo`/`us-east-1`, its native
  SSM connection and private API-only contract already prepared as documented
  in the owner/setup guides. Native `connect-mcp` is an explicit independent
  prerequisite, **not** an operation performed inside this E2E container.
- Private API config `.demo-state/aws-container/sre.env`, mode0600, and existing
  `sre-setup` directory. This run used project `sre-618-aws-container`, ports
  18638/18639/18640, boundary/runtime/consumer subnets128/28,144/28,160/28 under
  `10.253.161.0/24`, verified nonoverlapping. Earlier project/data are retained.
- `OTEL_OWNER_PRIVATE_DIR` identifies an absolute host directory0700 outside
  the checkout. Its files `credentials`, `config`, `settings.env` are0600.
  `credentials` contains only the expressly authorized `[otel-demo]` profile;
  `config` selects its `us-east-1` region. `settings.env` declares the operator's
  independently configured expected account, `AWS_SHARED_CREDENTIALS_FILE` at
  `/run/owner/credentials`, `AWS_CONFIG_FILE` at `/run/owner/config`, metadata
  access disabled and pager disabled. Never print/source/attach these files.
- Only the separate owner child mounts this holder. The API orchestrator knows
  its path but never mounts/reads its contents. Live parent mount/environment
  inspection passed. Docker control is explicit, not total host isolation.
  No AWS/MCP secret goes to checks/harness; no paid LLM call is enabled.
- Credential provisioning requires explicit session/destination authorization.
  Delete this temporary holder after owner operations, even if verification
  fails. The observed holder and files were removed after reset/guard checks;
  their contents were not read during cleanup. A new run needs fresh provision.

## Container commands

The AWS CLI distribution is pinned to its official public amd64 image digest;
Python and dependencies are pinned by the existing Dockerfile/uv.lock. See
[AWS's official Docker versioning documentation](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-docker.html).
Only reviewed source should receive local Docker control. Set the caller's
Docker configuration to the local Unix socket, never an ambient remote context.

```sh
docker build -f docker/otel-owner.Dockerfile -t sre618-owner:2.36.49 .
docker compose --env-file .demo-state/aws-container/sre.env -p sre618-review -f compose.yaml build api
docker run --rm --network host --user "$(id -u):$(id -g)" --group-add 967 \
  -e HOME=/tmp -e "SRE_OWNER_PRIVATE_DIR=$OTEL_OWNER_PRIVATE_DIR" --entrypoint python \
  --mount "type=bind,source=$(pwd -P),target=$PWD,readonly" \
  --mount "type=bind,source=$PWD/.demo-state/aws-container/sre-setup,target=$PWD/.demo-state/aws-container/sre-setup" \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
  --mount type=bind,source=/usr/bin/docker,target=/usr/bin/docker,readonly \
  --mount type=bind,source=/usr/lib/docker/cli-plugins/docker-compose,target=/usr/lib/docker/cli-plugins/docker-compose,readonly \
  --mount type=bind,source=/usr/lib/docker/cli-plugins/docker-buildx,target=/usr/lib/docker/cli-plugins/docker-buildx,readonly \
  -w "$PWD" sre618-review-api:latest \
  "$PWD/scripts/verify_setup_aws_journey.py" "$PWD/.demo-state/aws-container/sre.env"
```

## Actual result and limitations

First terminal attempt: connection200 but zero traffic; exit1, not accepted.
Owned diagnostic found bootstrap finished and services running; a governed API
query subsequently found17 real trace service series. Same source rerun:
baseline108calls/0errors/6orders; failure68calls/16errors/0orders/proxy500x9;
recovery234calls/0errors/15orders/proxy200x14. Triage/run/state/events/audit and
restricted403; second setup retained domain state/credential digest/audit.
Owner `fail` and `reset` executed in separate owner containers. Actual exit0.
New owner container launch/prepare also succeeded; zero ingress rules and enabled
termination at03:28:03UTC were verified. No additional extension was performed.
This is feature-candidate evidence, not final-main or independent reviewer
execution. Old suite1908pass remains compatibility evidence for unchanged
production runtime; new-hook live evidence is this run. Current-head CI/review
must be evaluated separately. Sanitized: yes.
