# Governed Grafana MCP demo runbook

This runbook starts the local gateway only after this checkout's pinned demo
has created its internal boundary and caller-token file. It describes how to
collect evidence; it does not claim that a live walkthrough ran for this change.

## Quick path

1. Use an isolated Docker daemon with no existing `otel-demo`, `grafana-mcp`,
   or `sre-mcp-boundary` resources. The demo uses global container and network
   names; never reuse or remove another contributor's stack.
2. Prepare this checkout's local `.env` and worktree ports, then start
   `scripts/demo_env.py up`. It creates `.demo-state/grafana-mcp.env` and the
   Docker network `sre-mcp-boundary`.
3. Start this checkout with `compose.yaml` plus `compose.mcp.yaml`. The
   `mcp-seed` service waits for the normal seed, and `api` waits for
   `mcp-seed` to complete successfully.
4. Capture only sanitized status codes, governed IDs, public error codes, and
   metadata-only audit fields. Never attach tokens, authorization headers,
   raw upstream logs, or query results.

The upstream `demo/digests.lock` must pin Grafana MCP to
`grafana/mcp-grafana:1.3.0@sha256:5114852743e450fe5186b6c1712419843eb4bd295e47e64c452c3aa0fab3c42e`.
The overlay deliberately does not redefine or weaken that upstream image pin.

## Prerequisites

- Docker and Docker Compose 2.24 or newer (the upstream overlay uses `!reset`).
- A working local `.env` for this repository with four distinct, non-placeholder
  `sre_` API keys, non-placeholder model/provider identifiers, and a random
  `AUDIT_HMAC_KEY`. Keep `OPENROUTER_API_KEY` empty for discovery-only checks.
  `scripts/bootstrap-worktree.py` copies `.env.example` when needed and creates
  `.env.worktree` with collision-checked local ports. Neither file is committed.
- At least 4 CPUs, 4 GB free memory, 15 GB free disk, and free demo host ports
  8090, 10000, and 9090. The helper clones the pinned OpenTelemetry Demo into
  ignored `otel-demo/`; its manifest and digest lock must match.
- Sufficient Docker network address space. If Compose says predefined address
  pools are fully subnetted, stop here and use an isolated daemon with free
  pools. Do not prune shared networks or attach to an unrelated project.
- Securely supplied `DEMO_HUMAN_API_KEY` and
  `RESTRICTED_HARNESS_API_KEY` shell variables for probes. Do not put either
  value in this document or in command history.

## Start the isolated stack

```sh
python scripts/bootstrap-worktree.py
# Edit the ignored .env and replace every placeholder before starting Compose.
python scripts/demo_env.py up
python scripts/demo_env.py verify
DEMO_STATE_DIR="$PWD/.demo-state"
test -s "$DEMO_STATE_DIR/grafana-mcp.env"
docker network inspect sre-mcp-boundary >/dev/null

DEMO_STATE_DIR="$DEMO_STATE_DIR" docker compose \
  --env-file .env --env-file .env.worktree \
  -f compose.yaml -f compose.mcp.yaml \
  up -d --build mcp-seed api

API_PORT="$(sed -n 's/^API_PORT=//p' .env.worktree)"
API_BASE_URL="http://127.0.0.1:$API_PORT"
curl --fail --silent "$API_BASE_URL/health/ready" >/dev/null
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
DEMO_STATE_DIR="$PWD/.demo-state" docker compose \
  --env-file .env --env-file .env.worktree \
  -f compose.yaml -f compose.mcp.yaml --profile checks \
  run --build --rm python-checks pytest -q \
  tests/test_mcp_contract.py tests/test_mcp_discovery.py \
  tests/test_mcp_owner.py tests/test_mcp_seed.py tests/test_mcp_overlay.py
```

For the live run, use synthetic payloads and select only public fields. The
following probes temporarily store response bodies in a private temporary
directory and remove them when the shell exits; retain only the selected,
sanitized fields:

The Compose `--env-file` options supply values to Compose and the seed service;
they do not define variables in the shell that runs `curl`. Supply the same
keys used by the seed before running these probes. If `.env.worktree` overrides
keys from `.env`, use the effective worktree values, not the older `.env`
values. Do not source either file or print the keys. Fail fast on missing shell
variables:

```sh
: "${API_BASE_URL:?Set API_BASE_URL using the worktree API_PORT}"
: "${DEMO_HUMAN_API_KEY:?Supply the seeded demo-human API key}"
: "${RESTRICTED_HARNESS_API_KEY:?Supply the seeded restricted-harness API key}"
```

If a request returns 401, resolve the credential mismatch before interpreting
the response as discovery or grant evidence.

