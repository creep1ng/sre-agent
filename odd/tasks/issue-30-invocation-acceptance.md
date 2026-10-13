# Issue 30 invocation acceptance

## Objective / problem / why
Complete CA1–CA5 against the existing #187 gateway, not a second runtime.
Ricardo confirmed the matrix and controlled real server on 2026-10-03.
Project 8 midnight.agent: #30 Todo; #18/#129/#187/#29 Done.

## Authorized scope / constraints
Direct, delegated implementation: isolated real pinned Grafana MCP, Grafana and
Prometheus; vector(1) positive control; reuse #29 relay, capture and bounded audit.
No retries/fallbacks, autonomous tool calling, UI, Skills, BoK, merge or issue closure.
Preserve other worktrees, credentials and volumes; no prune/down -v.
Baseline main: 4a4515b99b6f5931f43969f7147c6ec90519344f (clean fast-forward).
RDD off (global). TDD ON: global Gentle AI state `strict_tdd=true`, found after
initial inventory; runner: python scripts/issue30_capture.py inside python-checks.
Write failure assertions first; observe real E2E RED before runtime fixes, then
GREEN and refactor. No post-hoc unit tests. Existing checks: containerized pytest.

## Checklist / acceptance / checks
- [x] T1: Version controlled real stack and failure injection, isolated networks,
  pinned images, scoped token; observed Compose/build/health/image identity.
- [x] T2: E2E CA1–CA5 matrix: deterministic 200 + exactly one tools/call;
  safe no-grant/nonvisible/401 with zero upstream calls; 422/timeout/failure;
  known ID allowed/denied before discovery; per-case counter deltas and bounded
  metadata-only audit (no MCP row for 401). Fix only observed defects if needed.
- [ ] T3: Execute exact documented recipe on committed candidate, mandatory
  checks, real screenshot, sanitized compact evidence and provenance.
- [x] T4: Focused PR to main with real evidence, current base/tested SHA,
  line-size accounting and pending human/hosted checks; do not merge/close #30.

## Progress / evidence / next step
Inventory complete. #475 is merged; its 502 proves boundary crossing only.
Historical #187 78845c8 200/vector +1 and 403/+0 retained as historical evidence.
Current #29 counter overlay uses inert backend; adapt only the demo environment.
Real RED: 2026-10-03 22:39:25..22:40:08 UTC, main4a4515b: 200/vector1,
forwarded call1; 403/401/422 zero; 504/503/502 safe injected faults. Missing
public success correlation requires additive header; JSON null harness check corrected.
User chose exactly two PRs: infrastructure/control → acceptance (no size exception).
GREEN be42244: 10 real cases passed, 9 bounded metadata-only rows, 401 zero.
PR477 and stacked PR478 drafts published; metadata readback valid, both <=400 lines.
Local checks: 1477 passed, 1 skipped, 3 relay readiness failures; targeted 2 passed/1 failed.
Separate Alembic and declarative checks passed; hosted unit passed on 3bebe70.
Main advanced to 9781ee7 (grant validation, contract2.6); tested HEAD remains explicit.
Next: finish contract checks, resolve local readiness and obtain human/422 CA4 review.

## Acceptance verification resume (2026-10-12, America/Bogota)

The preceding checklist and results are historical; they are not current runs.
Current user authorizes a new isolated Compose verification, full-event SQL/schema
inspection, 401 investigation and documentary evidence updates only. Direct work;
no runtime/schema/test-expectation change, remote publication, merge or closure.
The CA4 decision is approved in issue comment 6137102582, limited to MCP invalid
input/422/stage=validation; never request it again or apply it to the 401.
Current GitHub main/HEAD: 763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9.
Live Project 8 read: #30 OPEN/Todo, Sprint 3, Estimate 0.
Preserve the existing documentary diff (SHA256 e52b150006c2228c72ea7ff934ceaa64195d082512787a9a18d615fee926939b)
and every historical evidence file. Snapshot build inputs; record dirty documentary
scope separately from the committed runtime SHA. Only synthetic local secrets,
empty provider keys, no host-published ports, unique project/networks, no teardown
of unrelated resources. Verification does not authorize implementation, so no
new unit tests, TDD configuration changes or runtime fixes are applicable.

- [x] T5: Preserve documentary/evidence hashes and identify frozen candidate.
- [x] T6: Build isolated real Compose stack; record config/images and ready health.
- [x] T7: Replay unchanged ten-scenario runner, preserving all variants/counters.
- [x] T8: Read complete SQL events by request IDs and UTC; validate full schema.
- [x] T9: Search other/authentication operations for 401; reconcile OpenSpec/ADR/schema.
- [x] T10: Deliver fresh CA matrix, sanitized reproducible artifacts, separate defects
  and minimal proposals; retain all failed/not-executed checks and required approvals.

Memory mirror pending: runtime has no authoritative session ID and forbids writes;
local task/evidence persistence continues. Historical Engram task #9444 was read
and reconciled with this file; current user instructions supersede its old pending
422 interpretation and publication plan without rewriting historical results.

