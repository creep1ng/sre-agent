# Authorized MCP discovery: issue #29 evidence

Discovery requires a direct `mcp.discovery` grant on `grafana-mcp`; the
response reveals active tools with a direct `mcp.invoke` grant for the same
Principal. It does not enumerate upstream tools.

## Passed replay and provenance

[`issue-29-live-evidence.json`](evidence/issue-29-live-evidence.json) records
the sanitized, isolated replay tested at PR368 descendant
`944f658f5a951c6506c6545e4fabf0c4ecd6ee43`, **not** a live execution on PR367.
The immediately prior PR367 matrix and 5cc9 replay are preserved unchanged at
archive commit `0b60b96da2047152f90c9a3669886a29e4f7289e`; the earlier
historical capture remains at `f3116b69909a482a76e91512135535632bca49fd`.
The 944 replay runtime image was built at `d484d3a8dd094d3c198a789c5f071be0d27be343`
and is the inspected same API image (`sha256:df681be1…`). Its `src/`,
`migrations/`, `schemas/` (contracts), `pyproject.toml`, `uv.lock`,
`compose.yaml`, and `compose.mcp.yaml` inputs have no diff to tested 944. The
intervening `docker/api.Dockerfile` change adds a demo compose file to the
checks-image COPY list; the demo/counter overlays do not change the API runtime.
This supports applicability to PR367 but does not turn the PR368 replay into a
PR367 execution; human review must confirm that applicability.

The evidence kind is controlled integration: real HTTP API-key authentication,
gateway, PostgreSQL audit sink, and pinned MCP binary. Grafana's backend was
intentionally inert at `http://127.0.0.1:1`; no Grafana query or successful tool
execution is claimed. The replay's 38 checks passed. They are not a pytest
result. Full environment and image IDs are in the JSON.

## CA → evidence → tested commit

All replay rows below refer to tested commit
`944f658f5a951c6506c6545e4fabf0c4ecd6ee43` and its recorded capture window.

| CA | Observed result | Request ID | Audit / boundary evidence |
| --- | --- | --- | --- |
| CA1 full visibility | 200; `query_prometheus` and `query_elasticsearch`; metadata fields present | `2bd3cd74-eab0-4695-a088-8342e7f83a64` | Correlated metadata-only discovery row |
| CA2 partial visibility | 200; only `query_prometheus`; restricted ID, name and description absent | `152d6c4f-237e-4e42-aee8-0905622324e0` | Correlated metadata-only discovery row |
| CA3 empty visibility | 200; `tools: []`; restricted metadata absent | `d4499420-79ec-49a5-aeb7-d33ab85587a5` | Correlated metadata-only discovery row; empty-list proof, not field-presence proof |
| CA4 no discovery grant | 403 `resource_unavailable` | `7c68b4bc-318b-47fe-849d-c454f2600472` | Denied discovery audit row |
| CA4 unknown key | 401 `authentication_failed` | `dc7ed049-2354-4d17-acb4-a0dcd3f473c0` | Rejected before MCP; no MCP row expected or required |
| CA4 no key | 401 `authentication_failed` | `3a1eb9ea-b893-47a1-92fe-d88b130885d2` | Rejected before MCP; no MCP row expected or required |
| CA4 unexpected query | 422 `contract_validation_failed` | `a4959c74-49e7-42e1-af4b-6cd82b3414e8` | Response audit row |
| CA4 invoke without grant | 403 `resource_unavailable` | `b781bbb1-6f5b-4b6a-b0c7-7c3514d31e4c` | Denied invoke audit row |
| CA5 metadata-only audit / discovery boundary | Five discovery rows plus denied invoke and two controls: eight rows, HMAC identity/resource references, `content_state=absent`, no redacted content or untrusted input | The eight audit request IDs are listed in JSON | Selected by request ID and UTC window; not a global count |
| Invocation boundary controls (not discovery success) | Cold call: 502 `upstream_invalid`, 3 boundary HTTP requests (`initialize:1`, `notifications/initialized:1`, `tools/call:1`). Warm call: 502 `upstream_invalid`, 1 request (`tools/call:1`). Neither is successful tool execution. | `62ea2197-7916-436f-a660-5ed51f70b1c9` / `48edda96-b6d5-4633-8813-8486a5c473a4` | Each has an upstream-stage error audit row; discovery itself caused zero crossings |

The seven discovery GETs and denied invocation occurred in
`[2026-10-03T17:32:20.179029Z, 2026-10-03T17:32:21.718401Z)`; the boundary
counter remained zero. The full audit selection is bounded to the ten replay
request IDs and `[2026-10-03T17:32:20.179029Z,
2026-10-03T17:32:22.175737Z)`, returning five discovery and three invoke rows.
The two 401s have no MCP row because both fail before reaching that service.