```sh
MCP_CAPTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$MCP_CAPTURE_DIR"' EXIT

curl -sS -o "$MCP_CAPTURE_DIR/mcp-discovery.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${DEMO_HUMAN_API_KEY}" \
  "$API_BASE_URL/v1/mcp/discovery"
jq '{request_id, server: .server.server_id, tools: [.tools[].tool_id]}' \
  "$MCP_CAPTURE_DIR/mcp-discovery.json"

curl -sS -o "$MCP_CAPTURE_DIR/mcp-allowed.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${DEMO_HUMAN_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_uid":"webstore-metrics","expr":"up","query_type":"instant","end_time":"now"}' \
  "$API_BASE_URL/v1/mcp/tools/query_prometheus"
jq '{result_type, warning_count: (.warnings | length)}' \
  "$MCP_CAPTURE_DIR/mcp-allowed.json"

curl -sS -o "$MCP_CAPTURE_DIR/mcp-denied.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${RESTRICTED_HARNESS_API_KEY}" \
  -H 'Content-Type: application/json' -d '{}' \
  "$API_BASE_URL/v1/mcp/tools/query_prometheus"
jq '{error_code: .error.code}' "$MCP_CAPTURE_DIR/mcp-denied.json"

curl -sS -o "$MCP_CAPTURE_DIR/discovery-denied.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${RESTRICTED_HARNESS_API_KEY}" \
  "$API_BASE_URL/v1/mcp/discovery"
jq '{error_code: .error.code, request_id}' \
  "$MCP_CAPTURE_DIR/discovery-denied.json"
```

The seeded `demo-human` has both tool grants; `restricted-harness` has no
discovery grant and must get 403. On a **fresh disposable stack only**, create
two additional synthetic Principals through the administrative API. Supply
`ADMIN_HUMAN_API_KEY` securely in the current shell; never paste it in output.
The normal seed intentionally does **not** authorize even `admin-human` to
manage grants. For this disposable demonstration only, provision that one
administrative scope first; do not add it to the production seed or run this
against shared data:

```sh
DEMO_STATE_DIR="$PWD/.demo-state" docker compose \
  --env-file .env --env-file .env.worktree \
  -f compose.yaml -f compose.mcp.yaml exec -T db \
  sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
BEGIN;
INSERT INTO resources (resource_type, resource_id, status)
VALUES ('administrative_control', 'grants', 'active');
INSERT INTO grants (grant_id, principal_id, action, resource_type,
                    resource_id, effect, status, created_at)
VALUES ('grant-admin-human-admin-write-grants', 'admin-human', 'admin.write',
        'administrative_control', 'grants', 'allow', 'active', now());
COMMIT;
SQL
```

This recipe uses a fresh idempotency key per mutation and keeps newly issued
keys in a private temporary directory. Check each command succeeds before
continuing; it is not intended to rerun against the same database.

```sh
umask 077
MCP_ADMIN_DIR="$(mktemp -d)"
trap 'rm -rf "$MCP_CAPTURE_DIR" "$MCP_ADMIN_DIR"' EXIT
for id in issue29-partial issue29-empty; do
  curl --fail --silent --show-error -o /dev/null \
    -H "Authorization: Bearer ${ADMIN_HUMAN_API_KEY}" \
    -H "Idempotency-Key: $(openssl rand -hex 16)" \
    -H 'Content-Type: application/json' \
    -d "{\"principal_id\":\"$id\",\"kind\":\"human\",\"display_name\":\"Issue 29 synthetic\"}" \
    "$API_BASE_URL/v1/principals"
  curl --fail --silent --show-error \
    -H "Authorization: Bearer ${ADMIN_HUMAN_API_KEY}" \
    -H "Idempotency-Key: $(openssl rand -hex 16)" \
    -H 'Content-Type: application/json' -d '{}' \
    "$API_BASE_URL/v1/principals/$id/credentials" >"$MCP_ADMIN_DIR/$id.json"
  curl --fail --silent --show-error -o /dev/null \
    -H "Authorization: Bearer ${ADMIN_HUMAN_API_KEY}" \
    -H "Idempotency-Key: $(openssl rand -hex 16)" \
    -H 'Content-Type: application/json' \
    -d "{\"grant_id\":\"grant-$id-discovery\",\"principal_id\":\"$id\",\"action\":\"mcp.discovery\",\"resource\":{\"resource_type\":\"mcp_server\",\"resource_id\":\"grafana-mcp\"},\"effect\":\"allow\"}" \
    "$API_BASE_URL/v1/grants"
done
curl --fail --silent --show-error -o /dev/null \
  -H "Authorization: Bearer ${ADMIN_HUMAN_API_KEY}" \
  -H "Idempotency-Key: $(openssl rand -hex 16)" \
  -H 'Content-Type: application/json' \
  -d '{"grant_id":"grant-issue29-partial-prometheus","principal_id":"issue29-partial","action":"mcp.invoke","resource":{"resource_type":"mcp_tool","resource_id":"query_prometheus"},"effect":"allow"}' \
  "$API_BASE_URL/v1/grants"
PARTIAL_API_KEY="$(jq -r .key "$MCP_ADMIN_DIR/issue29-partial.json")"
EMPTY_API_KEY="$(jq -r .key "$MCP_ADMIN_DIR/issue29-empty.json")"

for scenario in partial empty; do
  if [ "$scenario" = partial ]; then key="$PARTIAL_API_KEY"; else key="$EMPTY_API_KEY"; fi
  curl -sS -o "$MCP_CAPTURE_DIR/$scenario.json" -w '%{http_code}\n' \
    -H "Authorization: Bearer $key" "$API_BASE_URL/v1/mcp/discovery"
  jq '{request_id, tools: [.tools[].tool_id]}' "$MCP_CAPTURE_DIR/$scenario.json"
done
```

