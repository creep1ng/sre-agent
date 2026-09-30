# Issue 45: Governed Grafana MCP Verification

**Current delivery stage: P4 controlled metric/log smoke queries atop the P3 gateway-origin correction.** The combined candidate preserves discovery, rejects non-root URL paths, and exercises only fixed gateway queries with controlled fixtures; CA1–CA8 remain open.

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
- Current handoff authorizes bounded issue #45 local repair/tests and parent-owned GitHub operations only in `creep1ng/sre-agent`. The only commit operation authorized for this transition is the parent's exact `git add` of five P4 paths followed by `GIT_EDITOR=true git rebase --continue` in this worktree. No push/publication, cloud, SSH, paid-provider probe, deployment, merge, or issue closure is authorized.
- Parent refreshed live GitHub Project #8: issue #45 remains Todo, Sprint 4, with CA1–CA8 in scope. PR #425 has an open gateway-root-path review finding; no human acceptance is claimed.
- Follow the revised `AGENTS.md`: this is an academic tool for independent freelancers, not production SRE hardening. Prefer one repeatable E2E test over isolated or change-detector tests, and use only real evidence or exact reproduction instructions.

## Authorized Scope

- Preserve the P3 origin/path correction and P4 metric/Lucene-log smoke queries in `scripts/demo_mcp_gateway_probe.mjs`, with current HTTP/CLI tests, runbook and evidence.
- Preserve malformed-entry/redirect/privacy coverage and 35-second budget. No P5 source, producer/runtime, Compose/Dockerfile, dependency, live-service or credential changes.
- Parent owns commits, publication, branch propagation and human-review requests; this restacked candidate combines `codex/issue-45-gateway-root-path` and `codex/issue-45-03-queries` only.

## TDD

- Mode: strict
- Source: issue-specific handoff §4 / OPERATING-RULES §4, which enables strict TDD for issue #45 implementation; repository `AGENTS.md` separately prefers E2E, prohibits writing unit tests after code, and requires failure modes first for isolated work.
- Runner for the combined P3/P4 candidate: pinned Node 22.14 cached harness with controlled loopback HTTP/CLI tests in a networkless container; exact `docker run --pull never --network none` reproduction is recorded in the P4 report. No host package manager, DB/API/demo or live credential is needed. Historical root-only and preview-helper notes remain in dated checkpoints below.

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