The counter was reset before discovery (epoch 4) and again before the warm
control (epoch 5). `total_http_requests` counts forwarded boundary requests,
excluding counter-control endpoints; `upstream_attempts` increments before
forwarding; `upstream_failures` counts relay-client exceptions, not an HTTP 502
response. `mcp_methods` counts recognized JSON-RPC methods in object/batch
bodies (`initialize`, `notifications/initialized`, `tools/call`); unknown
string methods map to `other`. The versioned implementation is in PR368 at
`scripts/issue29_counting_relay.py` (blob
`4cacf7b81b57d70d4fcd7412d8c123d2e267addd`), not in the PR367 tree.

## Browser screenshot and separate failed attempt

The real-browser screenshot is [`issue-29-current-discovery.png`](evidence/issue-29-current-discovery.png)
with [separate provenance](evidence/issue-29-current-discovery.provenance.json).
It shows a real FastAPI JSON response with both published tools, status 200,
request ID `4b405cb1-f7bc-4085-a41e-c699ddafc498`, captured at
`2026-10-03T17:31:18.350Z` (HTTP `Date`: `Sat, 03 Oct 2026 17:31:17 GMT`). This
browser request predates the replay window and is **not** one of its request
IDs, audit rows, or counter observations. Three earlier PNGs remain historical;
their visible request IDs/date values do not match this replay and their tested
SHA is unknown:

| Older screenshot | Visible request ID | Visible HTTP `Date` |
| --- | --- | --- |
| `issue-29-pr365-live-discovery.png` | `2c9b249e-e790-44cf-8db1-62bcc09d1262` | `Thu, 01 Oct 2026 23:28:38 GMT` |
| `issue-29-pr367-live-discovery.png` | `1b090d22-115d-471d-9c17-a4fc44fcddbe` | `Thu, 01 Oct 2026 23:32:46 GMT` |
| `issue-29-pr368-live-discovery.png` | `6a40bf0a-4704-4437-a826-f4d06394ae0f` | `Thu, 01 Oct 2026 23:33:22 GMT` |

No old image is relabeled as current.

A separate replay attempt at `17:31:31Z` failed its cold-handshake assertion:
the relay counter had reset, but the existing API/upstream MCP session had not,
so the control counted only `tools/call: 1`. That failure remains in the
continuation evidence and is not mixed into the passed capture. The isolated
API container alone was restarted; the following run passed all 38 checks.
No database or volume was deleted. The command log records that the Compose
stack itself had remained alive about 16 hours; no fresh full-stack startup is
claimed.

The user explicitly accepted the stack's size exception. No size/approval label
was applied automatically. That exception does not constitute human evidence
acceptance or merge approval. The issue remains incomplete pending ordinary
human review and confirmation of PR367 applicability.

## Commands and bounded audit inspection

The capture/replay scripts are versioned only in PR368. The actual commands,
with private host output locations represented by `CAPTURE_DIR` and
`DELIVERY_DIR`, are recorded in the JSON. They built the pinned browser and
checks runner, restarted only the isolated API, captured the separate browser
request, then ran the passing replay at the exact tested SHA. `.env` is shown
only by path; never print or publish its values. No provider call was made.

The replay query selected all ten case request IDs and used both UTC bounds. An
equivalent read-only audit inspection is:

```sql
SELECT occurred_at, correlation->>'request_id' AS request_id,
       response_status, operation, action, stage, outcome, reason_code,
       policy_decision->>'decision' AS decision, content_state,
       COALESCE(jsonb_typeof(redacted_content), 'null') = 'null' AS no_content,
       COALESCE(jsonb_typeof(untrusted_input), 'null') = 'null' AS no_untrusted_input
FROM audit_events
WHERE operation IN ('mcp.discovery', 'mcp.invoke')
  AND occurred_at >= TIMESTAMPTZ '2026-10-03T17:32:20.179029Z'
  AND occurred_at <  TIMESTAMPTZ '2026-10-03T17:32:22.175737Z'
  AND correlation->>'request_id' = ANY(ARRAY[
    '2bd3cd74-eab0-4695-a088-8342e7f83a64', '152d6c4f-237e-4e42-aee8-0905622324e0',
    'd4499420-79ec-49a5-aeb7-d33ab85587a5', '7c68b4bc-318b-47fe-849d-c454f2600472',
    'dc7ed049-2354-4d17-acb4-a0dcd3f473c0', '3a1eb9ea-b893-47a1-92fe-d88b130885d2',
    'a4959c74-49e7-42e1-af4b-6cd82b3414e8', 'b781bbb1-6f5b-4b6a-b0c7-7c3514d31e4c',
    '62ea2197-7916-436f-a660-5ed51f70b1c9', '48edda96-b6d5-4633-8813-8486a5c473a4'
  ])
ORDER BY occurred_at, event_id;
```

The 38 live replay checks are not the existing pytest suite. No hosted CI or
independent human acceptance is implied by these local results. Do not mark #29
complete or integrate until the human review and repository checks permit it.
