# Issue 30 — governed invocation acceptance

Historical planning (2026-10-03): Ricardo confirmed the matrix and real controlled server, then chose
**two PRs**, no size exception: infrastructure/control, followed by acceptance.
Consume #187's runtime; no retries/fallback, autonomous calls, UI, Skills or BoK.
At that planning snapshot, #18/#129/#187/#29 were recorded as closed/Done in Project 8;
#30 was Todo and no existing acceptance PR was found. Historical 78845c8 proof and
#475's diagnostic 502 are not current success. See the current acceptance review below.

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
CA4: request IDs AND UTC window; HMAC identity/resource, action invoke and decision
at applicable stages, with only the approved MCP invalid-input exception below;
no arguments, raw output, untrusted input or redacted content. 401 has no MCP row.
CA5: allowed/denied known ID **before discovery**, 200/403 and tools/call1/0.

Relay resets are per case; cold initialize/initialized are separate from tools/call,
with no tools/list. The proxy also counts forwards to the actual MCP: success1,
injected faults0 (one relay attempt); controls never fabricate successful results.
The vector value is deterministic; its observation timestamp is run-dependent.
The approved CA4 interpretation below replaces the former pending interpretation;
it does not establish complete acceptance of #30.
RED on4a4515b observed real200/+1 and safe errors but no public success correlation.
The minimal additive X-Request-ID correction preserves the normalized body.
The PNG is a separate real browser POST/window, not replay evidence; inspect it.
Local checks are not hosted CI or human acceptance. Actual execution/provenance
belongs in the sanitized artifacts and PR; this recipe alone is not proof.

## Approved CA4 interpretation

