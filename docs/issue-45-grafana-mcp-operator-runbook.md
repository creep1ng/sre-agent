# Issue 45: operator prerequisites and evidence boundaries

**P3 delivers discovery; P4 adds controlled metric/log smoke-query behavior, not live acceptance.**
It helps independent freelancers prepare a safe environment before verifying
Grafana MCP through the governed gateway. All real CA1–CA8 remain open.

## Start here

1. Read [demo operations](demo-env.md), [signal definitions](demo-signals.md)
   and [gateway topology](governed-grafana-mcp-demo.md).
2. Confirm capacity, isolated resources and explicit target authorization.
3. Distinguish a healthy service, a controlled test and a real failure signal.
4. Follow the staged recovery checklist in the [issue tracker](../odd/tasks/issue-45-grafana-mcp-verification.md).
   Full-probe/cycle commands recorded there remain historical or planned;
   P3/P4 commands below cover only discovery and controlled smoke queries.

## Current contract and prerequisites

| Item | Verified reference or required condition |
|---|---|
| Base | `9eb3eb3dd3d55facfcd28d35490f85fedb95ac10` |
| Gateway contract | [MCP 1.0.0](../schemas/mcp/1.0.0/) |
| OpenTelemetry demo | Tag `3.0.0`, commit `1755859a9de82c2e5e225be68abc401a5ebf2b4f` |
| Grafana MCP | `grafana/mcp-grafana:1.3.0`; exact image pins in [digests.lock](../demo/digests.lock) |
| Resources | 4 CPUs, 4 GB free memory, 15 GB free disk; reassess before launch |
| Port/name isolation | The demo uses global `grafana-mcp` and `sre-mcp-boundary` names; a separate checkout alone is insufficient |
| Current capacity boundary | The recovered local environment had about 8 GB free and no OTel demo; no full demo was launched for this stage |
| Live authorization | Local/GitHub development does not authorize cloud, SSH, remote transfer or paid-provider probes |

The [manifest](../demo/manifest.yaml) declares the permitted demo layers and
ports. Do not add an MCP bypass port, attach the harness to demo networks or
reuse another project's resources to manufacture successful evidence.

## Safe local configuration

Use a private ignored `.env` based on `.env.example`, with non-production
values and no provider credentials. Never print, source, attach or commit it.
The existing `scripts/bootstrap-worktree.py` writes the worktree identity;
`scripts/worktree-compose` reads `.env` and then `.env.worktree`.
The generated identity owns the project and ports: do not replace it with a
fixed shared Compose project name. This stage does not start a stack.

For future authorized gateway checks, only named non-production gateway
credentials belong in the harness. The Grafana MCP/provider token does not.
The current [gateway overlay](../compose.mcp.yaml) supplies its token to the
API, not the harness. Keep that boundary unchanged.

## Acceptance gaps that must remain explicit

| CA | Required real evidence | Current gap / safe interpretation |
|---|---|---|
| CA1 | Prometheus metric and OpenSearch log through the gateway, with source/window | Controlled HTTP/CLI smoke queries cover fixed requests and safe summaries; no live Grafana/MCP response or CA1 acceptance is claimed |
| CA2 | Known-ID denial without prior discovery and zero upstream calls | A 403 or zero audit events cannot prove zero `tools/call` invocations; a trusted correlated upstream counter is required |
| CA3 | Discovery contains only authorized tools | Delivered server denial differs from partial-tool filtering; the latter depends on unmerged #29 / PR #365 |
| CA4 | Actual harness name/IP/port/proxy boundaries and no secret delivery | Missing targets or an unvalidated absent port binding remain unverified |
| CA5 | Read-only MCP with bypass/admin risk disclosed | `--disable-write` does not remove anonymous Grafana Admin or published proxy exposure; reachable paths are failure/risk |
| CA6 | Marker absent from complete logs, audit, snapshots and evidence | Sanitized CLI output is not an arbitrary-output redaction guarantee |
| CA7 | Normalized timeout/failure without alternate routes | P3 controlled redirects leave alternate-server counters at zero; live timeout evidence remains pending |
| CA8 | Two ordered failure→signal→reset cycles with measured baselines | Availability is not baseline recovery; real metric/log windows and chronology are required |

