# Authorized MCP discovery: issue #29 evidence

Discovery requires a direct `mcp.discovery` grant on `grafana-mcp`; it reveals
active tools with a direct `mcp.invoke` grant for that same Principal. It does
not enumerate upstream tools.

## Current replay and provenance

[`issue-29-live-evidence.json`](evidence/issue-29-live-evidence.json) records a
sanitized, isolated replay. It was executed at PR368 descendant SHA
`5cc9a17aff9cdef56c5ae57f51b98efeae91901d`, not on PR367's documentation commit
`f3116b69909a482a76e91512135535632bca49fd`. The prior historical matrix and
JSON remain available unchanged at that immutable commit:
`git show f3116b69909a482a76e91512135535632bca49fd:docs/issue-29-discovery-acceptance.md`
and `git show f3116b69909a482a76e91512135535632bca49fd:docs/evidence/issue-29-live-evidence.json`.
The replay environment reports no runtime-code/config diff between its image
build source `d484d3a8dd094d3c198a789c5f071be0d27be343` and tested SHA `5cc9` for
`src`, migrations, contracts/dependencies, Compose inputs and `docker/api.Dockerfile`.
PR368's intervening test-stage Docker `COPY` and demo-overlay changes do not
alter the API runtime image. This supports applicability to PR367 but is not a
claim that PR367 itself was live-tested; human review must confirm applicability.

The primary surface is controlled integration: real HTTP API-key auth and
gateway, PostgreSQL audit sink, and pinned MCP binary. Grafana's backend URL was
intentionally inert (`localhost:1`); no Grafana query or successful tool
execution is claimed. The 38 capture checks passed. Existing pytest checks are
separate and were not run by this replay.

## CA → evidence → commit

| CA | Observed result | Request ID(s) | Evidence / status |
| --- | --- | --- | --- |
| CA1 full visibility | 200; `query_prometheus`, `query_elasticsearch`; published metadata present | `122590cc-53ac-4649-a1a0-1dda4b8c2fbe` | Live controlled integration; audit row correlated in bounded capture; tested `5cc9a17…` |
| CA2 partial visibility | 200; only `query_prometheus`; restricted ID/name/description absent | `767633b3-15cb-4c51-8d24-89c60e7b9181` | Live controlled integration; audit row correlated; tested `5cc9a17…` |
| CA3 empty visibility | 200; `tools: []`; restricted metadata absent | `f10fc6b4-1084-4246-a946-f6e5768ce870` | Live controlled integration; audit row correlated; tested `5cc9a17…` |
| CA4 no discovery grant | 403 `resource_unavailable` | `fe64c1e6-033a-4657-9b2e-c3afa3debdd5` | Denied audit row; tested `5cc9a17…` |
| CA4 unknown key / missing key | 401 `authentication_failed` each | `12492297-4042-4691-bf6e-e3c3f7dd19df` / `18b35b83-5b73-45e5-8004-16abf6ea085c` | Rejected before MCP; no audit row is expected or required; tested `5cc9a17…` |
| CA4 invalid query | 422 `contract_validation_failed` | `b9ef1644-4730-4ef0-834b-c38fe339b11e` | Response audit row; tested `5cc9a17…` |
| CA4 invoke without grant | 403 `resource_unavailable` | `d9e94462-8255-4abf-afe3-4566894e5f5f` | Denied invoke audit row; tested `5cc9a17…` |
| CA5 metadata-only audit and discovery boundary | Five discovery rows (full, partial, empty, denied, invalid query); HMAC references present, content absent, no untrusted input; counter stayed zero through discovery and denial | Five discovery IDs above; 401 IDs intentionally have no rows | Eight bounded rows total: five discovery plus denied invoke and two controls; window and all selected rows are in JSON; tested `5cc9a17…` |
| Invocation boundary control (outside discovery success) | Cold 502 `upstream_invalid`; 3 HTTP crossings/methods: initialize 1, notifications/initialized 1, tools/call 1. Warm 502 `upstream_invalid`; 1 crossing, tools/call 1. Neither ran successfully. | `9313c2fc-1776-4dbb-95bd-41b1fa1b67e9` / `611b46d5-9f2d-40f6-8588-c2ce13a2b4b5` | Each error has an upstream-stage audit row; demonstrates boundary/handshake counts, not tool success; tested `5cc9a17…` |

