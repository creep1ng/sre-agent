# Authorized MCP discovery: issue #29 evidence

Discovery requires a direct `mcp.discovery` grant on `grafana-mcp`; the response
contains active tools with a direct `mcp.invoke` grant for that Principal. It
does not enumerate upstream tools.

## Evidence status and surfaces

[`issue-29-live-evidence.json`](evidence/issue-29-live-evidence.json) is a
sanitized historical capture. Its literal tested commit, UTC capture date,
environment identity and capture-window bounds were not retained. Do not
attribute it to a PR SHA or claim it was captured on this candidate. Request IDs
and statuses are preserved as historical observations. The checked-in screenshot
shows a different partial-discovery request (`1b090d22-115d-471d-9c17-a4fc44fcddbe`)
and one HTTP `Date` value (`Thu, 01 Oct 2026 23:32:46 GMT`); it is not the JSON
request and does not establish a run window or tested SHA. Missing raw response proof means negative public error
codes are unverified. `expected_error_code` denotes contract expectation only.
The old global audit `COUNT=50` is discarded, not case evidence.

The five selected discovery audit rows are the three 200s, 403 and 422 listed
in JSON, each correlated by request ID. They do not substantiate ten requests
or two runs. A 401 rejected before entering MCP intentionally has no MCP audit
row. Historical capture claims zero relay HTTP requests around discovery, but
its bounds are unknown; it is not a reproducible zero-call proof. The separate
positive control counted one parsed `tools/call` and returned HTTP 502
`upstream_invalid`: this demonstrates a request crossed the governed boundary,
not successful tool execution. No `initialize` or
`notifications/initialized` handshake count is recorded. Discovery does not
cover invocation correctness.

| CA | Scenario / historical observed result | Audit evidence | Status |
| --- | --- | --- | --- |
| CA1 | Full Principal: 200; both tools and published metadata | request `56fd27b7-f4fb-407f-bffd-1cce90088cd4`; metadata-only response row | historical, provenance incomplete |
| CA2 | Partial Principal: 200; only `query_prometheus`; restricted ID/name absent | `35d4b91c-4407-42b2-a913-2ab4d87fcaa5`; metadata-only response row | historical, provenance incomplete |
| CA3 | Discovery-only Principal: 200, empty tools | `417649d4-9822-486b-84a7-96a95e417617`; metadata-only response row | historical, provenance incomplete |
| CA4 | No credential / unknown key: 401 each; error code unverified | `abd62d55-c550-4569-9abc-301ae385cb6b` / `37629542-b840-4978-b1c3-e57c13769a30`; no MCP row expected | historical; code unverified |
| CA4 | No discovery grant: 403; code unverified | `9e9af57b-fc12-4f89-bfa7-aeee38e019dc`; denied metadata row | historical; code unverified |
| CA4 | Unknown query: 422; code unverified | `2a6a310a-2f80-4802-ac07-ed1fc6b611fa`; response error row | historical; code unverified |
| CA4 | Invoke without grant: 403; code unverified | `29fc67f2-df87-4d69-804d-7eb7891f22c8`; denied invoke row | historical; code unverified |
| CA5 | Five selected discovery IDs above correlate to metadata-only rows | identity/resource references present; `content_state=absent`; no content | historical; bounded query below required to reproduce |

Controlled tests use doubles; they can prove policy branches and zero upstream
calls by construction, not live behavior. PostgreSQL integration proves sink
persistence for its own test requests, not this historical capture. A live
walkthrough is required for real gateway, audit and relay assertions. The
current artifact is not enough to mark any live CA complete.

## Reproduce a bounded audit capture

For a new capture, record the tested full SHA, UTC environment/date, and UTC
window `[start,end)` immediately around probes. Put the observed request IDs in
`request_ids.txt` (one UUID per line); use only a dedicated isolated database.
This read-only query requires both request-ID and time bounds; empty IDs return
no rows. It does not backfill historical window values:

```sh
psql "$DATABASE_URL" -v start="$CAPTURE_START_UTC" -v end="$CAPTURE_END_UTC" \
  -v ids="$(paste -sd, request_ids.txt)" <<'SQL'
SELECT occurred_at, correlation->>'request_id' AS request_id, response_status,
       operation, action, stage, outcome, reason_code, content_state,
       (redacted_content IS NULL) AS no_content
FROM audit_events
WHERE occurred_at >= :'start'::timestamptz AND occurred_at < :'end'::timestamptz
  AND correlation->>'request_id' = ANY(string_to_array(:'ids', ','))
ORDER BY occurred_at, event_id;
SQL
```

For each case retain sanitized status, public error code (or explicitly
`unverified`), request ID, UTC window, selected audit fields and relay counter
before/after. Never retain credentials, headers, bodies, query results or raw
logs. Do not close #29 until every required CA is demonstrated at a named,
tested candidate and independently reviewed.
