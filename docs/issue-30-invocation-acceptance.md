# Issue 30 — governed invocation acceptance

Ricardo confirmed the matrix and real controlled server (2026-10-03), then chose
**two PRs**, no size exception: infrastructure/control, followed by acceptance.
Consume #187's runtime; no retries/fallback, autonomous calls, UI, Skills or BoK.
#18/#129/#187/#29 are closed/Done in Project 8; #30 is Todo. No existing acceptance
PR was found. Historical 78845c8 proof and #475's diagnostic 502 are not current success.

## Environment / exact recipe

Follow [#29's setup and image-identity procedure](governed-grafana-mcp-demo.md),
using a fresh unique ISSUE30_PROJECT and ignored `.env`/`.env.worktree`: distinct
synthetic API keys, random database password/audit key, model `synthetic/control`,
provider `synthetic`, empty provider keys. Never source/print configuration.
DEMO_STATE_DIR must stay at the absolute `.demo-state/$ISSUE30_PROJECT` directory
holding its private generated `grafana-mcp.env`; preserve supplied configuration.
CAPTURE_DIR is absolute/private/writable. Export TESTED_SHA from the committed
checkout and SRE_AGENT_BUILD_REVISION=$TESTED_SHA before building; do not change
code between build/capture. Record Docker/Compose/Python versions, uv.lock and
pinned demo digests, and built/running API image equality plus ready health.

```sh
docker compose -p "$ISSUE30_PROJECT" --env-file .env --env-file .env.worktree -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml config --quiet
docker compose -p "$ISSUE30_PROJECT" --env-file .env --env-file .env.worktree -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml build api python-checks
docker compose -p "$ISSUE30_PROJECT" --env-file .env --env-file .env.worktree -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml up --build --force-recreate -d --wait --wait-timeout 120 mcp-seed api grafana-mcp issue30-fault-proxy mcp-upstream
docker run --rm --user "$(id -u):$(id -g)" --network "container:$API_CONTAINER" --env-file .env --env-file .env.worktree -e TESTED_SHA="$TESTED_SHA" -v "$PWD/scripts:/app/scripts:ro" -v "$CAPTURE_DIR:/capture" "$ISSUE30_PROJECT-python-checks:latest" python /app/scripts/issue30_capture.py
docker compose -p "$ISSUE30_PROJECT" --env-file .env --env-file .env.worktree -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml --profile checks run --build --rm python-checks
docker build -f docker/e2e.Dockerfile -t "$ISSUE30_PROJECT-evidence-browser:local" .
docker run --rm --user "$(id -u):$(id -g)" --network "${ISSUE30_PROJECT}_runtime" --env-file .env --env-file .env.worktree -e TESTED_SHA="$TESTED_SHA" -v "$PWD/scripts/issue30_capture_browser.cjs:/e2e/capture-browser.cjs:ro" -v "$CAPTURE_DIR:/capture" "$ISSUE30_PROJECT-evidence-browser:local" node /e2e/capture-browser.cjs
docker compose -p "$ISSUE30_PROJECT" --env-file .env --env-file .env.worktree -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml stop
```

API_CONTAINER comes from the scoped Compose `ps -q api`; require image equality
and ready health before replay. Rebuild/recreate after source changes. No prune,
`down -v`, production credentials or paid calls. Retain synthetic audit records.

## CA → public POST → output → counter → audit

All requests target `/v1/mcp/tools/query_prometheus`; JSON records each case's
exact command/payload class, expected/observed output, counter and bounded audit.
CA1: 200 vector(1), one empty metric/value1/no warnings, tools/call1, success/allow.
CA2: no grant/nonvisible/invalid credential = 403/403/401, zero calls each.
CA3: invalid input/timeout/unavailable/malformed = 422/504/503/502, calls0/1/1/1.
CA4: request IDs AND UTC window; HMAC identity/resource, action invoke and decision;
no arguments, raw output, untrusted input or redacted content. 401 has no MCP row.
CA5: allowed/denied known ID **before discovery**, 200/403 and tools/call1/0.

Relay resets are per case; cold initialize/initialized are separate from tools/call,
with no tools/list. The proxy also counts forwards to the actual MCP: success1,
injected faults0 (one relay attempt); controls never fabricate successful results.
The vector value is deterministic; its observation timestamp is run-dependent.
The published validation-stage schema forbids identity/resource/decision at422;
that omission is explicit, and any stronger CA4 interpretation remains for Ricardo.
RED on4a4515b observed real200/+1 and safe errors but no public success correlation.
The minimal additive X-Request-ID correction preserves the normalized body.
The PNG is a separate real browser POST/window, not replay evidence; inspect it.
Local checks are not hosted CI or human acceptance. Actual execution/provenance
belongs in the sanitized artifacts and PR; this recipe alone is not proof.