T5 observed: frozen `git archive` build inputs at 763ccfc plus the preserved
documentary file only; snapshot, original patch and hashes under ignored
`.demo-state/issue30-verify-763ccfc-08d022/`. Fresh private synthetic env/token
generated from `.env.example`; network-only inventory confirms exclusive unused
10.253.147.0/28 and 10.253.147.16/28. Both networks are internal, without host ports.
T6 observed: ten project containers created, API image
sha256:8027d8110b091553221f444dc06d43fec21d0e9220732e8b00c411969aaa0217
equals built image; API/DB/Grafana/Prometheus ready. HTTP readiness/control probes
all 200 and MCP TCP ready at 2026-10-13T03:38:16.819628Z. `/version` is not a
published endpoint (404); OpenAPI metadata is checked separately before replay.
Sanitized effective Compose config and full scoped image identities are saved.
T7 observed: OpenAPI reports runtime revision 763ccfc and contract 2.7.0;
unchanged issue30_capture.py completed all ten scenarios with zero assertions
failed. New replay is isolated under this run's capture directory, never copied
over historical be42244/d7518ac records. Full SQL/schema/401 checks are separate
and can fail even when this older acceptance runner passes.
T8/T9 observed: nine complete SQL rows (all columns), with separate full
contract envelopes after documented optional SQL-NULL omission; four pass and
five fail Draft 2020-12 schema 2.7.0. Three 403s lack required
authorization_denial_cause; 504/503 upstream events persist retryable=false
instead of true. Never repaired evidence or values. Invalid-credential 401 has
zero rows across ALL operations by its request ID/window, zero outside-window
matches for the same ID, and zero authentication/credentials.authenticate
events within the entire fresh replay window. runtime-audit-evidence requires
terminal authentication evidence; ADR-005/schema allow unknown identity to
remain absent. The approved 422 exception does not excuse these defects.
At the T8/T9 checkpoint, current-candidate checks were running on their separate
checks database; their final result is recorded below without altering runtime.
T10 observed: fresh report/matrix, full SQL/contract events, two validators, safe
401 reproduction and images/config/health/check receipts saved under
`docs/evidence/issue30-763ccfc-08d022/`. Both full validators confirm 4 passed/5
failed; a separate 401 repeat confirms zero all-operation rows and zero calls.
Existing current-candidate checks passed (1823 passed, 1 paid-provider skipped,
2 warnings; Alembic no new operations); fresh MCP fixture conformance passed.
Only the new Compose project is stopped, keeping its synthetic data/config.
Next: user approval for separate runtime corrections (401 terminal event,
denial cause propagation, 503/504 retryability), then fresh integrated evidence
and human acceptance. No approved interpretation or historical result is changed.

## Pull-request publication (2026-10-12, America/Bogota)

Current user requests PRs for the delivered changes, superseding only the previous
no-publication restriction. No merge, issue closure, runtime/schema correction or
test-expectation change is authorized. Three bounded direct review units: approved
CA4 documentation/recovery, read-only verification helpers, and captured evidence.
GitHub main remains 763ccfc; Project 8 #30 remains OPEN/Todo. Engram's old task
mirror was reread; local progress remains authoritative for this resumed work.

- [x] T11: Prepare focused local candidates, real rendered screenshots and PR
  evidence; fix only helper formatting, preserving semantics and captured results.
- [x] T12: Validate exact candidates and size against their actual bases; record
  current artifact checks separately from the 763ccfc integrated execution.
- [ ] T13: Publish authorized codex branches and open/attach three PRs; verify
  remote head/base/body readback. Leave human review, runtime corrections and #30 open.

T11/T12 observed: three exact artifact candidates rendered and checked: documentary
06d03bd, formatted helpers 5937d7a, evidence package 3a276f3. Actual Chromium
captures inspected; no API/browser run is claimed. Docker artifact checks resolve
35 source/line references, retain documentary SHA e52b150 and all four historical
files, preserve original run artifacts and confirm both Python helper ASTs.
Ruff check/format passed. Original helper source remains in commit ae97464.
Formatted SQL/Ajv helpers re-read original IDs/window from the retained ready stack,
producing four byte-identical outputs (4 valid/5 invalid). A new 401-only repeat
73762dd7-4745-4c1c-9a9a-65db3e85d157 returned 401, zero tools calls and zero audit
rows; presence check correctly exited 1. Runtime remained 763ccfc with identical
API image; Compose start reran its existing seed/migration dependencies. Only this
project was stopped again, without deleting data. New publication manifest and
receipts are separate from original run evidence. User explicitly authorizes the
GitHub app connection for branch/PR publication; gh authorization stays read-only
for Project 8. Remote PR metadata and human review remain pending at this checkpoint.

Publication-base discovery: live main advanced to ef6b328 during preparation.
Native comparison reports only eight added #567 docs/helpers/tests; no relevant
runtime/schema/lock/delivery file changes. Preserve frozen candidate SHAs and
execution receipts. Record current base in PR1, keep subsequent PRs stacked, and
do not credit the recorded suite as execution of the newly added tests. Hosted
merge-candidate checks and human review remain pending.
