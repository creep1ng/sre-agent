# Issue 45: Governed Grafana MCP Verification

**Current delivery stage: bounded P7-D CLI symlink-invocation correction based on PR #437 head `41a3ed21aec8f579a2b5ce03bd37aecc34f41975`, now in draft after review finding 4144842486.** Parent reports exact pre-fix P7-D CI 36718125319 all-eight green and repaired governance/reconciliation 36720192583 passing; those historical checks do not cover symlink execution. This candidate adds a first-failing actual CLI symlink case and its minimal entrypoint correction; local RED/GREEN and syntax checks are recorded below, while parent-owned independent proof/publication remain pending. The separate P7-E origin tests remain frozen in their own worktree. No live target or CA completion is claimed; all real CA1–CA8 and human acceptance remain open.

## Objective

Make gateway-only metric/log consultation, MCP isolation, and a repeatable failure-signal-reset check reproducible and honestly evidenced for issue #45.

## Problem and Why

The integrated demo can query Grafana MCP directly, while the gateway has governed discovery and invocation. Neither path alone proves that the real harness obtains both signals only through the gateway or that denial, network isolation, and evidence sanitization hold together.

## Scope and Constraints

- Reuse the pinned demo and published MCP contract; do not rebuild OTel or the gateway runtime.
- Use only `query_prometheus` and `query_elasticsearch` via the gateway public API.
- Keep the MCP/provider token out of the harness and all evidence; derive only bounded, safe signal summaries.
- Never treat a healthy service check as proof of a failure signal.
- Do not claim total isolation if Grafana Admin, proxy, host-port, or other bypass remains reachable.
- Keep real-container evidence distinct from simulated transport tests.
- Current handoff authorizes bounded issue #45 local repair/tests and parent-owned commits, owned-branch publication and PR evidence in `creep1ng/sre-agent`. This P6 stage validates the current P5 retryable:false report field and case-insensitive offline UUID identity only; preserve offline/no-network witness boundaries. No cloud, SSH, paid-provider probe, deployment, merge, or issue closure.
- Parent refreshed live GitHub Project #8: issue #45 remains Todo, Sprint 4, with CA1–CA8 in scope. PR #425 has an open gateway-root-path review finding; no human acceptance is claimed.
- Follow the revised `AGENTS.md`: this is an academic tool for independent freelancers, not production SRE hardening. Prefer one repeatable E2E test over isolated or change-detector tests, and use only real evidence or exact reproduction instructions.

## Authorized Scope

- Preserve root-only routing, P4 metric/Lucene queries and P5 known-ID-first denial; validate retryable:false in offline reconciliation and compare UUID identity case-insensitively.
- Preserve malformed-entry/redirect/privacy coverage and 35-second budget. Only P6 offline reconciliation source/tests/report/runbook/task may change. No producer/runtime, Compose/Dockerfile, dependency, live-service, network or credential changes.
- Sole Luna high writer owns the bounded P6 local restack and offline report correction; parent owns independent checks, commits, screenshots, publication, branch propagation and human-review requests. Preserve the original P6 backup `6f6f9569419aaa8eb261bf32dbefcc6b0948b2c6` and the pre-retryable-restack backup.

## TDD

- Mode: strict
- Source: issue-specific handoff §4 / OPERATING-RULES §4, which enables strict TDD for issue #45 implementation; repository `AGENTS.md` separately prefers E2E, prohibits writing unit tests after code, and requires failure modes first for isolated work.
- Runner for this P6 correction: pinned Node 22.14 cached harness with offline CLI reconciliation in a networkless container; exact `docker run --pull never --network none` reproduction is recorded in the P6 report. No host package manager, DB/API/demo or live credential is needed. Historical root-only and preview-helper notes remain in dated checkpoints below.

## Tasks

- [ ] **MCP45-1 — Prove governed access from the harness**
  - Add a harness-side gateway probe for filtered discovery, allowed metric/log queries with source and window, denied known-ID invocation, and a genuine upstream tools/call counter witness (not an audit-event count). Start with an observed failing test.
  - Acceptance: only public gateway routes are called, the denied path has an observed upstream delta of zero, and summaries contain no raw operational bodies or credentials.
- [ ] **MCP45-2 — Prove isolation and safe failures**
  - Add name/IP/port/proxy bypass and token-absence probes from the actual harness network, plus synthetic-marker and timeout/failure assertions without raw-body publication. Start with an observed failing test.
  - Acceptance: unsafe reachable paths or leakage are explicit failures; no uncontracted retry or fallback is introduced.
- [ ] **MCP45-3 — Verify two complete signal cycles**
  - Add an explicit signal checker tied to the published Prometheus/OpenSearch queries and run fail → signal observation → reset → measured baseline twice. Start with an observed failing test.
  - Acceptance: signal and baseline are asserted separately from availability, with safe time windows and provenance.
- [ ] **MCP45-4 — Record acceptance evidence**
  - Document pinned versions, SHA, containerized commands, environment, safe observed outputs, and CA1–CA8 mapping. Run real-container checks only when an isolated demo and test credentials are available; otherwise mark those criteria pending instead of substituting mocks.

## Applicable Checks

- Observed RED → GREEN → REFACTOR per implementation task; favor a real harness E2E test that produces a repeatable artifact
- Existing MCP contract, authorization, overlay, and demo regression tests
- `node --check` for changed JavaScript; Ruff only if Python is changed
- `git diff --check` and structural review of network/credential boundaries
- Real harness/container probes and two demo cycles, with unavailable checks stated explicitly

## Historical Recovery Progress (2026-09-24; not current proof)

- Base fast-forwarded from `137b101` to integrated `origin/main` `3c7b4a3`, then rebased to `6eb5422` to obtain PR #376 instructions; untracked task/probe files were preserved.
- Existing direct-MCP signal script is a query reference, not gateway acceptance evidence.
- Project #8 was consulted live with explicit read-only authorization. The updated instructions reject invented captures and prioritize E2E behavior evidence.
- MCP45-1 has a gateway-only CLI probe and a controlled HTTP/CLI E2E test. The probe emits a sanitized pending report, and a separate offline reconciliation accepts only a matching sanitized counter witness. No real gateway/MCP execution or counter capture has occurred, so MCP45-1 remains open.
- MCP45-2 has a fail-closed harness boundary CLI covering service name, supplied direct IP/published endpoint, known provider-token variables, and proxy environment. It also reports normalized gateway timeout/unavailable errors. Controlled E2E coverage passed. A real worktree-network probe against the live MCP service name and its observed boundary-network IP ran twice; both returned `unverified` because there was no published MCP host port. This is partial reachability evidence, not complete isolation or CA4 acceptance. Proxy-route inspection and marker scanning across audit/log/snapshots remain pending; MCP45-2 remains open.
- MCP45-3 has a public-gateway capture/verify CLI for two documented payment-failure cycles. It compares checkout error metrics with checkout/proxy log summaries after two-minute windows and a 150-second settling interval. Controlled E2E passed, but no real fail/reset cycle or baseline was observed; MCP45-3 remains open.
- MCP45-4 has an operator runbook with the pinned base/environment, exact gateway/harness/cycle commands, and a corrected CA1–CA8 crosswalk. A boundary-only live harness observation is recorded there; it is explicitly unverified and does not complete CA4. A second full demo remains NO-GO with 5.1 GB free versus the documented 15 GB minimum and fixed demo project/container/network/port collisions. Candidate SHA, real captures, and PR evidence remain pending; MCP45-4 remains open.

## Historical Verification Evidence (not rerun for this candidate)

- MCP45-1 RED: `node --test tests/test_demo_mcp_gateway_probe.mjs` failed before implementation because the pending report/exit behavior did not exist.
- MCP45-1 GREEN and parent spot check: the same command passed (1 controlled HTTP/CLI E2E test). `node --check` and `git diff --check` passed in the writer run.
- MCP45-2 RED: `node --test tests/test_demo_mcp_probe.mjs tests/test_demo_mcp_gateway_probe.mjs` failed in 2 cases before implementation (missing-target status and normalized timeout summary).
- MCP45-2 GREEN and parent spot check: the same command passed (2 controlled HTTP/CLI E2E tests). `node --check` and `git diff --check` passed in the writer run.
- MCP45-3 RED: `node --test tests/test_demo_signal_cycles.mjs` failed because the capture/verify CLI module was absent.
- MCP45-3 GREEN and parent spot check: `node --test tests/test_demo_signal_cycles.mjs tests/test_demo_mcp_gateway_probe.mjs tests/test_demo_mcp_probe.mjs` passed (3 controlled HTTP/CLI E2E tests).
- Timeout correction RED/GREEN: `node --test tests/test_gateway_timeout_budget.mjs` failed with the old 15-second client budget, then passed after both gateway callers adopted 35 seconds to outwait the public gateway's 30-second timeout. Parent spot check passed all four focused tests.
- Runbook structural checks: 10 shell blocks parsed with `bash -n`; 6 relative links and script/Compose paths resolved; `git diff --check` passed. No live Docker check was performed.
- An anonymous-config build of the pinned harness image succeeded through the worktree Compose setup; all four controlled HTTP/CLI E2E tests passed in that container, as did seven Node syntax checks and `git diff --check`. A subsequent boundary-only real harness probe ran twice against the live `grafana-mcp:8000` service name and its observed `sre-mcp-boundary` IP without attaching the harness to a demo network. Both runs exited `2` with `status=unverified`: service name and direct IP were blocked, token and proxy variables were absent, and `mandatory_targets_missing` reflected the absent MCP host port. The live `otel-demo`/`grafana-mcp` remained unchanged (observed ID prefix `795d6e8`); the worktree runtime network was removed. No test credentials or other stack mutations were used. This is not CA4 acceptance, and no gateway, counter/audit, marker-scan, or signal-cycle evidence was produced.
- RDD is off; native risk assessment rated the current executable candidate `medium`. Its 1,690 changed lines across nine paths exceed the repository's 400-line PR threshold; any acceptance PR needs cohesive review slices or an explicit maintainer-approved size exception. No PR or exception exists.
- User selected `scripts/worktree-compose` for tests. `python3 scripts/bootstrap-worktree.py` reused the existing worktree project identity, and an anonymous-config harness build succeeded. The wrapper isolates the core Compose project/ports, not the demo's globally named MCP container/network. Do not use it to start a parallel full demo while the live `otel-demo` is running; the available disk and fixed names make that unsafe.
- Real Compose harness, Grafana MCP, and denied upstream counter checks: pending, not replaced by the controlled test.

## Current Candidate and Local Repair Tasks (2026-09-29)

- Route: delegated direct ODD; sole writer, no SDD state.
- Preserved complete recovery: local exclusive candidate; private locators remain in Engram, not public evidence.
- Branch: `codex/issue-45-recovery-20260929`; base/HEAD: `5b6109bd2c8100455136cf12ce91c52830833c7f`.
- Protected original recovery worktree: read-only; nine file hashes and status recorded outside the repository before recovery.
- Current resources supplied by parent: approximately 8 GB free, no OTel demo running here. Historical live-container and 5.1 GB statements above are not current observations.
- RDD: off, global; no native review or approval claim.
- Current producer contract: MCP `1.0.0`; server-restricted discovery denies without enumeration, but server grant currently exposes both tools. Partial-tool CA3 depends on unmerged #29 / PR #365, not a consumer workaround.
- Historical full task document mirror: `odd/issue-45-grafana-mcp-verification/tasks`. Current publication-readiness edits are local only; mirror refresh is pending because authoritative runtime Engram identity is unavailable. No session was registered.

