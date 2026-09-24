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

| Criterion | Expected public result | Controlled evidence | Live-stack evidence |
| --- | --- | --- | --- |
| CA1: permitted | 200 with only directly invokable tool metadata | `test_governed_discovery_uses_real_owner_and_direct_grants_per_principal`; HTTP discovery tests | Pending current-candidate capture |
| CA2: hidden | No restricted tool ID, name or description in response | Same distinct-Principal PostgreSQL test | Pending current-candidate capture |
| CA3: empty | 200 with `tools: []`, not 401 or 403 | Same test after restricted tool grant revocation | Pending current-candidate capture |
| CA4: invalid credential/request | 401 before owner read; unknown query 422 `contract_validation_failed` | `tests/test_mcp_discovery.py` service and HTTP tests | Pending current-candidate capture |
| CA5: audit | HMAC-referenced identity/resource, action, decision, request ID; no arguments or results | PostgreSQL-backed discovery test checks three persisted, correlated metadata-only events | Pending live-stack capture |

All controlled discovery cases assert zero calls to the upstream client. The
PostgreSQL-backed test also proves audit persistence, but does **not** replace
a real Grafana MCP/boundary counter. This worktree's pinned demo now passes
`scripts/demo_env.py verify` after the payment healthcheck timeout was corrected
in `compose.demo.yaml`. That proves demo availability, **not** gateway CA1–CA5:
the user reports verifying a live gateway flow, but no sanitized CA1–CA5 outputs,
upstream-counter reading, or correlated audit capture tied to the current candidate
are recorded here. Keep all live criteria pending until that evidence is captured.
Before issue acceptance, a PR needs the exact tested commit,
sanitized public outputs, real upstream count, correlated audit rows and
independent human review. If the candidate changes, recapture affected proof.
