# Governed Grafana MCP demo runbook

This runbook starts the local gateway behind a versioned, project-scoped counter
and describes how to collect evidence; it does not claim that a live walkthrough
ran for this change.

## Quick path

1. Use a unique Compose project name and an isolated Docker daemon. The counter
   overlay creates its own project-scoped boundary network and has no host-published
   MCP port; never reuse or remove another contributor's resources.
2. Prepare this checkout's local `.env` and worktree ports. For a query that
   requires a functioning Grafana backend, use the separately governed demo
   setup. For discovery and boundary diagnostics, a fresh caller-token file is
   enough; no full demo or paid call is required.
3. Start this checkout with `compose.yaml`, `compose.mcp.yaml`, and
   `compose.issue29-counter.yaml`. The `mcp-seed` service waits for the normal
   seed, and `api` waits for `mcp-seed` to complete successfully.
4. Capture only sanitized status codes, governed IDs, public error codes, and
   metadata-only audit fields. Never attach tokens, authorization headers,
   raw upstream logs, or query results.

The upstream `demo/digests.lock` pins Grafana MCP to
`grafana/mcp-grafana:1.3.0@sha256:5114852743e450fe5186b6c1712419843eb4bd295e47e64c452c3aa0fab3c42e`;
the counter overlay uses the exact same digest.

## Prerequisites

- Docker and Docker Compose 2.24.4 or newer (the demo overlay uses `!reset`
  and `!override`).
  The counter uses the API runtime image and its locked `httpx` dependency; no
  host relay install is needed.
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
# This overlay is for discovery/boundary diagnostics only; it does not start
# Grafana or promise a successful tools/call.
export ISSUE29_PROJECT="issue29-counter-$(date +%s)"
export DEMO_STATE_DIR="$PWD/.demo-state/$ISSUE29_PROJECT"
umask 077
mkdir -p "$DEMO_STATE_DIR"
python -c "import secrets,pathlib,os;pathlib.Path(os.environ['DEMO_STATE_DIR'],'grafana-mcp.env').write_text('MCP_GRAFANA_SERVER_TOKEN='+secrets.token_hex(24)+'\n',encoding='utf-8',newline='\n')"
test -s "$DEMO_STATE_DIR/grafana-mcp.env"
compose() { docker compose -p "$ISSUE29_PROJECT" \
  --env-file .env --env-file .env.worktree \
  -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml "$@"; }
# Keep this terminal/session open for the later compose() commands.
compose up -d --build mcp-seed api mcp-upstream grafana-mcp

API_PORT="$(sed -n 's/^API_PORT=//p' .env.worktree)"
API_BASE_URL="http://127.0.0.1:$API_PORT"
curl --fail --silent "$API_BASE_URL/health/ready" >/dev/null
```

The gateway keeps `http://grafana-mcp:8000/mcp`; the overlay's relay then
forwards to pinned service `mcp-upstream`. The generated token is private and
loaded through `env_file`. Do not start `api` with only `compose.yaml`: that
bypasses the governed MCP bootstrap. Compose dependency ordering is part of the
check, not a manual timing assumption.

For discovery-only checks, the token file created in the start procedure is
sufficient; the project-scoped overlay does not use the legacy global
`sre-mcp-boundary`.

The full OpenTelemetry demo is optional and outside this counter acceptance
path. If separately needed, run its existing setup only on a disposable,
isolated Docker daemon because it uses fixed container names; it is not a source
of live-query claims for the inert counter overlay:

```sh
python scripts/demo_env.py up
python scripts/demo_env.py verify
```

## Sanitized CA1–CA5 capture

> This is an operator runbook, not a PR `Reproduction commands` block. The
> host-side `python` and `curl` steps below are for an authorized local live
> demonstration only. PR evidence must follow `docs/pr-evidence.md` and use
> containerized `docker compose` or `docker run` commands.

Keep the exported project-scoped `DEMO_STATE_DIR` from setup for every later
`compose` command. Do not override it with `.demo-state`: the required token
file lives in `.demo-state/$ISSUE29_PROJECT/grafana-mcp.env`.

Run the repository's deterministic checks first and retain their exit status:

```sh
compose --profile checks \
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

The published MCP 1.0.0 result contract preserves a timestamp/value pair as
`result_type: "indeterminate"` when the upstream omits its type discriminator.
The value remains a string (including values such as `"NaN"` or `"Inf"`); the
gateway does not guess `scalar` versus `string` or convert it to a number. The
same schema continues to accept explicitly typed scalar/string pairs and
vector/matrix object results. The synthetic untyped-pair example is
`schemas/mcp/1.0.0/examples/query-prometheus-indeterminate-result.json`.

The seeded `demo-human` has both tool grants; `restricted-harness` has no
discovery grant and must get 403. On a **fresh disposable stack only**, create
two additional synthetic Principals through the administrative API. Supply
`ADMIN_HUMAN_API_KEY` securely in the current shell; never paste it in output.

Since the administrative grant seed landed, the normal seed already provisions
`administrative_control/grants` and both `admin.read` and `admin.write` on it
for `admin-human`. Confirm that before provisioning anything by hand; do **not**
insert those rows manually, because the resource and grant identifiers are
primary keys and a manual insert now fails with a duplicate-key error:

```sh
compose exec -T db \
  sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
SELECT count(*) AS seeded_administrative_grant_rows
  FROM grants
 WHERE principal_id = 'admin-human'
   AND resource_type = 'administrative_control'
   AND resource_id = 'grants'
   AND status = 'active';
SQL
```

Expect `2`. Anything lower means the administrative seed did not run, and the
grant calls below will return 403. Investigate the seed rather than writing
rows directly.

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

For CA5, match actual public `request_id` values to PostgreSQL metadata, not
raw payloads. Set these from the sanitized capture (do not substitute example or
historical IDs); the UTC window is the exact discovery capture window:

```sh
: "${DISCOVERY_REQUEST_IDS:?Set comma-separated request IDs observed in this run}"
: "${CAPTURE_START_UTC:?Set actual capture start time in UTC}"
: "${CAPTURE_END_UTC:?Set actual capture end time in UTC}"
compose exec -T \
  -e DISCOVERY_REQUEST_IDS="$DISCOVERY_REQUEST_IDS" \
  -e CAPTURE_START_UTC="$CAPTURE_START_UTC" \
  -e CAPTURE_END_UTC="$CAPTURE_END_UTC" db \
  sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -v ON_ERROR_STOP=1 -v request_ids="$DISCOVERY_REQUEST_IDS" \
    -v capture_start="$CAPTURE_START_UTC" -v capture_end="$CAPTURE_END_UTC"' <<'SQL'
SELECT correlation->>'request_id' AS request_id, response_status,
       action, stage, outcome, policy_decision->>'decision' AS decision,
       resource->>'resource_type' AS resource_type,
       identity ? 'principal_ref' AS has_principal_ref,
       content_state,
       COALESCE(jsonb_typeof(redacted_content), 'null') = 'null' AS no_content
FROM audit_events
WHERE operation = 'mcp.discovery'
  AND correlation->>'request_id' = ANY(string_to_array(:'request_ids', ','))
  AND occurred_at >= :'capture_start'::timestamptz
  AND occurred_at < :'capture_end'::timestamptz
ORDER BY occurred_at;
SQL
```

Authentication failures return before the MCP audit sink and have no
`mcp.discovery` audit row. For authenticated success, empty, and denial, require
the matching request ID, a HMAC Principal reference, the expected decision/status,
and `content_state='absent'` with no redacted content. Publish only these selected
fields. CA5 is the metadata-only audit/discovery evidence; a successful tool
execution is not a CA5 prerequisite.

Record the observed HTTP status and public error code for denied, invalid,
timeout, and upstream-failure scenarios. Use the versioned counter below to show
zero boundary requests for a denied request and distinguish one attempted
`tools/call` from successful tool execution. A status code alone proves neither.
Capture only aggregate counts and metadata-only audit fields; do not use raw
container logs as evidence.

## Count the MCP boundary (versioned instrument)

`compose.issue29-counter.yaml` replaces the external `sre-mcp-boundary` in
`compose.mcp.yaml` with `<Compose project>-mcp-boundary`; no `container_name`, MCP
host port, external relay file, or shared boundary network is used. The relay
script is mounted read-only into the API runtime image. `httpx` comes from the
existing locked application dependencies (`uv.lock`). The real Grafana MCP image
is pinned to `demo/digests.lock`; the relay targets `mcp-upstream:8000`, so its
HTTP client rewrites `Host` to the allowed upstream host. The gateway still calls
`grafana-mcp:8000` and requires no endpoint change.

The in-network `GET /__count` snapshot has a reset epoch, reset/capture UTC
timestamps, `total_http_requests`, `upstream_attempts`, `upstream_failures`, and
the `mcp_methods` map. Counts are aggregates only: bodies, headers, results,
paths, and request IDs are neither retained nor logged. Each non-control HTTP request increments the request and attempt counts once,
even if the relay cannot forward it and returns safe
`502 {"error":"upstream_unavailable"}`. `upstream_failures` means relay-level
forwarding exceptions only; an HTTP error status returned by MCP is preserved
and does not by itself increment that field. JSON-RPC methods are
counted per message; a batch may contain several. Only `initialize`,
`notifications/initialized`, and `tools/call` have named buckets; all other method
names go to `other` so arbitrary content cannot leak into the snapshot. A request
with both `initialize` and `notifications/initialized` is a handshake, distinct
from a subsequent `tools/call`; counters report observed messages only. GET
`/__count` and POST `/__count/reset` are not counted. This is boundary metadata,
not tool-success evidence or a PostgreSQL audit record.

This isolated project starts the pinned MCP service with `GRAFANA_URL` set to
loopback port 1; it does not provision or connect to a Grafana datasource
backend. Keep the generated token private. No
external MCP service or paid call is needed for discovery-only zero-crossing. An
invocation diagnostic is outside CA1–CA5 and is not required to succeed. If it
returns `502 upstream_invalid`, report the actual error and the counter evidence;
that proves only that the tool request crossed the gateway/upstream boundary, not
that the tool executed successfully.

Reset immediately before the capture window, then take start/end snapshots from
the relay container. Keep the timestamps, tested SHA, environment, and sanitized
counter snapshots together with the request IDs and bounded PostgreSQL audit
query. Only publish the selected aggregate fields; never publish the token,
authorization headers, raw responses, or raw logs.

```sh
counter() { compose exec -T grafana-mcp python -c \
  'import httpx,json; print(json.dumps(httpx.get("http://127.0.0.1:8000/__count",timeout=5).json(),sort_keys=True))'; }
