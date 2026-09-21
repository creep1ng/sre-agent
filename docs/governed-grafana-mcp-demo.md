# Governed Grafana MCP demo runbook

This runbook starts the local gateway only after the pinned Grafana MCP demo has
created its internal boundary and generated its caller-token file. It describes
how to collect evidence; it does not claim that the live walkthrough ran in this
checkout.

## Quick path

1. Use a pristine local checkout of the #291/#294 demo integration, including
   its `scripts/demo_env.py` and `compose.demo.yaml`. The locally available
   reference is `origin/feat/ht-demo-mcp@b4434ca0bc28ed52d49e52b5560758ea71ea38b1`.
2. Start that demo and let it create `.demo-state/grafana-mcp.env` and the
   Docker network `sre-mcp-boundary`.
3. Start this repository with `compose.yaml` plus `compose.mcp.yaml`. The
   `mcp-seed` service waits for the normal seed, and `api` waits for
   `mcp-seed` to complete successfully.
4. Capture only sanitized status codes, governed IDs, public error codes, and
   metadata-only audit fields. Never attach tokens, authorization headers,
   raw upstream logs, or query results.

## Prerequisites

- Docker and Docker Compose 2.24 or newer (the upstream overlay uses `!reset`).
- A working local `.env` for this repository; pass it with `--env-file` rather
  than sourcing or printing it.
- The pristine upstream demo checkout in `UPSTREAM_ROOT`. Its helper must be
  able to create `"$UPSTREAM_ROOT/.demo-state/grafana-mcp.env"` and the
  internal `sre-mcp-boundary` network.
- Securely supplied `DEMO_HUMAN_API_KEY` and
  `RESTRICTED_HARNESS_API_KEY` shell variables for probes. Do not put either
  value in this document or in command history.

## Start the isolated stack

```sh
export UPSTREAM_ROOT=/absolute/path/to/ht-demo-mcp
export DEMO_STATE_DIR="$UPSTREAM_ROOT/.demo-state"

python "$UPSTREAM_ROOT/scripts/demo_env.py" up
test -s "$DEMO_STATE_DIR/grafana-mcp.env"
docker network inspect sre-mcp-boundary >/dev/null

DEMO_STATE_DIR="$DEMO_STATE_DIR" docker compose \
  --env-file .env \
  -f compose.yaml -f compose.mcp.yaml \
  up -d --build mcp-seed api
```

The overlay fixes the upstream URL at `http://grafana-mcp:8000/mcp` and reads
the generated token file through `env_file`. Do not start `api` with only
`compose.yaml`: that bypasses the governed MCP bootstrap. Compose dependency
ordering is part of the check, not a manual timing assumption.

## Sanitized CA1–CA5 capture

> This is an operator runbook, not a PR `Reproduction commands` block. The
> host-side `python` and `curl` steps below are for an authorized local live
> demonstration only. PR evidence must follow `docs/pr-evidence.md` and use
> containerized `docker compose` or `docker run` commands.

Run the repository's deterministic checks first and retain their exit status:

```sh
docker compose --env-file .env -f compose.yaml -f compose.mcp.yaml \
  run --rm python-checks pytest -q \
  tests/test_mcp_contract.py tests/test_mcp_owner.py \
  tests/test_mcp_gateway.py tests/test_mcp_evidence.py
```

For the live run, use synthetic payloads and select only public fields. The
following probes temporarily store response bodies in a private temporary
directory and remove them when the shell exits; retain only the selected,
sanitized fields:

```sh
MCP_CAPTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$MCP_CAPTURE_DIR"' EXIT

curl -sS -o "$MCP_CAPTURE_DIR/mcp-discovery.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${DEMO_HUMAN_API_KEY}" \
  http://127.0.0.1:8000/v1/mcp/discovery
jq '{server: .server.server_id, tools: [.tools[].tool_id]}' \
  "$MCP_CAPTURE_DIR/mcp-discovery.json"

curl -sS -o "$MCP_CAPTURE_DIR/mcp-allowed.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${DEMO_HUMAN_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_uid":"webstore-metrics","expr":"up","query_type":"instant","end_time":"now"}' \
  http://127.0.0.1:8000/v1/mcp/tools/query_prometheus
jq '{result_type, warning_count: (.warnings | length)}' \
  "$MCP_CAPTURE_DIR/mcp-allowed.json"

curl -sS -o "$MCP_CAPTURE_DIR/mcp-denied.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${RESTRICTED_HARNESS_API_KEY}" \
  -H 'Content-Type: application/json' -d '{}' \
  http://127.0.0.1:8000/v1/mcp/tools/query_prometheus
jq '{error_code: .error.code}' "$MCP_CAPTURE_DIR/mcp-denied.json"
```

Record the observed HTTP status and public error code for denied, invalid,
timeout, and upstream-failure scenarios. CA3/CA5 also require an instrumented
upstream or boundary counter proving zero upstream calls for the denied request
and exactly one `tools/call` for the allowed request. A status code alone is not
that proof. Capture only method/path/count and metadata-only audit fields; do
not use raw container logs as evidence.

## Stop and status

```sh
DEMO_STATE_DIR="$DEMO_STATE_DIR" docker compose \
  --env-file .env -f compose.yaml -f compose.mcp.yaml down
python "$UPSTREAM_ROOT/scripts/demo_env.py" down
```

**Status in this checkout: not run here.** Docker access failed with permission
denied on `/var/run/docker.sock`, so the isolated live stack and CA5 evidence
remain pending. Deterministic local tests do not close that gap.