- [x] **MCP45-R1 — Repair smoke log query syntax**: controlled HTTP/CLI rejection of non-Lucene syntax, then published Lucene smoke query; observed RED/GREEN.
- [x] **MCP45-R2 — Reject gateway redirects**: both callers must leave alternate-server call count at zero and emit bounded errors; keep 35-second budgets.
- [x] **MCP45-R3 — Verify server-restricted discovery**: delivered public error contract, no unauthorized enumeration; partial-tool visibility remains pending producer dependency.
- [x] **MCP45-R4 — Enforce two-cycle chronology**: reject failure-before-baseline, reset-before-failure, and overlapping cycles; retain independent baseline/signal checks.
- [x] **MCP45-R5 — Exercise supplied proxy/admin targets**: bounded read-only TCP connection probes; any reachable bypass is failure/risk. Missing published-binding witness remains pending without independently validated source.
- [x] **MCP45-R6 — Reconcile runbook and local evidence**: current identity/commands, dependency ledger, CA gaps, full focused container checks, syntax and structural checks, one honest slicing forecast, recovery isolation readback.

## Bounded Independent-Verification Corrections

Independent read-only verification reproduced two CA2 coverage defects despite the prior 11/11 suite. The parent authorized this one correction in the same exclusive candidate; no producer edits, new build, Git operation, remote access or expanded acceptance work.

- [x] **MCP45-C1 — Preserve known-ID denial without prior discovery**: move the restricted known-ID invocation before any restricted discovery; first observe a failing real HTTP/CLI order assertion, preserving both safe request IDs and offline witness matching.
- [x] **MCP45-C2 — Reject generic audit-event witnesses**: observe offline CLI RED for `audit-counter` / `audit_events_total` zero, then accept only independently validated operator `upstream-counter` measurements; no event-count-to-upstream-delta promotion. Preserve safe UUID/counter guards; real counter evidence stays pending.
- [x] **MCP45-C3 — Reconcile correction evidence and forecast wording**: update runbook, rerun full harness/syntax/structural checks, refresh manifests and recovery isolation; qualify prior grouping as unmeasured semantic slices, not exception necessity.

## Current Verification Evidence

- C1/C2 observed RED: narrowed gateway E2E had two failing child assertions (wrong request order; generic audit zero accepted), TAP 2 passed/3 failed including parent (`correction-red.log`). After source repair, narrowed GREEN passed 5/5 (`correction-green.log`). The restricted known-ID POST now runs first, distinct safe discovery/denial request IDs remain checked, and audit counters fail without setting upstream_delta or witness. Valid matching `upstream-counter` zero still passes; UUID/non-negative monotonic counter guards remain intact. Refactor review required only request-block relocation and the narrowed witness-kind condition. Final correction suite passed 13/13; seven syntax checks passed (Node v22.14.0); 12 shell blocks, six links, script/Compose/service paths and diff check passed. Evidence: `correction-full-tests.log`, `correction-syntax.log`, `correction-structure.json`. Protected recovery hashes/status/HEAD remained unchanged. No build, producer/runtime edit or remote operation occurred; independent targeted recheck remains parent-owned.

- Pre-correction R6 full harness suite passed **11/11** (eight top-level plus three chronology subtests; `final-tests.log`); seven in-container `node --check` invocations passed (`final-syntax.log`, Node v22.14.0). Twelve fenced shell blocks parsed without execution, six relative links and all script/Compose/service references resolved (`structure.json`); `git diff --check` passed. Parent spot-check remains separate.
- Final full suite used the exact required four test paths and existing wrapper, omitting `--build` solely to reuse the one verified image under the build budget. Image ID `sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d`; Dockerfile, entrypoint and package/lock inputs match base. Exact commands and logs: `commands.md` in the private local recovery evidence package and `environment.json`.
- Recovery isolation: original nine hashes, status and HEAD match the pre-copy snapshot (`recovery-isolation.json`). No source producer, runtime/Compose boundary, other worktree, branch/index, commit or GitHub artifact changed.
- Not run: Python/DB/demo/real Grafana/MCP lanes, real upstream counter/audit, marker export scans, actual network inventory, or real cycles. No current screenshot, hosted CI or human acceptance is claimed. Existing controlled counters and synthetic chronology fixtures are not real-service evidence. CA1–CA8 and original MCP45-1..4 remain open.
- Historical recovery's 1,690-line statement omitted the 44-line timeout test; the recovered starting delta was 1,734 additions+deletions, not current proof.

- R5 RED: 0/3 (`r5-red.log`); explicit counter pass before source repair again 0/3 (`r5-red-connect.log`), both supplied proxy/admin routes received zero connections. GREEN: 3/3 (`r5-green.log`), one actual TCP connection per target and zero application bytes; reachable non-HTTP listeners fail/risk, missing/credential-bearing targets stay unverified. Refactor review kept TCP probing separate from legacy MCP HTTP reachability. Absent published-binding proof stays pending; no bypass port or demo-network attachment was created.

- R4 RED: three malformed-order CLI scenarios incorrectly passed; TAP reports 0/4 including parent (`r4-red.log`). GREEN: 4/4 (`r4-green.log`); ordered six-phase capture summaries verify, earlier failure/reset and overlapping second cycle reject with bounded `capture_chronology_invalid`. Fixture times are explicitly synthetic; this is not live cycle proof. Refactor review retained distinct settling, signal, baseline and chronology checks.

- R3 RED: new restricted-discovery assertion failed because the CLI made no restricted GET/report (2 pass/1 fail, `r3-red.log`). GREEN: 3/3 (`r3-green.log`), including rejection of enumerating and retryable denial responses; offline reconciliation requires the new safe evidence. Producer remains unchanged; this does not prove partial-tool CA3. Refactor review kept normalization explicit.

- R2 RED: both redirect-negative CLI cases failed (alternate server received four requests per caller); existing case passed (`r2-red.log`, 1 pass/2 fail). GREEN: gateway suite plus preserved timeout checks passed 4/4 (`r2-green.log`), alternate counters zero. Both fetch helpers now reject redirects with existing safe failure summaries, retaining 35 seconds. Refactor review retained separate bounded callers.

- R1 RED: narrowed gateway test with `--build` failed 0/1, HTTP 422 and `log_query_failed` for the JSON DSL query (`r1-red-container.log`). GREEN: same harness/test without `--build` passed 1/1 (`r1-green.log`). Refactor review: no extra abstraction needed; changed only the published query literal.
- Harness configured with unique worktree identity `4e5fb20b88f6`, anonymous Docker config, pinned Node 22.14 image; initial sandbox Docker denial resolved by approved local escalation. No DB/API/demo/provider started.

All historical evidence above remains labeled historical. Required runner:

```sh
scripts/worktree-compose --profile checks run --build --rm --no-deps -v "$PWD/tests:/source/tests:ro" harness node --test /source/tests/test_demo_mcp_gateway_probe.mjs /source/tests/test_demo_mcp_probe.mjs /source/tests/test_demo_signal_cycles.mjs /source/tests/test_gateway_timeout_budget.mjs
```

Use the same inspected harness lane, narrowed to each test file, for RED/GREEN. Build at most once, then reuse. No Python/DB/demo lane, network attachment, bypass port, or provider credentials. Local environment uses ignored non-production `.env` and generated `.env.worktree`; never print/source/attach either.

## Stacked-to-main delivery (user selected)

The user explicitly selected PRs integrated into main: `stacked-to-main`. First PR targets main; later PRs target the immediate preceding owned branch while it is pending, then retarget main after parent integration. Each PR integrates separately. No feature/tracker branch, automatic merge/closure or size exception is authorized.

The complete pre-staging candidate had 2,159 changed lines. Its parent full-suite rerun passed 13/13 and independent targeted verification passed 3/3. The genuine rendered package for fingerprint `d1d98d93c325291e3c4989c5caacff9195564d227fdd2391510ebf6c140046c4` is historical full-candidate evidence, not proof of this documentation stage. Staging changes this tracker fingerprint; all original implementation/test bytes are preserved in a private allowlisted source snapshot.

Prior foundation353/boundary383/signal601/gateway781 groupings were not minimal semantic slices and never justified an exception. A single measured semantic pass assigns recovery hunks to usable staged behaviors; retained-line counts are not final per-base diffs because extraction needs matching CLI/test adapters. No tests, history, comments or whitespace may be removed to fit the budget.

- [x] **MCP45-P1 — Map semantic delivery stages**: record precise recovered path/hunk ownership, measured retained lines and adapter uncertainty outside the repository; keep every behavior/test/documentation section assigned. No later stage is built in this task. The private semantic map assigns every recovered source/test/runbook line once; retained totals P3=329, P4=214, P5=49, P6=241, P7=372 (383 existing diff), P8=297, P9=102, P10=398. These are not final runnable diffs; CLI/test adapters and tracker changes remain to measure. P10 includes separable passive documentation, not an exception prerequisite.
- [x] **MCP45-P2 — Prerequisites documentation PR**: preserve this full tracker, publish a useful operator prerequisite/CA-gap guide, verify shell syntax/current links, render a fresh actual screenshot and prepare the exact PR template. Require <=400 measured additions plus deletions; publication/CI/human review remain parent-owned and pending. Observed first-stage checks: initial guide/tracker checks parsed one historical shell block and resolved ten links; publication-readiness checks now parse three blocks and resolve fifteen links with the added report. Fresh cached-container readback equals guide bytes / Node v22.14.0, and the unchanged sandboxed offline Chromium capture was visually inspected. Current mirror refresh is pending.
- [x] **MCP45-P3 — Discovery CLI**: allowed/server-restricted GET discovery, safe normalization, 35-second budget and redirect rejection. Fresh container HTTP/CLI RED 0/2 (module absent), GREEN 2/2; refactor review retained the small validators and explicit safe report. No query, invocation, witness, capture, CA2 or partial-tool filtering. Final syntax/docs/evidence checks recorded below; mirror pending.
- [ ] **MCP45-P4 — Governed metric/log smoke queries**: published PromQL/Lucene, safe summaries and failure/empty signals with E2E. Stage tests pending; real CA1 remains open.
- [ ] **MCP45-P5 — Known-ID denial before discovery**: correct request order and separate safe IDs, keep upstream proof pending; E2E must observe no earlier restricted discovery. Stage tests pending.
- [ ] **MCP45-P6 — Offline upstream witness reconciliation**: upstream-counter only, UUID/delta validation, no network/no audit-event substitution; matching/malformed/mismatched E2E. Stage tests pending.
- [ ] **MCP45-P7 — Harness boundary targets**: name/IP/port plus connect-only proxy/admin, no token delivery and fail/unverified summaries with real fixture connections. Stage tests pending.
- [ ] **MCP45-P8 — Metric capture**: public gateway metric summaries with source/window/settling, usable partial capture but no complete signal/cycle claim; matching E2E. Stage tests pending.
- [ ] **MCP45-P9 — Log signal capture**: add checkout/proxy log summaries, complete capture shape and matching HTTP/CLI cases; keep real cycles pending. Stage tests pending.
- [ ] **MCP45-P10 — Two-cycle verification**: offline baseline/failure/reset/chronology, shared caller timeout checks and final full runbook/evidence reconciliation. Stage tests pending; original live acceptance tasks stay open.