reset_counter() { compose exec -T grafana-mcp python -c \
  'import httpx; r=httpx.post("http://127.0.0.1:8000/__count/reset",timeout=5); r.raise_for_status()'; }
reset_counter
counter  # capture window start (zero required before discovery)
# Run the documented API probes now, then capture the end:
counter
```

For discovery, the start and end `total_http_requests`/`upstream_attempts` must both
remain zero. Keep invocation diagnostics in a separate capture window. A cold
first tool request may include the two observed handshake HTTP messages
(`initialize` and `notifications/initialized`) plus `tools/call` (three HTTP
requests); after the client session is already initialized, a reset followed by
a warm invocation may show one HTTP request with only `tools/call`. Do not assume
either: record the actual snapshot and session state. A 502 `upstream_invalid` is
not a successful invocation and is outside CA1–CA5; if the counter increments,
it proves boundary crossing only.

The acceptance replay is versioned at `scripts/issue29_capture.py`. It sends
real HTTP through this isolated gateway, provisions uniquely named synthetic
partial/empty principals, checks full/partial/empty visibility and denial/error
statuses, captures metadata-only PostgreSQL rows with the observed request IDs and
UTC window, and brackets discovery/denial plus cold/warm invocation diagnostics
with the counter. The configured backend is deliberately unreachable at loopback
port 1: a `502 upstream_invalid` is expected diagnostic evidence, never a
successful tool execution. It makes no provider or paid call. Synthetic principal,
credential, and grant rows are left intact for the audit trail; do not delete them.
The artifact excludes API keys and response bodies and is written only to the
ignored capture directory.

A counter reset does not clear the gateway's in-memory MCP session. Before each
full replay, recreate **this isolated project's API** so the first diagnostic
is genuinely cold. This preserves database rows and volumes. A reused gateway can
correctly issue only `tools/call` on its first diagnostic; the cold-handshake
assertion then fails and must not be reported as passed. Wait for API health after
recreation; no invocation probes may precede the replay. `compose restart api`
is sufficient only for another cold replay of the same verified image. It does
not rebuild source or apply configuration changes after changing commits.

Run after initial setup. Rebuild the API and checks images from the selected
checkout, then recreate the isolated stack and wait for API health. The `up`
command also rebuilds the migration/seed dependencies; existing database volumes
are retained. Do not use `--no-build` or merely restart an old API when changing
commits. Verify that the running API uses the newly built immutable image ID
before assigning `TESTED_SHA`, then run the
versioned script in the API container's network namespace. The API container is
attached to both project-scoped `runtime` and `mcp-boundary` networks; this
one-shot container therefore reaches `api`, `db`, and the counter without
publishing another port. The source is bind-mounted read-only; the host capture
directory is the only writable mount:

```sh
export SRE_AGENT_BUILD_REVISION="$(git rev-parse HEAD)"
compose build api python-checks
compose up --build --force-recreate -d --wait --wait-timeout 90 \
  mcp-seed api mcp-upstream grafana-mcp