The seven discovery GETs and denied invocation produced zero boundary requests.
Two 401s correctly have no MCP rows because they fail before the MCP service.
The audit query window is `[2026-10-03T01:24:20.826998Z,
2026-10-03T01:24:22.309602Z)` and filters the ten probe `request_id`s; it returns
exactly eight rows. These are not a global database count. Full selected audit
fields and exact times are recorded in the JSON artifact.

The replay resets the counter before discovery and before the warm control.
`total_http_requests` counts forwarded relay requests, excluding counter control
endpoints; `upstream_attempts` increments before forwarding; `upstream_failures`
counts relay-client exceptions only, not an HTTP 502 returned by the upstream.
`mcp_methods` counts recognized JSON-RPC method values in object or batch bodies
(`initialize`, `notifications/initialized`, `tools/call`); unknown methods map
to `other`. The versioned source and blob are recorded in JSON and live in the
PR368 descendant, not in the PR367 tree.

## Capture record and repeatability

The run started `2026-10-03T01:24:19.733029Z` and ended
`2026-10-03T01:24:22.330506Z`. Environment versions, image IDs, pinned MCP image,
runtime build source and sanitized command record are in the JSON. Actual stack
startup returned exit 0; the recorded capture command returned exit 0 with 38
checks. Command record uses `.env` by path only; never publish or print its
contents. The capture script and counter are versioned in PR368; they are not
present in PR367 and are not falsely presented as runnable from this tree.

The old PNG(s) are historical: their visible request IDs/date stamps do not
match this replay, and their tested-SHA provenance is unknown. A current
screenshot was not produced because local disk capacity blocked capture; no
replacement is fabricated. Screenshot evidence and independent human review
remain pending. The issue remains open.

## Separate controlled checks and bounded audit query

Mocks/doubles can prove policy branches by construction; PostgreSQL integration
can prove persistence for its own test requests. Neither is the live replay.
For the separate existing pytest suite, the containerized command is:

```sh
docker compose --project-name i29reconcile368 --profile checks run --build --rm python-checks pytest -q tests/test_mcp_contract.py tests/test_mcp_discovery.py tests/test_mcp_owner.py tests/test_mcp_seed.py
```

That suite was not run in this capture and is not marked passed here. The replay
script's PostgreSQL query uses both a UTC window and selected request IDs. An
equivalent read-only inspection is:

```sql
SELECT occurred_at, correlation->>'request_id' AS request_id,
       response_status, operation, action, stage, outcome, reason_code,
       policy_decision->>'decision' AS decision, content_state,
       redacted_content IS NULL AS no_content,
       untrusted_input IS NULL AS no_untrusted_input
FROM audit_events
WHERE occurred_at >= TIMESTAMPTZ '2026-10-03T01:24:20.826998Z'
  AND occurred_at <  TIMESTAMPTZ '2026-10-03T01:24:22.309602Z'
  AND correlation->>'request_id' = ANY(ARRAY[
    '122590cc-53ac-4649-a1a0-1dda4b8c2fbe', '767633b3-15cb-4c51-8d24-89c60e7b9181',
    'f10fc6b4-1084-4246-a946-f6e5768ce870', 'fe64c1e6-033a-4657-9b2e-c3afa3debdd5',
    '12492297-4042-4691-bf6e-e3c3f7dd19df', '18b35b83-5b73-45e5-8004-16abf6ea085c',
    'b9ef1644-4730-4ef0-834b-c38fe339b11e', 'd9e94462-8255-4abf-afe3-4566894e5f5f',
    '9313c2fc-1776-4dbb-95bd-41b1fa1b67e9', '611b46d5-9f2d-40f6-8588-c2ce13a2b4b5'
  ])
ORDER BY occurred_at, event_id;
```

Do not close #29 until remaining screenshots, applicability confirmation,
size disposition, and ordinary independent human review are resolved. This
local work does not publish or update any PR/issue; remote publication requires
separate explicit authorization.