No current public PR or hosted CI result is claimed. Parent refreshed issue #45 OPEN / Project #8 Todo, current main unchanged, and no owned issue PR before starting this chain. Each executable stage must have its own observed checks; prior full-candidate RED/GREEN is historical, not fresh stage proof. New logic requires observed RED before implementation.

## First-stage evidence

The fresh [prerequisite-guide screenshot](../../docs/evidence/issue-45-pr01/prerequisites.png) renders only this stage's operator guide, source SHA-256 `4e7b75726b9c155ebb9ec759a46188e9d1c76833590b4e6b82a997c7ee8be3fc`. It does not reuse the historical full-candidate image. PNG and guide were inspected for sensitive values; no environment, credentials, raw private paths or provider payloads are included.

## Next Step

The documentation prerequisite stage has its own observed structural/rendered evidence and a [sanitized report](../../docs/evidence/issue-45-pr01/report.md). Fresh cached-image readback returned exit 0 / Node v22.14.0 and exact guide bytes. The public Node base is not cached; the source-validated Compose build recipe is explicitly unexecuted. Guide/PNG bytes are unchanged; current tracker mirror is pending. Parent reviews, commits and publishes it, then independently scopes the next semantic stage against its actual base. Preserve all real CA1–CA8 gaps and producer dependencies; no automatic integration is authorized.

## P3 execution checkpoint

