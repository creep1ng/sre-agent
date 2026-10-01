# Authorized MCP discovery: issue #29 acceptance matrix

The gateway requires a direct `mcp.discovery` grant on `grafana-mcp` before
discovery. It then reveals only active tools with a direct `mcp.invoke` grant
for the same authenticated Principal. No upstream MCP enumeration is used.

## Start development and reproduce the controlled checks

Docker and Compose are required. Bootstrap this worktree, then replace the
placeholders in ignored `.env` with four distinct non-production `sre_` keys,
non-placeholder model/provider identifiers and a random `AUDIT_HMAC_KEY`.
Do not source, print or commit that file. See [the team workflow](team-workflow.md)
for the credential boundary.

```sh
python scripts/bootstrap-worktree.py
# Edit .env before running Compose.
scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_mcp_*.py
```

For the normal development UI/API (without the Grafana MCP overlay), run
`scripts/worktree-compose up --build --wait`; `.env.worktree` lists its
loopback `WEB_PORT` and `API_PORT`. Stop only this worktree with
`scripts/worktree-compose down`. To verify the live Grafana MCP boundary, use
the [isolated demo runbook](governed-grafana-mcp-demo.md) instead: it starts the
MCP seed and upstream first. Starting only `compose.yaml` is not a live MCP
check.

`tests/test_mcp_seed.py::test_governed_discovery_uses_real_owner_and_direct_grants_per_principal`
creates two synthetic Principals over the two-tool owner fixture. The full
Principal sees both tools; the restricted Principal sees one, then none after
its tool grant is revoked. These rows are test-only, not persistent demo grants.

Two further tests pin the authentication boundary itself.
`test_rejected_credential_discovery_writes_no_audit_event` attaches a real
recorder and asserts a rejected credential produces no audit event, because the
documented boundary rejects before the MCP sink.
`test_http_discovery_authenticates_before_validating_the_request` asserts that
an unauthenticated request with an unknown query parameter is 401, not 422.

## Captured live evidence

The live walkthrough in the [governed Grafana MCP demo runbook](governed-grafana-mcp-demo.md)
was executed against this stack on the SHA recorded in each pull request. The
sanitized artifact is [`issue-29-live-evidence.json`](evidence/issue-29-live-evidence.json).
It contains only public identifiers, status codes, published error codes,
request IDs, boundary counter totals and audit metadata: no credential, no
`Authorization` header, no request body and no upstream result.

Every CA1–CA4 probe ran between two counter readings. The counter sat on the
governed boundary address `http://grafana-mcp:8000/mcp` that `compose.mcp.yaml`
configures, and forwarded to the image pinned in `demo/digests.lock`.

| Reading | Total HTTP requests at the boundary | MCP methods observed |
| --- | --- | --- |
| Before the first discovery probe | 0 | none |
| After the eighth discovery probe | 0 | none |

The instrument was shown to be live rather than idle: one subsequent
`POST /v1/mcp/tools/query_prometheus` by the fully granted Principal produced
exactly `tools/call: 1` alongside `initialize` and
`notifications/initialized`, which is the real crossing reaching the pinned
image. Discovery therefore decides before execution.

The authentication boundary is observable in the same artifact. Ten
authenticated discovery requests produced ten `mcp.discovery` rows across two
capture runs, and neither rejected credential produced a row, matching the
documented boundary rather than contradicting it.

| Criterion | Scenario | Observed result | Correlated audit row |
| --- | --- | --- | --- |
| CA1 | `GET /v1/mcp/discovery` as the fully granted seeded Principal | 200; `tools` = `query_prometheus`, `query_elasticsearch`, each with `display_name`, `description`, `visibility`, `tags`, `action` | 200, `read_metadata`, `response`, `success`, `allow` |
| CA2 | Same request as a Principal holding only the `query_prometheus` invoke grant | 200; `tools` = `query_prometheus`; the body contains neither `query_elasticsearch` nor its display name | 200, `read_metadata`, `response`, `success`, `allow` |
| CA3 | Same request for a Principal whose only grant is server-level discovery | 200; `tools` = `[]`; not 401 and not 403 | 200, `read_metadata`, `response`, `success`, `allow` |
| CA4 | No `Authorization` header | 401 `authentication_failed` | none, by design |
| CA4 | Well-formed but unknown bearer key | 401 `authentication_failed` | none, by design |
| CA4 | Authenticated Principal without the server discovery grant | 403 `resource_unavailable` | 403, `read_metadata`, `authorization`, `denied`, `deny` |
| CA4 | Granted Principal sends an unexpected query parameter | 422 `contract_validation_failed` | 422, `read_metadata`, `response`, `error`, `allow` |
| CA4 | Invoke `query_prometheus` without the invoke grant | 403 `resource_unavailable` | 403, `mcp.invoke`, `authorization`, `denied`, `deny` |
| CA5 | Correlate each public `request_id` against `audit_events` | 5 correlated rows; `identity.principal_ref` and `resource.resource_ref` are HMAC-SHA-256 digests; `content_state` = `absent`; `redacted_content` null; `untrusted_input` null | see above |

| Criterion | Expected public result | Controlled evidence | Live-stack evidence |
| --- | --- | --- | --- |
| CA1: permitted | 200 with only directly invokable tool metadata | `test_governed_discovery_uses_real_owner_and_direct_grants_per_principal`; HTTP discovery tests | Captured: 200 with both tools |
| CA2: hidden | No restricted tool ID, name or description in response | Same distinct-Principal PostgreSQL test | Captured: restricted tool absent from the body |
| CA3: empty | 200 with `tools: []`, not 401 or 403 | Same test after restricted tool grant revocation | Captured: 200 with an empty list |
| CA4: invalid credential/request | 401 before owner read; unknown query 422 `contract_validation_failed` | `tests/test_mcp_discovery.py` service and HTTP tests | Captured: 401 twice, 403 twice, 422 once |
| CA5: audit | HMAC-referenced identity/resource, action, decision, request ID; no arguments or results | PostgreSQL-backed discovery test checks three persisted, correlated metadata-only events | Captured: five correlated metadata-only rows |

Keep the three surfaces distinct. The controlled tests use in-memory doubles
and assert zero upstream calls by construction. The PostgreSQL-backed test
proves audit persistence against the real sink. Only the live walkthrough can
support an upstream-call claim, and it is the only surface that produced the
counter readings above.

Two limits remain outside this story. The full pinned demo environment is not
required for these criteria: the live walkthrough needs only `compose.yaml`
with `compose.mcp.yaml`, because discovery performs no upstream call.
Separately, tool invocation sends snake_case arguments while the pinned
upstream expects camelCase, so a granted invoke returns `502 upstream_invalid`
after a real crossing. Invocation is explicitly out of scope for this story and
is reported rather than changed here.

Independent human review of this evidence is still required before the issue
closes. If the candidate changes, recapture the affected proof.