API_CONTAINER="$(compose ps -q api)"
API_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$API_CONTAINER")"
BUILT_API_IMAGE_ID="$(docker image inspect --format '{{.Id}}' \
  "${ISSUE29_PROJECT}-api-runtime:local")"
test "$API_IMAGE_ID" = "$BUILT_API_IMAGE_ID" || {
  echo "API image mismatch; stop without capturing evidence" >&2; exit 1;
}
export TESTED_SHA="$SRE_AGENT_BUILD_REVISION"
export CAPTURE_DIR="$DEMO_STATE_DIR/captures"
mkdir -p "$CAPTURE_DIR"
CHECKS_IMAGE="${ISSUE29_PROJECT}-python-checks:latest"
docker run --rm --user "$(id -u):$(id -g)" \
  --network "container:$API_CONTAINER" --env-file .env --env-file .env.worktree \
  -e TESTED_SHA="$TESTED_SHA" \
  -v "$PWD/scripts/issue29_capture.py:/app/scripts/issue29_capture.py:ro" \
  -v "$CAPTURE_DIR:/capture" "$CHECKS_IMAGE" \
  python /app/scripts/issue29_capture.py
```

Retain `API_IMAGE_ID` with the checkout SHA and build commands as runtime
provenance (image IDs contain no credentials). Do not change checkouts between
building and capturing; if any build, health, or image check fails, stop instead
of attributing evidence to the new SHA.

Review `.demo-state/$ISSUE29_PROJECT/captures/live-replay.json` for the exact
`tested_sha`, timestamps, observed HTTP statuses/error codes, method counts, and
sanitized correlated audit rows. Keep failed/skipped outcomes failed; do not turn
the diagnostic 502 into an accepted invocation.

### Real browser evidence (separate request)

The repository-versioned `scripts/issue29_capture_browser.cjs` uses Playwright from
`docker/e2e.Dockerfile` (pinned Playwright 1.63.0 base and npm lockfile). It navigates
to the actual FastAPI discovery endpoint, checks HTTP200/two tools, refuses to
capture a visible API key or Bearer header, and restricts authenticated browser
requests to the isolated API host. It writes a real PNG plus separate request-ID,
SHA and UTC provenance; no generated image or Swagger example substitutes for it.
For the #366 contract surface, `scripts/issue29_capture_openapi_browser.cjs`
uses the same browser runner and isolated network/configuration. Mount that script
instead at `/e2e/capture-browser.cjs` to capture the actual GET `/openapi.json`,
assert its required invocation body/two typed variants/request examples and render
the real document. It does not submit any illustrative request or invoke a tool.
Record the API candidate's actual SHA, not the instrument checkout's SHA if they
are different trees. The browser instrument is a repeat companion from #368;
its later versioning does not retroactively change earlier capture provenance.

The screenshot is a separate GET from the replay: do not assign its ID to replay
rows or include it in that earlier audit/count window. Manually inspect before
publication; a text scan does not certify a PNG.

```sh
docker build -f docker/e2e.Dockerfile -t "${ISSUE29_PROJECT}-evidence-browser:local" .
docker run --rm --user "$(id -u):$(id -g)" \
  --network "${ISSUE29_PROJECT}_runtime" --env-file .env --env-file .env.worktree \
  -e TESTED_SHA="$TESTED_SHA" \
  -v "$PWD/scripts/issue29_capture_browser.cjs:/e2e/capture-browser.cjs:ro" \
  -v "$CAPTURE_DIR:/capture" "${ISSUE29_PROJECT}-evidence-browser:local" \
  node /e2e/capture-browser.cjs
```


The failure-scenario functional check is versioned at
`tests/test_issue29_counting_relay.py`; it starts the real relay subprocess and a
local HTTP stub, verifies pass-through status/body/headers and method classification,
checks a refused-upstream safe 502 and ensures counters/control operations behave
as documented. Run it with the repository's isolated checks DB:

```sh
compose --profile checks run --build --rm python-checks pytest -q tests/test_issue29_counting_relay.py
```

## Stop safely

Stop only this isolated Compose project; this retains its containers and named
volumes and does not touch a separate demo project:

```sh
compose stop
```

**CA5 evidence boundary:** This is a procedure, not evidence that a live run
occurred for a particular commit. CA5 is evidenced by bounded, correlated,
metadata-only audit/discovery observations; discovery must show zero upstream
requests in its separate counter window. An invocation diagnostic is not a CA5
requirement, and a 502 is not success. Record the exact tested commit with
sanitized captures; evidence from an earlier candidate does not automatically
prove a later one.