Base `73fd51ab6ea9a2235b51aa70e851ab930e89a5c0`, branch `codex/issue-45-02-discovery`; parent PR [#424](https://github.com/creep1ng/sre-agent/pull/424) is published with 346 changed lines. Parent refreshed issue #45 OPEN / Project #8 Todo / Sprint 4. Some PR checks passed and others are running; requested human review is not approval. Only this new discovery worktree is writable. Original recovery, full recovery and published first-stage worktree stay read-only. Existing task history and future stages remain intact.

P3 checks: the exact existing worktree checks harness ran Node E2E from current mounted tests. Initial runner setup rejected unsupported `--no-build` before execution; removing that flag restored the authorized command. No build/pull occurred. [Current controlled evidence](../../docs/evidence/issue-45-pr02/report.md) is separate from historical full-recovery results. All live acceptance tasks remain open; publication and human review remain parent-owned.
Final P3 checks passed: 2/2 current controlled tests, two Node syntax checks, 18 relative links, five shell blocks parsed only, whitespace/privacy checks and a genuine offline rendered E2E screenshot. Protected original/full recovery and published first-stage hashes/status/HEAD are unchanged. No actual CA completion, hosted CI or human approval is inferred; the tracker mirror remains pending.

## PR #425 review correction checkpoint

- [x] **MCP45-P3-R1 — Validate raw discovery tool entries**: PR #425 (`efb8446` over `73fd51a`); fix [review finding](https://github.com/creep1ng/sre-agent/pull/425#discussion_r4140568933) by validating raw `tools` cardinality and each expected string ID before normalization. Fresh HTTP/CLI scenarios observed RED (malformed extra entry accepted; `0 !== 1`), minimal fix GREEN 2/2, syntax checks passed on Node v22.14.0. Updated [current report](../../docs/evidence/issue-45-pr02/report.md) and exact-source screenshot; current diff is 392 text additions+deletions plus one PNG file, within 400. No CA1–CA8 closes; parent owns mirror/publication. Initial Docker denial was retried with authorized escalation; original recovery roots stayed untouched.

## Current preview-helper prerequisite (2026-09-30)

- Base/main: `5b6109bd2c8100455136cf12ce91c52830833c7f`; branch: `codex/issue-45-00-preview`. This independently useful preview helper precedes the foundation documentation PR #424; parent owns the documented stacked-to-main restack and the later discovery PR #425 correction.
- The current issue-specific task identity remains this file. Preserve every dated P1/P2/P3/P3-R1 result above; they describe earlier candidates and do not imply their implementation is present in this main-based helper branch.
- Live/current parent facts: PR #424 still has two open review corrections (repeatable Markdown→HTML/PNG proof and accurate TDD provenance). PR #425 has a fresh source correction at `9eb3eb3dd3d55facfcd28d35490f85fedb95ac10`; hosted CI run 36669373324 passed all eight jobs, governance and reconciliation. CI, the preview screenshot, and requested review are not user approval.
- Scope: render a supplied tracked Markdown document with the small syntax subset needed by the preview (`docs/pr-evidence.md`), into an offline local HTML template with source SHA; capture its real browser rendering in a pinned, networkless, sandboxed Chromium container. No general Markdown dependency/parser, service, public hosting, arbitrary URL fetch, or issue CA claim.

- [ ] **MCP45-V1 — Write first-failing CLI coverage**: test valid Markdown/template/output, source-hash footer, escaping of raw HTML, bounded supported syntax (headings, paragraphs, lists, tables, links, inline code/strong and fenced code), and nonzero missing-input/template errors. Observe RED before writing the helper.
- [ ] **MCP45-V2 — Implement the reusable preview helper**: standard-library Node CLI accepts explicit input/template/output paths; emits offline HTML and source SHA; rejects bad arguments/read failures/unresolved template placeholders; does not fetch links, scripts, images or fonts.
- [ ] **MCP45-V3 — Verify actual rendered output safely**: run focused CLI E2E plus Chromium screenshot inside the cached pinned Playwright image, with docs/template/helper read-only, output isolated under `/tmp`, no network, no secrets and sandbox intact. Inspect the actual PNG; record browser version, dimensions, SHA-256 and exact command.
- [ ] **MCP45-V4 — Record preview evidence and current scope**: concise report maps this helper to rendered-artifact evidence only, includes exact base/tested SHA/image/commands and observed expected/actual result, sanitizer check, rollback, and explicit non-claims. Preserve the full issue tracker and keep CA1–CA8/P4–P10 pending.


## Frozen preview-helper checkpoint

Terminal partial: CLI E2E observed RED 3/3 before implementation and GREEN 3/3 after (Node v24.20.0), plus syntax and actual docs/pr-evidence.md HTML rendering. Test coverage does not yet demonstrate every V1 failure case; V1/V2 remain unchecked against their full wording. Chromium capture exited 133 with generic `No usable sandbox!`; the cause is unattributed. No sandbox bypass or further capture attempt, PNG, report, commit, push or PR exists. V3/V4 remain pending. Four new files totaled 387 additions before this checkpoint; remeasure before publication and preserve all history. Parent must resolve the real rendered-proof gap; P4–P10 safe local work remains available.

## Current P4 query stage (2026-09-30)

Candidate: `codex/issue-45-03-queries`, base `9eb3eb3dd3d55facfcd28d35490f85fedb95ac10` (PR #425); exclusive query worktree. Preview-helper checkpoints above describe a separate frozen main-based candidate; no renderer is installed in this branch. GitHub Projects refreshed: issue #45 OPEN / Project #8 Todo. P3 current CI passed all eight jobs; human review remains pending.

Authorized scope: P4 only — fixed public-contract metric/Lucene log queries through the gateway; safe source/window/count/error summaries, controlled failure/empty/redirect coverage. No restricted invocation, witness reconciliation, producer repair, boundary probing, cycle capture or live acceptance. Preserve every P3 malformed-entry and sanitization check. Effective test-first mode comes from the issue handoff/workflow, not an asserted repository AGENTS toggle. Existing cached Node22.14 harness lane; RED before source implementation, GREEN then proportional refactor/checks. Keep measured whole PR additions+deletions <=400 without history/tests/format deletion.

- [x] **MCP45-P4-A — Observe query HTTP/CLI RED**: permanent CLI tests asserted fixed request paths/payloads, safe summaries, empty/timeout failures, redirects, no leaked fixture secrets and invalid-config zero network. The networkless cached runner showed RED (0/2 passed before source).
- [x] **MCP45-P4-B — Implement governed smoke queries**: added bounded POST transport with 35-second timeout and redirect rejection, plus fixed metric/Lucene query and allowlisted summaries; retained `runDiscovery` export name and invalid-config zero-network behavior. Harness GREEN 2/2.
- [ ] **MCP45-P4-C — Verify and record evidence**: current full HTTP/CLI GREEN, syntax/structure/privacy/diff checks; exact candidate report and genuine rendered evidence, independent check and hosted CI/publication parent-owned. CA1–CA8 remain open without real environment proof.

P4 local evidence: observed RED and GREEN in the cached Node 22.14 harness using an explicitly networkless loopback Compose overlay; direct `docker run --network none` reproduction also passed 2/2. The report records exact source/test SHA-256 and distinguishes controlled fixtures from real service evidence. A genuine screenshot was not captured in this scope, so P4-C and publication readiness remain pending.

Parent verification checkpoint: current source `d6ca8ffd15ce609f3cc8a6f56f907cfba0076df2c76cdd7151fcb88f0cd35a0a` / test `9830e2a59a0c0e47ae1d58d7c1f75e07a45ca7a3d08250d396822537ff0a1221` passed 2/2 in the exact public networkless Docker command, with both hashes unchanged. Earlier independent verification used a pre-formatting test revision and remains historical. Source implementation is locally verified; P4-C/publication remains pending genuine screenshot, hosted CI and human review.

Final label-only correction names tests/output as gateway smoke queries rather than invocation-free discovery. Parent exact current Docker run again passed 2/2; source hash unchanged, final test SHA-256 `ae917a52057545eb823ca25d354b39284da2418c2ca79725dd9d9ac71bdfb0d7`. The earlier hashes above retain their historical scope. Local commit is a recovery anchor, not publication/acceptance.

## Priority gateway-root review correction

At the original gateway-root correction checkpoint, candidate `codex/issue-45-gateway-root-path` was based on PR #425 `9eb3eb3dd3d55facfcd28d35490f85fedb95ac10`. Earlier P4 checkpoints describe local recovery commit `4c9697411e25d954d03d1afaaef7622d54422cad` (326 changed lines), not code installed in that discovery-based correction. P5 planning was started separately but no P5 source work is authorized until this routing finding is addressed. Fresh live Projects: issue #45 OPEN / #8 Todo; new unresolved [review](https://github.com/creep1ng/sre-agent/pull/425#discussion_r4140855307).

The configured gateway is documented as an origin; non-root paths currently pass validation then are silently discarded by url.origin. Reject unsupported non-root paths rather than silently changing the configured route. Preserve root URLs, discovery behavior, malformed-entry fix and 35-second/no-redirect budget. No producer/cloud/runtime changes. This is a small cohesive corrective unit; keep all task history, full diff<=400 and real evidence requirements. At that checkpoint, parent owned later bottom-up propagation into local P4/P5 and publication; no restack had occurred.

- [x] **MCP45-URL-R1 — Observe configured-path HTTP/CLI RED**: permanent CLI test first; cached networkless runner observed the non-root base path incorrectly returned status 0 instead of rejecting configuration.
- [x] **MCP45-URL-R2 — Reject unsupported gateway paths**: `validGatewayUrl` now accepts only root pathname; root and `/` both make the normal two discovery GETs, while `/mcp-gateway` and `/mcp-gateway/` fail before any HTTP. GREEN 2/2, syntax and diff checks passed.
- [ ] **MCP45-URL-R3 — Bind correction proof and propagate**: concise [root-correction report](../../docs/evidence/issue-45-gateway-root/report.md)/current hashes prepared; genuine screenshot, independent review, hosted CI and parent-owned publication remain pending.

URL correction test evidence is in `/tmp/issue45-gateway-root-evidence/url-red.log` and `url-green.log`; no screenshot was attempted in this slice. The controlled fix does not close CA1–CA8.

Gateway-root parent checkpoint: exact current source/test hashes in the correction report independently passed 2/2 using the networkless cached Docker command, unchanged before/after. Public PR #425 remains draft at unfixed `9eb3eb3`; source finding was acknowledged in reply [4141205759](https://github.com/creep1ng/sre-agent/pull/425#discussion_r4141205759). No review thread was resolved; propagation, screenshot/publication and hosted CI remain pending.

## P4 restacked validation checkpoint

Parent local root correction `f23e9a01f01b0ef85c3a7a43a134e413af0a87dc` is now the base for this P4 candidate; P4 remains the current stage and all root/P4 checkpoints above remain intact. The first combined-suite run failed at the root-slash case because the P4 fixture still held the deliberately empty log response from the preceding empty-result scenario. Restoring the successful fixture before root-slash validation corrected the test adapter; no P4 or root source behavior changed. Current cached networkless suite passed 2/2, syntax and whitespace checks passed, and exact hashes/command are in the updated [P4 report](../../docs/evidence/issue-45-pr03/report.md). A fresh screenshot for this combined test hash, independent review, hosted CI, task mirror refresh, public propagation and human acceptance remain parent-owned; CA1–CA8 stay open.


## Root correction publication checkpoint

Current source is the discovery-based root correction; P4 restack `265c9dafe3182c01522db99369b70735467468f9` above describes a separate local child, not installed P4 code here. Real parent-controlled screenshot is now attached in [the correction report](../../docs/evidence/issue-45-gateway-root/report.md), SHA-256 `56bc41f324877a53ab9dc1ecc1bb3a4fb7a279003550f0d314c3969115133587`. Host sandboxed Chromium rendered actual Docker output and assertions; source/test hashes are unchanged from independently verified `f23e9a01`. This does not resolve PR424's containerized Markdown-preview finding. Public binding, current hosted CI and human review remain pending; URL-R3 stays unchecked. Public425 is draft at unchanged9eb3 and its own source remains unfixed.


## P4 restack onto published PR #430 parent (2026-09-30)

The root correction was published as ready PR #430 at head `73cd29e58288329a7b2b0fd9eaa816ecace26438`, based on PR #425 at `9eb3eb3dd3d55facfcd28d35490f85fedb95ac10`; its 140 additions and 11 deletions are within the documented limit. The P4 branch was first rebased onto that published head as local commit `c66dd887d2f7a5700f7992cf697e52ccecb4e197`, preserving the root correction history and the complete P4 query history above. PR #430 hosted CI run `36678518934` was still running at this checkpoint; governance/reconciliation and GitGuardian checks passed, and requested review is not acceptance. P4 remained local; publication and its screenshot are parent-owned. The P4 four-request query behavior and the restored successful log fixture before root-slash validation remain intact. CA1–CA8 remain open; real service evidence and human acceptance remain pending.


## Final P4 local restack after PR #430 report correction (2026-09-30)

Parent published the report-only correction as PR #430 head `bb384f08ed65b6429b2d5d4175c035a541f4686e`, directly atop `73cd29e58288329a7b2b0fd9eaa816ecace26438`; it changes eight report lines and deletes one. The P4 commit was replayed onto that current parent. A local backup ref preserves the intermediate P4 commit `c66dd887d2f7a5700f7992cf697e52ccecb4e197`. P4 source/test SHA-256 remain `e75fcf678255cd031d05b98691ffc82f12aeeb646e0939546ae969bfb8bfca36` / `73f08fe9a43d480ca61674b1bc8deed096490c85d8926a1bf9d6df8197c922e9`. The repeated exact cached Node 22.14.0 Docker command passed 2/2; observed controlled output remained `status=pending` for missing upstream witness, with 12 gateway requests and zero alternate-server calls (`/tmp/issue45-p4-final-restack-evidence/docker-test-final.log`). Both changed JavaScript files passed `node --check`; `git diff --check` passed. The 504 fixture verifies bounded `upstream_timeout` normalization only; it does not exercise actual 35-second client-budget expiry. No screenshot, live Gateway/MCP, upstream counter, hosted P4 check, or human acceptance is claimed. Parent's new PR #430 CI remained pending at this checkpoint; CA1–CA8 remain open.

## P4 current evidence attachment

Parent exact committed `fac4831` Docker rerun passed2/2 with unchanged hashes. Genuine [P4 PNG](../../docs/evidence/issue-45-pr03/queries.png), SHA-256 `ff6bc808650b42bca8d239a4c41612df6a71fffd347513b6e32d9857498b6448`, now records observed queries, safe summaries and actual assertions. P4-C remains unchecked pending publication/hosted CI; requested human review and real CA1–CA8 remain open.

## Current P5 known-ID denial stage (2026-09-30)

Fresh owned branch `codex/issue-45-04-known-id-denial`, base published P4 `c840ed76f8e16f123e1d33127ff7798e5de49597` / PR431. Old P5 planning at `4c969741` remains untouched in its separate dirty worktree. Latest live Projects: issue45 OPEN, Project8 midnight.agent Todo. Parent430 bb384 current CI36679193203 passed all8 jobs; human review and parent425 source integration remain pending.

Authorized scope: restricted known-ID Prometheus POST must be the first request, before all discovery; retain P4 fixed query/discovery behavior, root-only validation, malformed-entry/privacy/redirect checks. Report only bounded status/code/safe UUID and upstream_delta:null. Controlled success stays pending; no P6 witness option, actual upstream-zero assertion, CA2 closure, producer/runtime/cloud changes. Strict test-first ON comes from the issue handoff/OPERATING-RULES, not a repository toggle. Runner is the cached Node22.14 networkless Docker HTTP/CLI test documented in P4; no build/pull, secrets, API/DB/demo or host package manager.

- [x] **MCP45-P5-A — Observe known-ID-first denial RED**: permanent HTTP/CLI test first; assert restricted POST is request one, exact public route/payload, safe denial UUID distinct from discovery UUID, null upstream_delta and pending success. Cover wrong status/code/missing or invalid UUID fail-closed without output leakage; cached networkless Docker run observed 0/2 before source implementation.
- [x] **MCP45-P5-B — Implement bounded denial summary**: prepend restricted POST to unchanged four-request P4 sequence and allowlist denial output; never convert 403 or fixture counts into upstream-counter proof. Preserve existing public boundaries and 35-second/no-redirect budget; exact cached networkless Docker suite passed 2/2.
- [x] **MCP45-P5-C — Verify and bind evidence**: exact committed source/test hashes passed cached Docker 2/2 and Node syntax checks; the actual P5 PNG, full task mirror, PR #432 publication, and hosted CI passed at that checkpoint. Reopened after review finding 4141925985: the published P5 source accepts equal valid denial/discovery UUIDs and can still report pending. Parent moved PR #432 to draft; P5 source correction remains pending. CA1–CA8 and human acceptance remain open.

P5 local evidence: `/tmp/issue45-p5-evidence/red.log` records pre-source RED (0/2) on Node 22.14.0; `/tmp/issue45-p5-evidence/green.log` records current controlled GREEN (2/2). Source/test SHA-256 are recorded in `docs/evidence/issue-45-pr04/report.md`. The controlled success remains `pending` with `upstream_delta: null`; no zero-call or CA2 claim is made. Parent owns screenshot, task mirror, independent verification, commit, publication and hosted P5 CI. P4 hosted CI run `36680206014` passed all eight jobs per parent checkpoint; human acceptance and CA1–CA8 remain open.

Next step: parent completes P5-C evidence/publication readiness. New scope forecast is not a measured final diff; measure the complete PR against `c840ed76f8e16f123e1d33127ff7798e5de49597`, including parent-owned PNG, and preserve all task history without cosmetic trimming.

## P5 parent committed proof checkpoint

Parent committed source/tests/docs as `638942a4aa6278ae4c32bb61e72d214aaffe5e28`, then exact cached networkless Docker syntax/E2E passed2/2 with unchanged report hashes. [Actual P5 PNG](../../docs/evidence/issue-45-pr04/known-id.png), SHA-256 `ff510c21f80a58a4e57db727d3bf58d3c9144d2e1a7092d7b947b00280b21edb`, binds observed denied-summary and first-request assertions. P5-C remains open for current publication/hosted CI; real CA1–CA8 and human acceptance remain pending.

Latest P5 checkpoint: PR #432 was published at `0022a2a7373bba3309a0c82caf2e0e6ab7b9fe97`; hosted CI run `36683005655` completed with all eight jobs passing. Governance, reconciliation and GitGuardian checks passed; the current body and full task mirror were read back. P5-C controlled-delivery proof is complete; no human acceptance or CA1–CA8 closure is claimed.

Review correction: finding [4141925985](https://github.com/creep1ng/sre-agent/pull/432#discussion_r4141925985) shows the P5 producer-side CLI does not reject a repeated valid UUID; its report can remain pending. PR #432 is now draft. P6's offline validator independently rejects duplicate IDs, but does not repair or replace that P5 check. P5-C is reopened until the parent-owned source correction is verified.

Parent checkpoint: P5 was published as PR #432 at `0022a2a7373bba3309a0c82caf2e0e6ab7b9fe97`; hosted CI run `36683005655` completed with all eight jobs passing, and governance, reconciliation and GitGuardian checks passed. Current PR body and full task mirror were read back. This completes P5 controlled delivery evidence only; human acceptance and real CA1–CA8 remain pending.

## Current P6 offline witness stage (2026-09-30)

Fresh owned branch `codex/issue-45-05-witness`, base P5 PR432 `0022a2a7373bba3309a0c82caf2e0e6ab7b9fe97`. P5 current hosted CI36683005655 is still running at this checkpoint; P5 fixture proof and published source-bound PNG are not real CA2 evidence. Old worktrees and full task history remain unchanged.

Scope: offline `--reconcile <report> --witness <file>` dispatch before any live probe. Validate actual P5 query-smoke schema/phase and complete safe pending report, normalize allowlisted fields, correlate a separately operator-validated upstream-counter UUID with the known-ID denial, require nonnegative safe-integer monotonic counters and zero delta to pass. Reject generic audit/event witnesses, including known audit_events_total relabeled upstream-counter. Metadata validation cannot independently establish the source's true semantics; real operator/counter provenance and CA2 stay pending. No network, actual counter capture, producer/runtime/cloud changes or P7 behavior.

- [x] **MCP45-P6-A — Observe offline CLI RED**: permanent E2E first for matching zero witness, invalid report/schema/phase/explicit extra failures, generic/relabelled audit source, mismatched UUID, malformed/reversed/unsafe/nonzero counters and bounded malformed/missing/oversized files/arguments. Observed RED 1/2 before source edits; assert zero gateway calls and no marker leakage.
- [x] **MCP45-P6-B — Implement safe P5 report/witness adapter**: adapted bounded recovery validators to current schema/phase, preserving denied/restricted-discovery IDs, positive query counts/source/windows and null error fields. Normalizes only validated safe fields; rejects the known generic `audit_events_total` source even if mislabeled; no audit-event-to-upstream promotion or forged pending failure suppression. Exact cached Docker GREEN 2/2.
- [ ] **MCP45-P6-C — Verify and bind offline evidence**: exact cached Node22.14 networkless Docker GREEN, syntax/diff/privacy/hashes, report and genuine screenshot; parent owns mirror/publication/hosted CI and human request. Strict test-first ON is from the issue handoff, not AGENTS. Measure full per-base <=400 additions+deletions without history/test/comment/format trimming; forecast320–390 is not a final diff.

P6 local proof: `/tmp/issue45-p6-evidence/red.log` records the pre-source RED; `/tmp/issue45-p6-evidence/green.log` records the exact cached Node 22.14 networkless Docker GREEN (2/2). Current source/test SHA-256 and offline-only limitations are recorded in `docs/evidence/issue-45-pr05/report.md`. The controlled fixture witness is synthetic and does not close CA2.

Next step: parent completes P6-C screenshot, independent verification, full mirror, publication and hosted CI. Keep all CA1–CA8 and human acceptance open. Preserve all historical checkpoints above.

## Priority P5 duplicate-ID correction (2026-09-30)

Current exclusive branch `codex/issue-45-04-known-id-denial`, HEAD `0022a2a7373bba3309a0c82caf2e0e6ab7b9fe97`, base P4 `c840ed76f8e16f123e1d33127ff7798e5de49597`. Live Project #8 refreshed: issue #45 Todo / Sprint 4. PR #432 is draft; review [4141925985](https://github.com/creep1ng/sre-agent/pull/432#discussion_r4141925985) is source-confirmed and unresolved. Previous green CI does not cover repeated IDs.

Reconciled the complete P6 tracker history into this parent document; P6 code/report remain only in its separate clean local child `6f6f9569419aaa8eb261bf32dbefcc6b0948b2c6`, not in this candidate. P6 publication is held. Historical dated scope and checkpoints above are preserved, not current authorization or proof.

- [x] **MCP45-P5-ID-R1 — Observe duplicate UUID RED**: permanent actual HTTP/CLI fixture uses the same valid UUID for denial and discovery; assert exit 1, sanitized fail report, unchanged five-request order and null upstream delta. Exact numeric duplicate RED observed against the original P5 source (expected exit 1, got 0). This RED did not test case variants; a genuine alphabetic case-variant was added as post-fix validation.
- [x] **MCP45-P5-ID-R2 — Enforce distinct IDs**: minimal validated-ID comparison rejects equal validated UUIDs case-insensitively as `restricted_request_ids_not_distinct`, without changing routes, query payloads, privacy fields or claiming actual upstream zero. Exact cached networkless Docker GREEN 2/2 and both Node syntax checks passed. Captures: `/tmp/issue45-p5-id-repair-evidence/red.log` and `/tmp/issue45-p5-id-repair-evidence/final-green.log`.
- [x] **MCP45-P5-ID-R3 — Refresh correction delivery proof**: parent independent exact-current Docker checks, source/test hashes, genuine fresh screenshot and report, <=400 current-base delta, full lossless mirror, owned fast-forward publication/current CI and review reply. Keep P5-C open until observed; no automatic resolution/acceptance.

Next step: parent owns R3 independent verification, fresh screenshot, report/task mirror, commit/publication/current CI, and later P6 restack. This local candidate is not committed or published. Exact runner is the existing cached Node22.14 networkless Docker lane in the P5 report; no build/pull, credentials, API/database or demo start. CA1–CA8, CA2 proof and human acceptance remain open.

## P5 correction parent committed evidence checkpoint

Exact `db7eef3cbfdd2090519145a73b5437e8069fd45c` independently passed cached Docker syntax/HTTP-CLI 2/2 with source `9af21e534a7d60abf3a0ecf3bb3b2ec60d7fb93064ee27fc770224d2db5baa01` and test `7346b55130ffec319789576a3e49265fda7a7e0d53725e3c71efc648138127c9` unchanged. Real [fresh correction PNG](../../docs/evidence/issue-45-pr04/known-id-corrected.png), SHA-256 `3fc38417cc40fb56c410bfc13768f09ffa457076be3acfe4b7b989f97d288063`, was visually inspected. R3/P5-C remain pending publication/current hosted CI/human request; P6 remains frozen local child. No real CA closed.

## P5 corrected public candidate verification checkpoint

Current PR #432 head `98746fbdea6bd7c07e972225f941b99f2ea601ce`, parent P4 `c840ed76f8e16f123e1d33127ff7798e5de49597`, is ready for requested human review, not approved. Exact hosted CI `36688732677` completed all eight jobs successfully; governance/reconciliation and GitGuardian passed. Parent watch exited 0 and exact run API confirmed every job. Public correction PNG ContentsAPI bytes/hash and full body matched local evidence. Current-base size is 272 additions + 27 deletions = 299. Reply [4142394608](https://github.com/creep1ng/sre-agent/pull/432#discussion_r4142394608) records the correction without resolving the thread. R3/P5-C controlled-delivery checks are now observed complete; all dated pending/reopened notes above retain their historical scope. Human acceptance and real CA1–CA8 remain open. This tracker-only checkpoint is local, pending repository commit; published source/report/PNG remain bound to the verified candidate.

## P6 recovery restack and ID consistency tasks

Parent authorizes sole Luna high writer to restack only owned local `codex/issue-45-05-witness` from old base `0022a2a7373bba3309a0c82caf2e0e6ab7b9fe97` onto verified P5 `98746fbdea6bd7c07e972225f941b99f2ea601ce`. Preserve local backup ref to original `6f6f9569419aaa8eb261bf32dbefcc6b0948b2c6` first; no push/publication or other worktree changes. Reconcile this full parent tracker with original P6 history without deletion. Parent source inspection found P6 offline report validator compares UUID strings case-sensitively despite accepting uppercase UUID syntax; verify genuine alphabetic same-ID case with permanent HTTP/CLI offline RED before changing that guard. This is a consumer-validator correction, not producer/runtime work or live acceptance.

- [x] **MCP45-P6-R1 — Restack preserved offline adapter**: backup ref `codex/issue-45-05-witness-before-p5-id-restack` preserves original P6 commit `6f6f9569419aaa8eb261bf32dbefcc6b0948b2c6`; local-only rebase replayed P6 onto P5 `98746fbdea6bd7c07e972225f941b99f2ea601ce`. Task/test conflicts were reconciled preserving the full parent/P6 history, P5 duplicate-ID cases, and existing offline tests. No reset/stash/skip or foreign worktree write.
- [x] **MCP45-P6-ID-R1 — Verify offline UUID identity gap**: permanent offline CLI case uses a saved valid pending report with alphabetic denial/discovery IDs differing only by case and a valid counter witness matching the denial ID; expected exit 1 / `probe_report_invalid`, observed exit 0 / pass against restacked source. The case includes an unchanged gateway-call assertion and sanitized failure expectation. This is the observed RED; no source fix was made.
- [x] **MCP45-P6-ID-R2 — Enforce normalized offline distinct IDs**: case-insensitive denial/discovery identity is enforced; witness correlation retains exact request-ID matching. Preserve allowlist/count/schema/file bounds, counter-only semantics, live P5 guard and no-network dispatch. Exact cached Docker GREEN 2/2 and syntax/diff checks passed; parent owns independent checks/media/commit/publication/current CI.

Keep P6-ID-R2 and P6-C open. The current P5 PR also has a new parent-reported `retryable: false` contract gap; parent has paused P6 source edits/publication until that correction is handled. Exact RED capture: `/tmp/issue45-p6-restack-evidence/red.log`; it shows the offline same-UUID case accepted with `status:pass`, while existing P5 exact and alphabetic duplicate-ID guards and P6 zero-delta positive reconciliation still execute. This local recovery anchor is deliberately not ready for publication. The full parent tracker preserves earlier P6 history. Strict test-first is from the issue handoff; exact cached Node22.14 networkless Docker runner. No history/test/comment/format trimming or claims of CA2 proof; CA1–CA8 and human acceptance remain open.

## P5 invocation retryable review correction

Live [finding4142436803](https://github.com/creep1ng/sre-agent/pull/432#discussion_r4142436803) matches current `98746fb` source: invocation denial omits retryable capture/validation, happy fixture omits the field, but MCP1.0.0 public_errors requires 403/resource_unavailable/retryable:false. Parent marked #432 draft and acknowledged [4142607486](https://github.com/creep1ng/sre-agent/pull/432#discussion_r4142607486); current8green CI does not exercise malformed invocation retryable. P5-C reopened for this distinct new contract defect. P6 local `bc11898b` is clean, deliberately failing its new offline UUID test; no offline source fix/publication. Original backup ref preserves `6f6f956`.

- [x] **MCP45-P5-RET-R1 — Observe invocation retryable RED**: permanent actual HTTP/CLI fixture sets valid denial retryable:false; expect normalized denied.retryable:false, true/missing/nonboolean/null fail closed and preserve five requests/privacy/null upstream delta. RED observed before source edits: CLI report omitted required `retryable:false`. Capture: `/tmp/issue45-p5-retryable-evidence/red.log`.
- [x] **MCP45-P5-RET-R2 — Enforce denial retryable contract**: capture only boolean or null, require false in invocation-denial guard; preserve UUID distinctness and all P4 behavior. Exact cached Docker GREEN 2/2; syntax/diff and current report hashes recorded in the report. Capture: `/tmp/issue45-p5-retryable-evidence/green.log`.
- [x] **MCP45-P5-RET-R3 — Refresh current delivery proof**: parent independent exact-current tests, fresh real screenshot, report/full mirror, <=400 total current-base delta, owned commit/publication/CI/review reply. Human acceptance and real CA1–CA8 remain open.

Sole Luna high writer repairs only P5 source/test/report and this full tracker; no P6/producers/runtime/Compose/dependencies/cloud changes. Strict test-first runner unchanged cached Node22.14 networkless Docker. Parent owns Git/PNG/publication/current CI. Keep all dated history; no size-only trimming.

Observed P5 retryable correction candidate: source `5aecebdcbdb4601296f8969a9832e7b51ed38280baa38ab4f7c3a01987ae6e00`; test `0429268af26e224df3b3b03a9c91942df846af23e6001e36092c543507703a4d`. Valid `retryable:false` is now summarized; true, missing, null, and string values fail with `restricted_invocation_not_denied`, while the five-request order, distinct IDs, privacy checks and `upstream_delta:null` remain asserted. P5-RET-R3 and P5-C remain pending parent independent verification, screenshot, mirror, commit/publication/current CI; P6 remains frozen, deliberately RED, and unmodified.

## P5 retryable parent committed evidence checkpoint

Exact `c2500771560c8e89b3e4d4656547ab8871146250` independently passed cached Docker syntax and HTTP/CLI2/2 with unchanged source5aecebdc/test0429268a. Real [fresh retryable PNG](../../docs/evidence/issue-45-pr04/known-id-retryable.png),SHA-256 `71ba7b1fc7b5ee7e9f302a8c30a45797b72974b3acc167295e6ad50bedb915b2`, visually inspected/sanitized. RET-R3/P5-C pending publication/currentCI; P6bc118 deliberately RED and frozen. All real CA1–CA8/human acceptance open.

## P5 retryable current hosted proof and P6 next step

Current PR #432 `9cdf424573b35216702787af6e45be4172757b9b` ready, 351 additions + 27 deletions =378, tested `c2500771560c8e89b3e4d4656547ab8871146250`. Exact CI `36693158406` all8 terminal success; watch exit0 and exactAPI verified, governance/reconciliation/GitGuardian pass. Current public PNG ContentsAPI bytes/hash and body readback exact; reply [4142791153](https://github.com/creep1ng/sre-agent/pull/432#discussion_r4142791153) records correction without resolving thread. RET-R3/P5-C controlled delivery complete; requested human review and all real CA1–CA8 open. This tracker-only checkpoint is local pending repository commit; no published source/evidence changes.

Historical next-step note at that checkpoint: preserve the frozen P6 backup before restacking onto P5, retain the offline UUID RED, and adapt to P5 retryable semantics.
- [x] **MCP45-P6-RET-R1 — Verify current denial schema offline**: test-first offline RED observed because accepted normalized report omitted `denied.retryable:false` (undefined vs false); capture `/tmp/issue45-p6-current-evidence/red.log`. The test was added before source edits.
- [x] **MCP45-P6-RET-R2 — Preserve nonretryable denial semantics**: require and retain exactly `denied.retryable:false`; true/missing/null/string fail closed with `probe_report_invalid`. Cached Docker GREEN 2/2, syntax and diff checks passed; capture `/tmp/issue45-p6-current-evidence/green.log`. No counter provenance or actual CA2 claim.


## P6 current local retryable/UUID candidate checkpoint (2026-09-30)

Backup ref `codex/issue-45-05-witness-before-retryable-restack` preserves P6 HEAD `bc11898b5b1a9b9437b0b1b477400e351eabdc5c`; original pre-restack backup `codex/issue-45-05-witness-before-p5-id-restack` remains `6f6f9569419aaa8eb261bf32dbefcc6b0948b2c6`. The owned P6 commit is locally restacked onto P5 PR #432 ready head `9cdf424573b35216702787af6e45be4172757b9b` as `1803790`; tracker conflict used the full parent-reconciled task and preserved P5 and P6 histories.

Observed retryable:false RED/GREEN. Parent found that the earlier witness-negative cases reused an invalid duplicate-ID report and stopped at `probe_report_invalid`; the fixture now restores a valid report and asserts each specific witness failure. Test-first RED showed case-variant witness/denial IDs were incorrectly accepted; exact-match correlation is restored. Final cached Docker GREEN 2/2 verifies each witness guard and keeps reconciliation offline. Source SHA-256 `06260e9cb35327f234ac40c880f838fd9398f43831c588eae7711de82dbf97cb`; test SHA-256 `29013ec083adab404f7531039105477a0e82eb5d6d19f371e82f5b099013a138`. Measured current-base delta versus `9cdf424573b35216702787af6e45be4172757b9b` is 363 additions + 17 deletions = 380 lines against P5 `9cdf424573b35216702787af6e45be4172757b9b`. Parent owns P6-C independent verification, current screenshot, mirror, final commit/publication/current CI; no claim of real counter/provenance or CA2/CA1–8 acceptance.

## P6 parent committed evidence checkpoint

Exact `afcc54680d50069acfaa0349bc08ba74232839c1` independently passed Docker syntax/HTTP-CLI2/2 with unchanged source06260e9c/test29013ec0. Actual [P6 PNG](../../docs/evidence/issue-45-pr05/offline-witness.png),SHA-256 `88c5787b707f6bad23e27961e87410652b9a5bee75cb868ccc29aa27b91df1cd`, visually inspected/sanitized. P6-C remains pending publication/currentCI; all real CAs/human acceptance open.

## P6 input-read and runbook review correction

Public4347cf7a6b remains source-unfixed/DRAFT after reviews4143234061/4143234075: readFile loads all bytes before16KiBcheck; runbook64–66 incorrectly says reconciliation unimplemented. Parent source-confirmed/ack4143288241. Current388publishedlines; preserve full history/tests, measure correction beforepublication, split cohesive units or obtain explicit maintainer exception if >400. No implicit exception. P6-C reopened; no realCAclosed.
- [x] **MCP45-P6-IO-R1 — Observe bounded-file CLI RED**: permanent CLI test creates a 1 GiB sparse report and requires exit 1 plus a small structured `probe_report_invalid`. Under the cached Node22.14 networkless Docker runner capped at 256 MiB memory/swap, the pre-fix CLI child closed with status `null` and no structured report; test runner exited 1 (2/3 passed). Capture: `/tmp/issue45-p6-current-evidence/io-red.log`. No source edits preceded RED.
- [x] **MCP45-P6-IO-R2 — Enforce pre-read bound and current stage docs**: loader uses `open` and a fixed 16,385-byte buffer, reads at most limit+1 through EOF, rejects oversized content before parse, and closes the handle. Same capped Docker GREEN 3/3; the sparse report failed safely with `probe_report_invalid` in 233 output bytes. Existing malformed/missing input, offline witness guards, retryable:false, 15-request sequence and zero alternate-server assertions remained green. Runbook now correctly identifies implemented P6 offline reconcile and states it does not capture counters or establish witness provenance/semantics. Source/test hashes and full-base diff recorded in the current checkpoint below.
- [ ] **MCP45-P6-IO-R3 — Bind corrective delivery proof**: parent independent current tests/realPNG/report/fullmirror, actualbase<=400 or explicit maintainer exception, owned publication/currentCI/humanrequest; preserve originalscope/allhistory.

## Accepted PR434 corrective size exception (2026-09-30)

User explicitly accepted the parent question permitting PR #434 to exceed 400 additions plus deletions for the coherent input-read bound, permanent behavioral test, runbook stage correction and current delivery proof. The pre-repair candidate measured 404 additions + 17 deletions = 421. This is a scoped maintainer exception, not blanket approval for future PRs or functional/human acceptance; no exception label is authorized. Resume IO-R1/R2/R3 with strict test-first and the existing cached networkless Node22.14 runner, adding a 256MiB memory/swap ceiling for the sparse-input case. All real CA1–CA8 remain open.

## Current P6 IO correction checkpoint (2026-09-30)

The parent-authorized exception remains limited to this current PR #434 input-read/test/runbook/current-proof correction. Base remains P5 `9cdf424573b35216702787af6e45be4172757b9b`; published PR434 head remains `7cf7a6b3303c1f928f1b2d78bc46ebde24c4f0e1` and the source finding is not yet published as fixed. Exact GREEN is `/tmp/issue45-p6-current-evidence/io-green.log`; test-first RED is `/tmp/issue45-p6-current-evidence/io-red.log`.

The RED run's prior shared log filenames accidentally overwrote raw retryable-schema captures: `/tmp/issue45-p6-current-evidence/red.log` and `green.log` now contain the IO correction runs. Those earlier raw bytes are unavailable and are not reconstructed. Earlier written checkpoint text is retained as historical documentation only; the separately named current IO captures remain available. No witness provenance/counter source validation, producer, network capture, real CA2, or CA1–CA8 closure is claimed.

Current source SHA-256 `8a9d926288b416157e041e3a84c4e075a65bec799dcd5af227af1fe5f9e61583`; test SHA-256 `c5e016a9f6445176ff0aa44d39bcac4347ff114da18e71ed027e0de57a161961`; full current-base text diff is 456 additions + 20 deletions = 476, within the user's exception only for this correction. Final syntax/full-suite log is `/tmp/issue45-p6-current-evidence/final-verification.log` (SHA-256 `d74f5a9ae8e052db5848b4eb074c914dd5710ce3d269080656bca4f728fab3fa`). Parent owns independent verification, genuine current screenshot, full mirror readback, commit/publication/current CI, and human review; P6-IO-R3 remains pending.

## P6 input-bound parent independent verification

Parent exact cached Node22.14 networkless Docker, memory/swap 256MiB, syntax and full CLI suite passed 3/3 (no skips). The 1GiB sparse report failed safely with probe_report_invalid in 233 bytes; existing 15 gateway requests / zero alternate calls remain asserted. Source8a9d9262/testc5e016a9 unchanged after verification. Current runbook stage text inspected against implemented dispatch. IO-R3 remains pending committed proof, fresh PNG, mirror/publication/current CI/human request. Capture: /tmp/issue45-p6-io-parent-evidence/parent-green.log.

## P6 bounded-read committed proof and fresh capture

Exact d4146e58b21fbbafd70c3d36f28ec884e2924e82 independently passed syntax/full Docker CLI3/3, memory/swap256MiB, no network/skips; unchanged source8a9d9262/testc5e016a9. Real [bounded-read PNG](../../docs/evidence/issue-45-pr05/offline-witness-bounded.png),1600×2000/340903bytes/SHAe22fab60b1bd66d2c835f1d97c9292adcfa7dcea01d49858322ca0d7e57f67af inspected/sanitized; historical PNG retained. IO-R3 remains pending publication/currentCI/human request, all real CAs open.

## P7-D service-name and direct-IP slice (2026-09-30)

Parent authorized a coherent split of the preserved P7 boundary candidate. This worktree covers only supplied service-name and direct-IP HTTP health targets on P6 base `529b2105a5f2ee841c804713b5e32b605edb965a`. Preserve the P6 rollback/current tracker sections above. The complete prior P7 candidate and its published-origin code/tests/docs remain in parent-owned commit `05970c1ddcf38ab3c0543000ffdaf5d5865abe7b` and backup ref `codex/issue-45-06-full-boundary-backup-20260930`; P7-E below retains that follow-up rather than dropping it.

- [x] **MCP45-P7-D-A — Observe service/IP behavior RED**: permanent HTTP/CLI tests were added before source edits for reachable responses, blocked targets, missing/invalid inventory, and non-followed redirects. Exact cached Node22.14 Docker on the untouched 529 source failed 0/4 tests: legacy exit 0 instead of required reachable exit 1 or unverified exit 2. Capture `/tmp/issue45-p7-service-ip-evidence/service-ip-red.log`, SHA-256 `65446b80f451a506c4e234a1bd8f00bdfa4e5a7af1a456fc20907669a6e9ddfa`.
- [x] **MCP45-P7-D-B — Implement supplied service/IP health checks**: fixed unauthenticated GET `/healthz`; bounded parsing of service name, port, and IP inventory; manual redirect handling and body cancellation; allowlisted summaries only. Any HTTP response, including redirect/error, fails; missing, invalid, or blocked targets remain unverified and cannot assert full isolation. Exact cached Docker tests pass service/IP 4/4 and unchanged gateway CLI 3/3; syntax checks pass.
- [ ] **MCP45-P7-D-C — Verify current slice**: cached networkless Node22.14 tests, existing gateway tests, syntax/diff/privacy checks, report and measured <=400 current-base additions+deletions. Parent owns independent verification, real screenshot, mirror, commit/publication/current CI and human request. No live topology proof is claimed.

## P7-E follow-up retained from complete P7 candidate

- [ ] **MCP45-P7-E — Verify published HTTP origins**: bounded safe parsing/probing/matching of explicitly supplied published origins, including userinfo/path/query/fragment rejection, remains a distinct cohesive follow-up. Its original permanent tests and docs are preserved in the parent-owned full P7 candidate/backup and must be carried into the future P7-E task; this slice does not claim to implement or verify published-port reachability.
- [ ] Preserve end-state CA4/CA5 evidence requirements: actual harness network inventory, proxy/admin checks, independently validated binding/topology and source of truth, no-provider-secret checks, plus real markers/behavior as required. Synthetic controlled fixtures and supplied-target health results are not complete isolation evidence. CA1–CA8 and human acceptance remain open.

P7-D strict test-first is ON from the issue handoff/OPERATING-RULES, not a repository toggle. Exact runner uses cached Node 22.14 image SHA `060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d`, `--pull never --network none`, 256 MiB memory/swap, and read-only tests/scripts/schemas mounts. The earlier 5-second helper timeout raced the legacy per-target five-second timeout and is inconclusive; this RED used a 20-second helper timeout and completed the old CLI. No Git or publication operation is authorized for this writer.

P7-D local source SHA-256 `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283`; test SHA-256 `205885029a70adda1e9cd424f87efe446db473790d7334e93ff077b3bf7514c6`. At this checkpoint, before restoring the preserved full-P7 historical sections below, the text delta against `529b2105a5f2ee841c804713b5e32b605edb965a` was 363 additions + 19 deletions = 382; screenshot excluded. P7-D-C remains pending parent independent verification, current screenshot/mirror, final count, commit/publication/current CI, and human request.

## Historical full-P7 candidate record (retained verbatim; not current P7-D status)

The following P7 entries are copied exactly from the prior full P7 tracker. Their D-A/D-B checkboxes and source/test claims refer only to the historical combined candidate `05970c1ddcf38ab3c0543000ffdaf5d5865abe7b`, not the current P7-D service/IP slice above. The current per-slice status and hashes above supersede those historical candidate states. P7-E work remains pending despite its completion inside that old combined candidate.
## P7 direct-target boundary slice (2026-09-30)

Route: delegated direct, sole Luna6 high writer. Owned branch codex/issue-45-06-boundary-direct on P6db4b009; unchanged stacked-to-main strategy. Scope: replace legacy raw-URL boundary output with supplied service-name/direct-IP/published-HTTP-endpoint GET /healthz reachability observations, no authentication/body output/redirect following, bounded input/timeout and safe allowlisted summaries only. No port scanning, discovery, topology probing, cloud/SSH, Compose/runtime/producer/dependency or foreign changes. Existing contract/gateway behavior unchanged. Current400-per-PR limit applies; PR434 exception does not extend here. Full scope is not narrowed: proxy/admin connect-only probes, independent host-binding/network witness, no provider-token delivery, complete marker surfaces and real harness execution remain later required work, not assumed satisfied.

Current source evidence: legacy demo_mcp_probe.mjs is17lines and prints raw targets/error details then falsely claims isolation when missing IP/bindings. Raw recovery provides reusable safe supplied-target parsers/tests but wholeP7 forecast383beforeevidence is oversized; use coherent direct-target slice followed by proxy/admin slice, preserving all final criteria. The direct-only CLI must never claim total isolation/pass: reachable direct path is fail/exit1; blocked or missing/invalid inventory remains unverified/exit2 with supplied-targets-only coverage and explicit pending full boundary work. Exclude URL/IP/ports, bodies, errors and token/proxy secrets from output. Invalid targets must not be contacted; bound lists and accept only stated direct target forms. Fixed /healthz and redirect manual; no alternative request paths. No live environment evidence available.

TDD strict ON from issue handoff/OPERATING-RULES; runner cachedNode22.14 image060b50ea networknone/pullnever, source/tests/schema read-only; exactDocker command recorded in per-slice report. Testfirst permanent HTTP/CLI behavior RED, then implementation, GREEN/refactor; preserve all gateway tests. Forecast215–300text includingtest/docs/report/task; measureactual<=400 withoutcodegolf/history/testdeletion.
- [x] **MCP45-P7-D-A — Observe direct boundary CLI RED**: permanent HTTP/CLI tests were written before source. After extending the child deadline to20s, isolated exact base source `356f59d75536541790591d4fd3cd2cea60bfef2bbbc1dffabddb63782f488910` completed with exit0 for missing/blocked/invalid inventory where required exit2 and did not implement the reachable-target exit1 contract. RED 0/5; `/tmp/issue45-p7-direct-evidence/direct-red-completed.log`. Initial 5s `direct-red.log` remains inconclusive only.
- [x] **MCP45-P7-D-B — Implement safe direct boundary observations**: bounded DNS/IP/published-origin parsing and at most16 targets; unauthenticated fixed `/healthz` GET/manual redirects/body cancellation; safe `{kind,status,http_status}` summaries. Reachable503/302 fail exit1; blocked/missing/invalid remain `unverified` exit2 and full boundary pending. Direct GREEN5/5; existing gateway tests3/3; syntax/diff checks pass. Runbook/report updated. No real isolation or CA4/CA5 proof claimed.
- [ ] **MCP45-P7-D-C — Bind verified direct-stage delivery**: parent current independent Docker checks, exactSHA/hashes/realPNG/fullmirror/per-base<=400, ownedPR/currentCI/human request. All real CAs remainopen until actualenvironment evidence.

## P7 test deadline correction and P6 rollback checkpoint

Initial P7 direct-red.log captured only child kills at the test helper5s deadline, potentially racing the legacy5s fetch budget; it is preserved as inconclusive, not completed-behavior RED. P7 source remains unchanged. Extend the permanent test helper to20s, then observe actual legacy completion/structured-contract failure before source implementation. P6 source-confirmed rollback review4144076795 is mechanically corrected in parent15eec333cfdb6e0ab5a7e926f5f4b7d7c8fa33ae (P6 offline rollback preservesP5 guards); exact cached Docker3/3 passed. Prior db4CI36707970552all8success; newP6doc/media/publication/currentCI pending. Parent will propagate only final ownedP6 tip after P7 candidate is safely committed; no restack of dirty work, no reset/stash.

## Parent P7 controlled verification and cohesive split checkpoint (2026-09-30)

Parent independently observed frozen full candidate syntax and 8/8 (direct5 plus gateway3) in cached Node22.14 Docker with networknone and256MiB; `/tmp/issue45-p7-direct-parent-evidence/raw-green.log`. Source `edb4ceaecb457b5393d400b3743b74c396a3beaa8f2b422a032b99cea7e0e5a6`, test `7ad77165f40eca8175697b23887fb4e87362c624a8a68e44d3a6f286592f11d6`. Raw candidate was406 lines before this recovery checkpoint, not the older403 report count. It must not be published as one PR. Preserve the full candidate via local commit/backup ref before splitting into P7-D service-name/direct-IP and P7-E published origins with corresponding permanent tests/docs/evidence. Both retain supplied-targets-only/unverified semantics and full final criteria; no exception transfer, size trimming, history/test deletion or codegolf. P7-D-C remains pending. P6 prior406 CI36710332171 passed all8; new529 tracker-only CI36712710854 remains pending, no old-CI substitution. Review reply4144379416 leaves human thread open.

## Current P7-D verification after historical recovery

The active P7-D candidate remains on base `529b2105a5f2ee841c804713b5e32b605edb965a`; source `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283` and tests `205885029a70adda1e9cd424f87efe446db473790d7334e93ff077b3bf7514c6` are unchanged. Parent independently passed the cached Docker service/IP and gateway suites 7/7 with four syntax checks and no skips (`/tmp/issue45-p7-service-ip-parent-evidence/raw-green.log`). Exact-base P6 hosted CI `36712710854` is terminal all-eight success; P7 has not been published and no P7 CI is claimed. After verbatim prior-P7 history restoration, current text delta is 393 additions + 19 deletions = 412 (12 above hard gate before screenshot accounting); no real CA1–CA8 evidence or human acceptance is claimed.

## Documentation-only tracker recovery prerequisite (2026-09-30)

This candidate restores the complete task history from the service/IP worktree without shipping P7 source, tests, or runbook changes. The prior full combined P7 candidate and backup `codex/issue-45-06-full-boundary-backup-20260930` remain preserved; the current service/IP behavior is separate local-only work, not code delivered by this documentation candidate. Published-origin P7-E and all final CA1–CA8 evidence remain pending.

- [x] **MCP45-P7-TR-A — Restore full tracker history**: copy the full restored tracker, retain dated checkpoints and historical P7 direct RED/GREEN/deadline/split evidence, and update only the primary stage header to describe this documentation-only prerequisite. Exact copied input before header/checklist additions was 79,393 bytes, SHA-256 `4bbfbe9a3f9e948c51590fd5cd01968c4f8d517e0ee313b0a0c042af81b75239`.
- [x] **MCP45-P7-TR-B — Observe tracker contents in a read-only container**: use the P7-TR report command to read the actual task file and print only selected current/historical section markers. Parent owns execution and real screenshot; this structural/documentation proof does not validate source behavior or close the earlier PR #424 containerized Markdown-preview gap.
- [ ] **MCP45-P7-TR-C — Bind documentation delivery**: parent independently verifies current diff and task/report readback, accounts for screenshot in the actual-base size, updates the full Engram mirror, commits/publishes the documentation prerequisite and checks exact hosted CI. Human review remains pending; no issue closure or acceptance is claimed.

P7-D service/IP proof is separate from this candidate: local source `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283`, test `205885029a70adda1e9cd424f87efe446db473790d7334e93ff077b3bf7514c6`; parent observed 7/7 controlled tests and four syntax checks. Those files and checks are not in this documentation-only candidate. No runtime probe, Docker service, demo, network, or provider was executed for this task.

## Tracker recovery parent evidence checkpoint

Exact committed `bdc2d96a18a00d0426ff0a2209662c5417c5e7e7` read-only/networkless Node22.14 inspection exited0 and found seven selected markers; no application runtime or Markdown preview ran. Real [tracker inspection PNG](../../docs/evidence/issue-45-pr06-tracker/tracker-inspection.png),1600×1500/152003bytes/SHA`c4f39f73ef3c51790ca5d3a1cb31292e8f4f3cd6861d1e65ba0e6638eb59c072`, visually inspected/sanitized, records that tested checkpoint; later changes only record this proof/checklist and attach media. Initial entrypoint failure retained, direct Node command corrected. TR-C exact publication/CI/human request remains pending; all real CA1–CA8 open.

## Tracker recovery public candidate checkpoint

PR #435 published `08bf3fb60649ba73a70a1480c00fa81b6409a38c` on immediate owned P6 `529b2105a5f2ee841c804713b5e32b605edb965a`,84 additions+1 deletion=85 including realPNG. Public body/PNG were read back exact; papiarcacamilo requested, not approved. Parent current08bf document Docker inspection exited0/seven markers,82253bytes/taskSHA`40f5e29bc186b8001cf13dea93a174d25920e65c3478d1354ea2837fd0977342`,no runtime. ExactCI36716395896 is running; initial governance36716395845 cancelled, not a pass. TR-C remains pending terminal currentCI. This checkpoint is local recovery progress after publication, not pixels/current-tested bytes from the previous capture.

## P7-D owned tracker-inclusive restack checkpoint

Parent preserved complete service/IP source/tests/runbook/report/task in local `a81c10980fbae43cde58df53d16665b1e8629efa` and backup `codex/issue-45-06-service-ip-before-tracker-restack` before clean restack from529 onto PR43508bf. The sole task conflict uses the newest full parent recovery document, retaining all P6/P7/tracker-publication history and adding this current stage. Runtime source/test hashes remain `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283` / `205885029a70adda1e9cd424f87efe446db473790d7334e93ff077b3bf7514c6`; exact restacked verification and actual <=400 per-base count/proof are pending. No reset/stash or oversized publication; P7-E and real CA1–CA8 remain required.

## P7-D restacked parent verification and capture

Exact committed66ff3d87f5deeb1eba9c86c5800f4cd2f836b647 independently passed cached Node22.14 networknone256MiB Docker syntax4files and7/7(4direct+3gateway),no skips; source8d639/test205885 unchanged. Real [P7-D PNG](../../docs/evidence/issue-45-pr06/service-ip.png),1600×2100/252193bytes/SHA`2f42b09e81780d16ff9e8565d34720c31f0fbd8099d2d2122bededc12ba16a7f`, inspected/sanitized; actual committed output excerpt, not full/liveboundary. P7-D-C publication/exactCI/humanrequest pending. All real CA1–CA8 and P7-E remain open.

## P7-D public candidate and parent prerequisite CI checkpoint

Owned PR437 published41a3ed21aec8f579a2b5ce03bd37aecc34f41975 on43508bf3fb60649ba73a70a1480c00fa81b6409a38c,369add20del389includingrealPNG. Publicbody/PNG readbackexact; papiarcacamilo requested/notapproved. Parent independently exact41a3 cachedDocker syntax4files/full7/7,no skips,current-committed-green.log; source8d639/test205885 unchanged. Exact435CI36716395896 completedall8SUCCESS,none skipped/watch50507exit0/currentgovernanceSUCCESS. Exact437CI36718125319 running samewatch72940; initialgovernancecancellednotpass. P7-D-C remains pending terminal437CI. This checkpoint is localpostpublicationprogress, not pixels from earlier66ffPNG. All realCA1–8 and humanacceptance remainopen.


## P7-E published-origin extension candidate (2026-09-30)

Authorized scope is the preserved mandatory published-origin portion of the direct-target probe, based on P7-D PR #437. Keep all four inventory values required: service host, port, direct IP list, and bounded `MCP_PUBLISHED_ENDPOINTS`. Restore safe root HTTP(S) parsing, fixed unauthenticated `/healthz`, manual redirects, response-body cancellation, and allowlisted `{kind,status,http_status}` summaries. Preserve all service/IP cases and their behavior; append `published-port` observations. Invalid/missing complete inventory must contact no targets and remain `unverified` (exit 2); any HTTP response is reachable/fail (exit 1); blocked targets remain unverified. Coverage stays `supplied-targets-only`, `full_boundary` stays `pending`. Never claim total isolation, published-port absence, binding/topology, CA4/CA5, or human acceptance from controlled fixtures.

Effective test-first mode: strict ON from the issue handoff/OPERATING-RULES, not the repository toggle. Add/update permanent HTTP/CLI tests before source edits and observe RED against exact P7-D base `41a3ed21aec8f579a2b5ce03bd37aecc34f41975`. Use cached Node 22.14.0 image `sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d`, `--pull never --network none --memory=256m --memory-swap=256m`, 20-second helper, read-only test/script/schema mounts. No build/pull, host package tools, live target, credentials, producer/runtime, Compose, dependency or remote changes. Use unique `/tmp/issue45-p7-published-origins-evidence` captures; preserve all earlier evidence files.

- [x] **MCP45-P7-E-A — Observe published-origin HTTP/CLI RED**: retain existing service/IP behavior assertions while adding the valid published endpoint to complete fixtures; cover reachable HTTP 503/302, blocked endpoint, redirect not followed, safe summaries/no authorization/no URL or body leakage, and invalid userinfo/path/query/fragment with zero contacts. Explicitly test missing `MCP_PUBLISHED_ENDPOINTS` while the other three inputs are valid, expecting fail-closed unverified and zero requests. Capture exact RED before source edits.
- [ ] **MCP45-P7-E-B — Implement bounded published-origin checks**: parse only bounded root HTTP(S) origins with valid DNS/IP host and safe port; reject credentials and non-root path/query/fragment before any request; enforce existing combined target limit; append only `published-port` targets. Retain fixed `/healthz`, safe `{kind,status,http_status}` output, no authorization, manual redirect/body cancellation, and prior service/IP behavior. No pass/total-boundary semantics.
- [ ] **MCP45-P7-E-C — Verify and bind current slice**: exact cached networkless Docker RED/GREEN, unchanged gateway suite, Node syntax, diff/privacy review, source/test hashes, accurate runbook/report, and measured complete current-base delta including task/report/PNG. Parent owns independent check, fresh screenshot, full mirror, commit/publication/current CI and human-review request. Keep P7-D/P7-E real CA1–CA8 and human-acceptance work open.

The preserved combined-candidate implementation and tests are reference/history only; this task must not replace whole files from that branch. Existing P7-D service/IP tests and semantics remain required. P7-E is a supplied-origin controlled check, not proof of actual published binding or absence of alternate routes. Proxy/admin reachability, independent network/binding inventory, token absence, marker surfaces, live harness, and actual CA evidence remain pending.


## P7-E test-first checkpoint (separate frozen worktree)

Before the current symlink-correction task began, P7-E HTTP/CLI tests were added first in `/tmp/sre-agent-issue45-published-origins-20260930`; its P7-D source remained unchanged. Exact cached Node 22.14.0 networkless Docker observed 0/5 tests passing (exit 1): current P7-D omitted published-port summaries for 503/blocked/302 and accepted invalid or missing-only published inventory while contacting direct targets. Test SHA-256 `06abebbc07d036fae93f544099ecd89ff514b2e6e2cd3578f530c22c22ae6e8a`; capture `/tmp/issue45-p7-published-origins-evidence/red-confirmed.log`, SHA-256 `1911649e24602773a0d7c722fdb5e120b70733c5f2d9d6cffeae99bd15bbc3ce`. That P7-E source/test worktree stays frozen and its source was not modified. This checkpoint records only the honest RED; it is not part of the P7-D symlink-fix implementation.

## P7-D CLI symlink invocation review correction (2026-09-30)

Parent source-confirmed review [4144842486](https://github.com/creep1ng/sre-agent/pull/437#discussion_r4144842486): the current `pathToFileURL(process.argv[1])` entrypoint guard can skip `main()` when Node invokes the script through a symlink, silently exiting 0 rather than emitting the structured CLI report/status. Parent placed PR #437 in draft and acknowledged the finding in [4145035051](https://github.com/creep1ng/sre-agent/pull/437#discussion_r4145035051). Existing P7-D hosted CI `36718125319` passed all eight jobs and repaired governance/reconciliation `36720192583` passed; those checks are historical for the unsymlinked invocation and do not test this finding. Human acceptance remains pending.

Strict test-first remains ON from the issue handoff/OPERATING-RULES. Use a genuine E2E CLI invocation through an ephemeral symlink created only in container-writable temporary storage; scripts/tests/schemas stay mounted read-only. On the exact P7-D base `41a3ed21aec8f579a2b5ce03bd37aecc34f41975`, expect missing-inventory invocation through the symlink to emit the normal safe JSON report and exit 2, not silent exit 0. Preserve the four existing service/IP tests and all safety behavior. Use the cached Node 22.14.0 networkless Docker command, 256 MiB memory/swap, and 20-second helper; no network/live service, credential, runtime, producer, Compose, dependency, cloud, Git or remote operation. Existing P7-E RED/captures remain separate and untouched.

- [x] **MCP45-P7-S-A — Observe symlink CLI RED**: permanent actual CLI test creates a temporary symlink to the script, invokes Node through it with missing inventory, and expects a structured unverified report plus exit 2. Observe the silent/incorrect current behavior against exact base before source edits; retain all four direct HTTP/CLI tests and assertions.
- [x] **MCP45-P7-S-B — Preserve CLI entrypoint semantics through symlinks**: minimally fix main-entry detection so direct and symlink invocation execute the same CLI logic; retain safe report, exit 1/2 behavior, fixed `/healthz`, no-auth/manual-redirect/body-cancel controls, and existing service/IP behavior. Do not implement or claim the frozen P7-E source correction in this candidate.
- [x] **MCP45-P7-S-C — Verify and bind review correction**: exact cached Docker RED/GREEN for the symlink and all existing P7-D cases, existing gateway suite, syntax/diff/privacy checks, hashes and honest report/task proof. Measure complete candidate additions+deletions against PR #435 base `08bf3fb60649ba73a70a1480c00fa81b6409a38c`, including parent-owned proof/media; PR #437's old checks are not substitute proof. Parent owns independent verification, screenshot, mirror, commit/publication, current CI, governance and human review. Do not transfer PR #434's exception. No real CA1–8 or human acceptance is claimed.

Observed S-A RED on the exact unmodified P7-D base: cached Node v22.14.0 networkless Docker ran all five service/IP CLI tests; the new actual symlink invocation failed at the expected assertion (`0 !== 2`), while all four pre-existing direct-target cases passed (4 pass / 1 fail, exit 1). This confirms silent exit 0/no structured report through the symlink, not a network failure. Test SHA-256 `cc42eafa276225d4a26e112aed527bbdcb3c5d804797b7266eefadb7ef49923f`; unchanged source SHA-256 `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283`; raw `/tmp/issue45-p7-symlink-evidence/red.log`, SHA-256 `f01ff9e805e3f206b2151bea370b62ae6e08325eee7e568c01e2439584209ede`. Current test-first checkpoint is recorded before any source edit. S-B source fix remains pending. P7-E RED above is a separate frozen candidate. All real CA1–CA8, proxy/admin, topology/binding, token-absence, marker, live-harness, and human-acceptance evidence remain open.

## P7-D symlink GREEN and size-gate checkpoint

Minimal realpathSync/fileURLToPath entrypoint correction passed writer and independent parent cachedNode22.14 networknone256MiB Docker:8/8(5direct including actual symlink+3gateway),none skipped,four syntax checks,exit0. SourceSHA90ca3f79153c070ba000996241e7ce43030a2052f8a6b73dbb342b18e7a67879/testcc42eafa276225d4a26e112aed527bbdcb3c5d804797b7266eefadb7ef49923f. Parent raw /tmp/issue45-p7-symlink-parent-evidence/green.log; writer RED/GREEN preserved. Prior S-B-pending sentence is the dated RED checkpoint, not current status. Complete435-based candidate measured451 additions+deletions before this checkpoint/new media, exceeding400; no exception inferred from434 or unscoped acepto. Local candidate frozen/uncommitted; S-C screenshot/publication/exact correctedCI/human pending, PR437 remains draft. Ask one scoped437 size exception; do not trim history/tests or publish oversized. E source frozen; all realCA1–8 open.

## P7-D symlink owned-branch publication (2026-09-30)

Sole-writer correction candidate propagated the 4-file fix unchanged to owned `codex/issue-45-06-service-ip` (base `08bf3fb60649ba73a70a1480c00fa81b6409a38c`) and re-verified with fresh pinned captures: RED re-confirmed 4/5 (`0 !== 2`, exit 1) on base source `8d639e4c` (`red-owned.log` SHA `aec702ea22d66d6923e62d1026663377d7c255d709b5163eed34095460ee1e3e`); GREEN 8/8, no skips, exit 0 on fixed source `90ca3f79` (`green-owned.log` SHA `ba1ef0e46eb9c83e44cee73eec4ce8687e9b0df6abc1ab6bd3dde2411ad84bd9`). Report binds the new capture; committed PNG reused as the real rendered artifact (shown assertions byte-identical; symlink path evidenced by TAP log). Pushed only the owned branch with exact-lease check; new hosted CI, read-back, and human-review request recorded in the PR. P7-E stays frozen; CA1–CA8 and human acceptance remain open.
