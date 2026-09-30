# Issue 45: operator prerequisites and evidence boundaries

**P6 adds offline reconciliation of a separately trusted counter witness; P5 denial and P3/P4 behavior remain controlled-only, not live acceptance.**
It helps independent freelancers prepare a safe environment before verifying
Grafana MCP through the governed gateway. All real CA1–CA8 remain open.

## Start here

1. Read [demo operations](demo-env.md), [signal definitions](demo-signals.md)
   and [gateway topology](governed-grafana-mcp-demo.md).
2. Confirm capacity, isolated resources and explicit target authorization.
3. Distinguish a healthy service, a controlled test and a real failure signal.
4. Follow the staged recovery checklist in the [issue tracker](../odd/tasks/issue-45-grafana-mcp-verification.md).
   Full-probe/cycle commands recorded there remain historical or planned;
   P3/P4 commands below describe their historical stages; P5 covers known-ID
   denial, P6 covers offline witness reconciliation, and P7-D checks only
   supplied service-name/direct-IP health targets. Published-origin checks are
   a separate P7-E follow-up.

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

- P3 discovery → P4 fixed metric/log smoke queries → P5 known-ID-first denial
  before all discovery. P6 offline upstream-counter reconciliation is implemented
  by this probe's `--reconcile <report> --witness <file>` mode. It consumes a
  separately operator-validated witness without network access; it does not
  capture counters or independently establish witness provenance or semantics.
- P7-D supplied service-name/direct-IP health checks and P7-E published-origin
  checks are controlled target probes only; connect-only proxy/admin probes and
  independently verified topology/binding evidence remain required for CA4/CA5.
- Metric capture → log signal capture → offline two-cycle verification.

The gateway probe is `scripts/demo_mcp_gateway_probe.mjs`; it does not directly
connect to Grafana MCP. Signal capture in `scripts/demo_signal_cycles.mjs` and
published-origin boundary checks remain planned, with matching E2E tests. The
P7-D service/IP stage below does not prove complete harness isolation. No
future-stage command is prescribed here.
Each stage must retain behavior, tests, operator documentation and its own proof.

## Delivery and evidence boundaries

The user selected **stacked-to-main**: first PR targets main; subsequent PRs
review against their preceding owned branch while pending, then retarget main
after that parent integrates. Every PR integrates separately. There is no
feature tracker branch, automatic merge or issue closure. A user-approved size
exception applies only to PR #434's current P6 input-read correction; it does
not authorize future PRs.

The full recovery previously passed 13 controlled tests and three independent
targeted checks. Its rendered screenshot is historical full-candidate evidence,
not discovery-stage evidence. PR #424 published the prerequisite documentation;
P3 has separate current controlled HTTP/CLI evidence, not live CA completion.
Its publication, hosted CI and human review remain parent-owned. See
[PR evidence requirements](pr-evidence.md).

## Rollback and next step

P6 adds offline reconciliation to the CLI, matching controlled E2E assertions,
and P6-specific stage documentation; no producer, runtime, configuration,
migration or dependency changes. Roll back the P6 reconciliation and bounded
file-reader source, its offline CLI tests, and P6-specific documentation together.
Preserve P5 known-ID-first denial, retryable:false validation, distinct denial
and discovery UUIDs, and the P3/P4 history and evidence. Offline reconciliation
is implemented; actual upstream-counter capture/provenance and real CA1–CA8
evidence remain separate pending work.
Reassess each actual diff against its current base; retained source-line
estimates do not justify an exception.

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

## P5: controlled known-ID-first denial

The current probe first sends one restricted-role `POST` to the public
`/v1/mcp/tools/query_prometheus` route, using the same fixed `webstore-metrics`
`up` payload as the allowed metric query. This request occurs before any
discovery. It then performs the unchanged P4 sequence: allowed discovery,
allowed Prometheus POST, allowed Elasticsearch/Lucene POST, and restricted
discovery. The complete controlled request order is asserted by the E2E test.

The report uses the `denied` summary key and exposes only HTTP status, the
allowlisted `resource_unavailable` code, a validated safe UUID, the contract's
`retryable: false` value, and `upstream_delta: null`. The later restricted-
discovery request keeps a distinct UUID. Invalid status, code, UUID, or missing,
true, null, or nonboolean retryable values fail closed; response bodies and
credentials are not summarized. A successful controlled fixture remains
`pending` because it supplies no trusted upstream-call witness. In particular,
the 403 and null delta do not prove zero upstream invocations or satisfy CA2.
No P6 witness/reconciliation option is present in this stage.

Repeat the controlled test with the cached pinned image and the P4 networkless
Docker command above. This exercises loopback fixtures only; it is not live
gateway, Grafana/MCP, upstream-counter, or CA1–CA8 acceptance evidence. No
provider credential, stack, build, pull, or network is needed.

## P6: offline upstream-witness reconciliation

Only after an operator has independently established a trusted upstream
`tools/call` counter and its correlation to the P5 denied request may the
sanitized P5 pending report and a separate witness file be reconciled. The
witness contains `kind: upstream-counter`, a bounded source identifier, the
exact `denied.request_id`, and nonnegative safe-integer `before`/`after` counts.
The request ID must match; `after` must be at least `before`; only zero delta
passes. A generic audit/event count (including `audit_events_total`) is never
accepted, even if relabeled. Shape checks cannot establish counter semantics:
the operator remains responsible for independently validating the source and
correlation. A fixture witness is not real CA2 evidence.

The CLI validates the current P5 `gateway-query-smoke` report, requires and
retains `denied.retryable: false`, compares denial/discovery UUID identity
case-insensitively, requires exact witness/denial request-ID matching, and normalizes output to allowlisted summary fields. It reads bounded local JSON only and
makes no gateway or upstream call. Missing, malformed, oversized, mismatched,
invalid, or nonzero witnesses fail closed. Keep witness source material private;
do not attach raw counters, audit rows, credentials, or response bodies.

Reconciliation can be repeated offline with the cached pinned image. Mount only
the script, schemas, and private sanitized evidence read-only; no credentials or
network are required:

```sh
docker run --pull never --network none --rm \
  -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  -v "$EVIDENCE_DIR:/source/evidence:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node /source/scripts/demo_mcp_gateway_probe.mjs \
  --reconcile /source/evidence/pending.json \
  --witness /source/evidence/witness.json
```

The controlled E2E uses synthetic loopback fixtures only. No actual operator
counter was captured; no P6 result closes CA2 or any CA1–CA8 criterion.

## P7-D: supplied service-name and direct-IP health checks

The current `scripts/demo_mcp_probe.mjs` accepts only the supplied
`MCP_PROBE_HOST`, `MCP_PROBE_PORT`, and `MCP_IPS` inventory. It issues
unauthenticated GET requests to fixed `/healthz`, does not follow redirects,
cancels response bodies, and emits only target kind/status/HTTP status. Any HTTP
response is reachable and fails; missing, invalid or blocked targets remain
`unverified` (exit 2), never an isolation pass. `coverage` is
`supplied-targets-only` and `full_boundary` remains `pending`.

Repeat the controlled loopback HTTP/CLI cases with the cached pinned image:

```sh
docker run --pull never --network none --memory=256m --memory-swap=256m --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_probe.mjs
```

These fixtures do not observe real harness networks or prove binding, proxy,
admin, token-absence, or total isolation. P7-E published-origin checks and
independent network/topology evidence remain pending; CA1–CA8 remain open.
