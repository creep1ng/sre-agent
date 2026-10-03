# Issue 334 closure gaps

## Objective, problem and scope
Close CA5 consumption-policy audit provenance and CA8 controlled UTC rollover / in-flight policy evidence, including the related CA3 transition proof. Preserve #467 fail-closed, #468 correlation-based deduplication and all historical rows. Prepare a bounded PR to main; no merge or issue closure.

Base: `4a4515b99b6f5931f43969f7147c6ec90519344f`. Route: delegated direct.
GitHub Projects: user creep1ng project 8 midnight.agent; issue 334 Status Todo (live read).
Worktree: `/tmp/issue334-closure`, branch `fix/issue-334-closure`.

## Confirmed intent and constraints
User confirmed existing admitted requests keep captured effective policy, limits and UTC admission month through settlement; updates govern new admissions only. No cancellation, reassignment, heuristic historical reconciliation, payloads, secrets or real-provider calls. Public audit read endpoints are specified but not implemented; do not fabricate a runtime read endpoint or claim one was exercised. Verify actual persistence and repository retrieval.
Count additions plus deletions against current main; <=400 or explicit maintainer exception. Preserve unrelated branches/worktrees and test boundaries.

## Testing mode and runner
No explicit TDD on/off setting found; do not invent global TDD configuration. Follow repository test-first constraint and user-requested HTTP regressions: write behavioral integration scenarios before production code; observe failing CA5 on base, then verify GREEN. No isolated helper/unit-only substitute. Runner: existing Docker Compose python-checks, pytest with real isolated PostgreSQL and deterministic provider/catalog doubles. RDD off (global); ordinary human review required.

## Checklist
- [x] C1: Test-first CA5 HTTP success/rejection -> persisted/retrieved policy evidence. Preserve immutable published contracts and metadata-only audit. Capture RED then GREEN and relevant audit/admission tests.
- [x] C2: Controlled clock UTC month rollover with reserved and settled usage isolated per period, admitted-before/completed-after request, hot policy change while in flight, no double debit/loss/reassignment. Verify #467/#468 regressions.
- [ ] C3: Run mandatory repository checks and relevant budget/session/idempotency/concurrency suites; record tested/base SHA, environment, repeatable Docker commands, real sanitized output/capture and complete CA matrix. Publish PR to main, report pending checks and closure recommendation for human review only.

## Progress and next step
C1/C2 verified: base CA5 missing policy_ref; both final rollover variants failed on missing policy evidence before source changes. GREEN: 19 passed in 122.24s on actual source/tests (real HTTP/PostgreSQL). Four #468 coexistence variants returned 200/200/429; #467 and remaining reservation/idempotency acceptance checks passed. Known test-authoring cap/period-isolation errors were corrected before source; initial formatter cache permissions corrected with owner UID and no-cache. Next: commit candidate, full checks, evidence and PR; C3 pending.