## Executable stage boundaries

- Discovery CLI (P3) → fixed metric/log smoke queries (P4) → known-ID-first denial →
  offline upstream-counter reconciliation.
- Harness boundary targets, including connect-only proxy/admin probes.
- Metric capture → log signal capture → offline two-cycle verification.

The gateway probe is `scripts/demo_mcp_gateway_probe.mjs`; it does not directly
connect to Grafana MCP. Signal capture
in `scripts/demo_signal_cycles.mjs` and boundary updates to `scripts/demo_mcp_probe.mjs`
remain planned, with their matching E2E tests. No future-stage command is prescribed here.
Each stage must retain behavior, tests, operator documentation and its own proof.

## Delivery and evidence boundaries

The user selected **stacked-to-main**: first PR targets main; subsequent PRs
review against their preceding owned branch while pending, then retarget main
after that parent integrates. Every PR integrates separately. There is no
feature tracker branch, automatic merge, issue closure or approved size exception.

The full recovery previously passed 13 controlled tests and three independent
targeted checks. Its rendered screenshot is historical full-candidate evidence,
not discovery-stage evidence. PR #424 published the prerequisite documentation;
P3 has separate current controlled HTTP/CLI evidence, not live CA completion.
Its publication, hosted CI and human review remain parent-owned. See
[PR evidence requirements](pr-evidence.md).

## Rollback and next step

P3 adds only the discovery CLI, matching tests and documentation/evidence; no
producer, configuration, migration or dependency changes. Revert those additions
and documentation updates together, preserving PR #424 and recovery sources.
The next unit is governed metric/log queries with matching controlled checks.
Reassess its actual diff against its current base;
retained source-line estimates do not justify an exception.

## P3: discovery-only CLI

After the private local configuration setup above, use `MCP_GATEWAY_URL`,
`DEMO_HUMAN_API_KEY` (server grant) and `RESTRICTED_HARNESS_API_KEY` (no server
grant) only for explicitly authorized targets. Keep credentials out of command
arguments, files for publication and output. Supply them through the harness
environment using Compose `-e NAME`, not literal values. Then run
`node scripts/demo_mcp_gateway_probe.mjs` inside that harness.
`MCP_GATEWAY_URL` must identify a gateway origin (scheme, host and optional port)
with no non-root path; unsupported paths fail before any HTTP request.

This stage makes exactly two GET requests to `/v1/mcp/discovery`, never a tool
invocation. Exit 0 means the expected server/two tools and a non-enumerating,
non-retryable 403 with a safe UUID were observed; exit 1 means failure. Redirects
are rejected; each request keeps a 35-second budget. Reports allowlist fields,
not raw response text. This does not prove CA2 or partial-tool CA3 filtering.

Run the P3 discovery cases using the historical command below; P4's current
networkless command appears in its section:

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree \
  -f compose.yaml --profile checks run --rm --no-deps \
  -v "$PWD/tests:/source/tests:ro" harness node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```

Use the existing harness image or an independently authorized harness build;
this stage reused the cached image without building. See the P3
[controlled evidence](evidence/issue-45-pr02/report.md). Known-ID invocation,
upstream counters and cycle verification remain pending.

## P4: controlled metric/log smoke queries

After P3 discovery, the probe issues exactly two fixed POSTs through the public
gateway: `query_prometheus` for `up` from `webstore-metrics` at `now`, and
`query_elasticsearch` for the Lucene filter `resource.service.name:checkout`
from `webstore-logs` over `now-5m..now` with limit 1. Redirects are rejected;
each request retains its 35-second timeout. Output includes only source, window,
HTTP status, normalized error kind, result/warning counts and metric result type.
Raw operational responses are not reported. A successful controlled report is
`pending` because it has no independent upstream witness; it is not CA1 evidence.

The controlled fixture test can be repeated without network access or secrets
using the already-cached pinned harness image:

```sh
docker run --pull never --network none --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```

See the [P4 controlled evidence report](evidence/issue-45-pr03/report.md).
Live Grafana/MCP behavior, provider credentials, an independent counter, full
redaction, network isolation and all CA1–CA8 remain unverified.