[Ricardo's recorded decision](https://github.com/creep1ng/sre-agent/issues/30#issuecomment-6137102582)
accepts exclusively the MCP invocation with invalid input, HTTP 422 and
`stage=validation`. For that event, the [published audit schema 2.7.0][validation-schema]
forbids `identity`, `resource` and `policy_decision`. It retains `operation=mcp.invoke`,
`action=invoke`, `correlation.request_id` and `reason_code=contract_validation_failed`;
the public error is `error.code=contract_validation_failed`.

[Authorization precedes input validation][invoke-source]: the Principal and the
`allow` decision are already known. Their omission is a deliberate audit-contract
restriction, not missing authentication or authorization. The [MCP projector][projector-source]
also removes that context for the validation stage. This accepted limitation of
direct attribution does **not** apply automatically to every 422 or change other
stages' requirements. Identity, resource, action, decision and correlation remain
required where the applicable contract requires them. Arguments, raw output and
secrets must never be persisted in this metadata-only evidence.

### Proposed CA4 replacement in #30 (not published)

Replace only the CA4 checkbox; leave CA1–CA3, CA5 and the rest of the issue unchanged:

> - [ ] **CA4.** La auditoría metadata-only cumple el esquema aplicable a cada etapa y contiene identidad, recurso, acción, decisión y correlación donde el contrato los exige. Exclusivamente para la invocación MCP con entrada inválida, HTTP 422 y `stage=validation`, se acepta la omisión contractual de `identity`, `resource` y `policy_decision`, conservando `action=invoke`, `correlation.request_id` y el error contractual (`reason_code=contract_validation_failed`). La autorización ya ocurrió y la identidad y la decisión `allow` son conocidas; la omisión no implica ausencia de autenticación/autorización ni se generaliza a todos los 422. No se persisten argumentos, salida cruda ni secretos. Véase la [decisión aprobada](https://github.com/creep1ng/sre-agent/issues/30#issuecomment-6137102582).

## Acceptance review against current main

Review date: 2026-10-12 (America/Bogota). GitHub `main` and the clean starting
checkout both resolved to `763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`.
Live [Project 8](https://github.com/users/creep1ng/projects/8) reads show #30 **Todo**,
Sprint 3, Estimate 0; #18/#129/#187 **Done**, but #29 **In progress** even though
its issue is closed. [#30](https://github.com/creep1ng/sre-agent/issues/30) remains open.
[PR #478](https://github.com/creep1ng/sre-agent/pull/478) and
[PR #477](https://github.com/creep1ng/sre-agent/pull/477) were merged on 2026-10-04 (America/Bogota);
that integration does not establish full story acceptance.

The [GREEN acceptance records](evidence/issue30-acceptance.jsonl) belong to tested
SHA `be422443b1a20fe059ec86b6b5eb6c9552f005ba`, replay window
`2026-10-03T23:27:48.178107Z`–`2026-10-03T23:28:35.011308Z`: ten scenarios,
nine selected audit rows. The [invocation PNG](evidence/issue30-invocation.png)
belongs to a **separate** browser POST/window, recorded on JSONL line 14 at the
same tested SHA; it is not replay evidence. The [infrastructure RED records](evidence/issue30-infrastructure.jsonl)
belong to `d7518ac637c3af31ce6c417869e364b802f82b51`, with four missing-success-correlation
assertions. None of those captures, records, outcomes or SHAs is changed or relabeled.

| Criterion | Current acceptance status | Evidence and comparison with current source |
| --- | --- | --- |
| CA1 | Partial | [GREEN line 12](evidence/issue30-acceptance.jsonl#L12): 200, normalized vector(1), one relay `tools/call` and one real forward. Current [gateway][invoke-source] retains one call and `X-Request-ID`, but its result adapter changed since the tested SHA; no new current-main replay. |
| CA2 | Partial | [GREEN lines 5–7](evidence/issue30-acceptance.jsonl#L5-L7): no grant/nonvisible tool/invalid credential = 403/403/401, safe errors and zero calls/forwards. Current authorization still precedes execution; no new current-main counter evidence. |
| CA3 | Partial | [GREEN lines 8–11](evidence/issue30-acceptance.jsonl#L8-L11): 422/504/503/502 with safe published [MCP errors](../schemas/mcp/1.0.0/grafana-mcp.yaml). Validation makes zero calls; injected faults make one relay attempt but zero real forwards. Current input validation/error mapping exists; transport/result handling changed, so historical success is not a new execution. |
| CA4 | Partial; interpretation satisfied | [GREEN lines 3–12](evidence/issue30-acceptance.jsonl#L3-L12): correlated metadata-only rows with stage-appropriate HMAC attribution; line 8 retains action/correlation/error and omits the three fields exactly as approved. Current schema/projector agree. The 401 has zero `mcp.invoke` rows; the 422 decision does not approve that separate boundary. No new current-main SQL evidence or full audit-schema validation of persisted rows. |
| CA5 | Partial | [GREEN lines 3–4](evidence/issue30-acceptance.jsonl#L3-L4): known ID before any discovery, 200/403, call/forward 1/1 and 0/0. The [replay client](../scripts/issue30_capture.py) still orders these first; current invocation does not require discovery. No new current-main replay. |

All GREEN references in the table mean **historical evidence**, not tests run in
this documentation review. The runner, audit helper, browser client, overlays and
`uv.lock` match the historical tested checkout; the gateway does not. Static
comparison is not a replacement for rebuilding/recreating and exercising main.
SQL evidence exposes a derived `decision` column; the contract field is
`policy_decision`, and correlation is `correlation.request_id`, not a top-level ID.

### Remaining acceptance work / separate evidence gaps

- CA4's interpretation is resolved; only its documentation is updated here. The
  issue-body replacement above remains a proposal until publication is authorized.
- Repeat the documented isolated-stack recipe at the intended acceptance SHA,
  recording image identity, counters and bounded SQL without reusing old totals.
- Historical JSONL line 15 records 1477 passed, one skipped and three local relay
  readiness failures; a targeted rerun still had one failure. It also records
  pending schema tooling and human review. These records remain historical, not
  current failures or current passes; this review does not resolve them by assertion.
- The historical SQL projection proves selected metadata, not validation of every
  persisted event against the full current schema. No authentication-stage audit
  proof accompanies the 401: [the current handler returns before MCP auditing][invoke-source].
  Track that attribution/evidence boundary separately; do not broaden the approved
  422 exception or silently call it accepted.
- Independent human review of evidence freshness and scope remains necessary;
  neither merged PRs nor CI alone accept #30. No schema, runtime, test expectation,
  historical evidence, remote issue or PR is changed by this documentation work.

[validation-schema]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/schemas/releases/2.7.0/json-schema/domain/audit-event.schema.json#L844-L870
[invoke-source]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/src/sre_agent/gateway/mcp.py#L446-L544
[projector-source]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/src/sre_agent/gateway/audit.py#L176-L211