Expect 200 with `[query_prometheus]` for `partial`, and 200 with `[]` for
`empty`. Neither response may contain the hidden tool's name or description.
Do not revoke seed-owned demo grants: rerunning `mcp-seed` rejects that drift.
The controlled PostgreSQL test creates the same grant shapes without changing
the persistent demo rows.

For CA4, omit the bearer token and expect 401; send an unexpected query
parameter with a valid discovery token and expect 422
`contract_validation_failed`. Record only status, public error code and
`request_id`:

```sh
curl -sS -o "$MCP_CAPTURE_DIR/unauthenticated.json" -w '%{http_code}\n' \
  "$API_BASE_URL/v1/mcp/discovery"
jq '{error_code: .error.code, request_id}' "$MCP_CAPTURE_DIR/unauthenticated.json"
curl -sS -o "$MCP_CAPTURE_DIR/invalid-query.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer ${DEMO_HUMAN_API_KEY}" \
  "$API_BASE_URL/v1/mcp/discovery?unexpected=1"
jq '{error_code: .error.code, request_id}' "$MCP_CAPTURE_DIR/invalid-query.json"
```

For CA5, match each public `request_id` to PostgreSQL audit metadata, not raw
payloads:

```sh
DEMO_STATE_DIR="$PWD/.demo-state" docker compose \
  --env-file .env --env-file .env.worktree \
  -f compose.yaml -f compose.mcp.yaml exec -T db \
  sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
SELECT correlation->>'request_id' AS request_id, response_status,
       action, stage, outcome, policy_decision->>'decision' AS decision,
       resource->>'resource_type' AS resource_type,
       identity ? 'principal_ref' AS has_principal_ref,
       content_state,
       COALESCE(jsonb_typeof(redacted_content), 'null') = 'null' AS no_content
FROM audit_events
WHERE operation = 'mcp.discovery'
ORDER BY occurred_at DESC LIMIT 20;
SQL
```

Authentication failures return before the MCP audit sink and have no
`mcp.discovery` audit row. For authenticated success, empty and denial, require the matching
request ID, a HMAC Principal reference, the expected decision/status, and
`content_state='absent'` with no redacted content. Publish only these selected
fields. This query does not prove the upstream call count; obtain a separate
real Grafana MCP/boundary counter for the same request window before claiming
live CA5.

Record the observed HTTP status and public error code for denied, invalid,
timeout, and upstream-failure scenarios. CA3/CA5 also require an instrumented
upstream or boundary counter proving zero upstream calls for the denied request
and exactly one `tools/call` for the allowed request. A status code alone is not
that proof. Capture only method/path/count and metadata-only audit fields; do
not use raw container logs as evidence.

## Stop and status

```sh
DEMO_STATE_DIR="$DEMO_STATE_DIR" docker compose \
  --env-file .env --env-file .env.worktree \
  -f compose.yaml -f compose.mcp.yaml down
python scripts/demo_env.py down
```

**CA5 evidence boundary:** This runbook is an operator procedure, not evidence
that a live run occurred for any particular commit. A live CA5 pass requires a
real Grafana MCP `tools/call` counter and metadata-only PostgreSQL audit capture
showing zero upstream calls for denied requests and exactly one for an allowed
request. An HTTP 200 response or deterministic test results alone do not prove
CA5. Record the exact tested commit with the sanitized counter and audit
evidence; evidence from an earlier candidate does not automatically prove a
later one.
