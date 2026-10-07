# Issue #333 — Residual consumption-read acceptance

## Objective and problem

Reconcile merged PRs #383/#384 against current main, repair only reproduced
consumption-read defects, and supply current, repeatable acceptance evidence.
The original implementation is delivered; unresolved review metadata is not
proof of a current defect. GitHub Project 8 remains Todo / Sprint 4.

## Scope and authority

- Route: delegated direct ODD; no new SDD pipeline.
- Exclusive candidate: `fix/issue-333-residual-20260929`, initially based on
  `5b6109bd2c8100455136cf12ce91c52830833c7f`.
- Owner: this issue session; one writer in the isolated candidate.
- Historical U333-1 through U333-5 remain delivered history in merged PRs
  #383/#384. The dirty brave-harbor recovery document and implementation remain
  untouched; never restore their older implementation over main.
- Authorized: bounded usage query/aggregation, additive contract and activation,
  behavior/conformance tests, documentation, evidence, owned follow-up PRs.
- Excluded: billing, price invention, token inference, currency conversion,
  #334 enforcement, cloud/SSH, paid/live-provider probes, merge/close/tag/deploy.
- Published 2.4.0 is immutable. Count all additions plus deletions per PR.
  Above 400 requires a new scoped maintainer exception or cohesive slicing.
- GitHub credentials are authorized only for `creep1ng/sre-agent`.
- RDD is off (global); do not change the user-owned switch.
- User now requires GPT-6 Luna high for delegated agents, never Astra xhigh.
- Maintainer approval: the user answered `aprobado` to the NEW size exception
  solely for the self-contained additive contract publication/activation
  (estimated 6,500–7,500 changed lines). Do not transfer it to other slices.
- Retain the user's established stacked-to-main strategy for issue #333:
  PR #421 → invariant preparation → publication/activation. Child PRs initially
  target their immediate parent for focused review; retarget after parent merge.
  There is no feature tracker and no automatic merge authority.

## TDD and checks

Strict RED → GREEN → REFACTOR is enabled by the inherited AGENTS instructions.
Write missing behavior scenarios before implementation; never invent RED for
already-delivered behavior. Use this candidate's unique Compose project and
isolated `python-checks-db`, never another workspace's or demo database.

Exact focused runner after safe local bootstrap:

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_usage_read_acceptance.py tests/test_audit_events_contract.py'
```

Applicable checks: usage/audit HTTP and PostgreSQL acceptance; response/control,
seed, incident migration and health regressions; Ruff lint/format; schema tooling
and release conformance; `git diff --check`; independent current-candidate
verification; hosted CI and governance; real sanitized screenshot and human
review request. Local, controlled-provider and hosted evidence stay distinct.

## Tasks and acceptance

- [x] **U333-6 — Validate cross-incident request attribution before filtering.**
  Reproduce identical/different consumption on one request across incidents;
  fetch all related response evidence, mark ambiguous attribution unknown,
  preserve exact-once, scoped run counts, UTC months and inspected-row cap.
  Checks: observed RED/GREEN, existing usage/audit acceptance, lint/format.
  Rollback: only query/aggregation change and its scenarios/documentation.
- [x] **U333-7 — Enforce cost and coverage contract invariants.**
  Reproduce contradictory cost metadata and coverage status/count examples;
  couple non-null amount to USD/exact and null amount to null metadata. Counts
  describe distinct requests and sum to request_count; status reflects counts.
  Use semantic validation for arithmetic, not a false JSON Schema claim.
  Checks: conformance negatives/positives plus runtime acceptance.
- [ ] **U333-8 — Publish and activate an additive contract.**
  Publish a self-contained next release containing the delivered usage route
  and usage.read audit operation; activate it without editing 2.4.0.
  Publication-size exception approved; coordinate the next additive version.
  Checks: immutable inventory, generation, conformance and runtime version/path.
- [x] **U333-9 — Retest delivered historical corrections.**
  Verify audit-before-release and audit_unavailable suppression, denial cause,
  Bearer challenge, seed/migration/readiness expectations; repair only a failure.
  Checks: current-candidate HTTP/PostgreSQL and migration regression commands.
- [ ] **U333-10 — Publish evidence and reconcile every touched PR.**
  Maintain all eight historical review threads, including outdated/resolved
  status, in a disposition ledger. Publish current SHA/base, CA1–CA7 mapping,
  exact Docker commands, observed output, sanitized actual screenshot, CI links
  and remaining human dependencies on each touched PR. Correct stale merged
  PR pending instructions additively; no historical branch rewrite.

## Progress and evidence

- Live GitHub identity and repo access verified as `creep1ng`.
- #384 merged at `6f637a6f1ddc3a206c744c9effb6690a22696829`;
  #383 merged at `4b0c8740a042a8654979dd43481c7ad4f9992ea1`.
- Live inventory is paginated; two #383 and six #384 threads were inspected.
  The initial inventory had no open issue-333 PR; subsequent PR #421 is below.
  Project 8 was read live before scoping.
- Current source confirms three residual leads: incident filtering before
  consistency, missing proposal invariants, advertised 2.4.0 without usage path.
  U333-6 is locally verified; contract/release leads remain U333-7/U333-8.
- U333-6 RED: 3 failed / 41 deselected before source edits. After container
  Ruff normalization, usage/audit GREEN: 48 passed in 18.45s. Check-only Ruff
  passed; both files already formatted; `git diff --check` passed.
- Owned Compose project `candidate-wt-9bb3531fa9f1` uses `python-checks-db`.
  Initial Docker pool exhaustion prevented execution; inspected routes/networks
  before creating only its runtime bridge at non-overlapping `10.253.33.0/24`.
- U333-9: 103 seed/migration/readiness/control/response regressions passed in
  33.87s; usage audit-before-release, failure suppression, denial cause and Bearer
  challenge also passed in the 48-test run. No historical fixes were reapplied.
- Local evidence and all-eight-thread ledger: [residual review](../../docs/evidence/issue-333-residual-review.md).
  Actual FastAPI/SQL captures and visually inspected Chromium screenshot are ready
  for parent verification; capture rerun passed 2 tests (42 deselected, 7.00s).
  Independent verification, publication, hosted CI and human acceptance remain pending.
- Full existing release snapshot is 194 files / 6,150 lines before additions;
  its self-contained publication cannot fit a 400-line PR by omitting evidence.
- PR #421 is published at `c57732f4407e9a0d4e9ee89fde7286e79b4f1876`:
  304 changed lines, real JSON/PNG/SQL, independent 48+103 tests, parent 48-test
  spot check, and all eight hosted CI jobs passed in run `36657302250`.
  Final evidence-binding governance run `36659223751` also passed.
- Source/head and actual hosted synthetic merge `36d44dcd04b9f0207ff6eb0d86722741bf8e03d1`
  share full tree `1a89670e5aa0e25352a1c93ec09a2c67000c0c9e`. The unavailable
  `d6f31fb` in review prose was not substituted for the actual candidate.
- Remaining invariants were reproduced on this exact head: AJV and runtime
  accept four contradictory cost/coverage payloads; seven valid examples pass.
  ASGI OpenAPI still advertises 2.4.0 with a usage route absent from that snapshot.
  Existing immutable 2.4.0 validates: 199 artifacts / 16 checks, hashes unchanged.
- At the U333-7 checkpoint, implementation was on
  `fix/issue-333-contract-invariants`, based on the owned PR #421 head;
  publication followed after invariant verification.

- U333-7 RED: runtime 16 failed / 10 passed; after fixing composed-filter closure,
  schema/semantic checks had 16 failed / 11 passed. Focused schema GREEN: 27 passed.
  Final runtime/usage/audit: 74 passed; full tooling: 123 passed; all ten immutable
  releases validate; all 194 published 2.4.0 file hashes are unchanged. Ruff and
  whitespace checks pass. [Invariant evidence](../../docs/evidence/issue-333-contract-invariants.md).
- Runtime identity is restored; reconcile the full Engram mirror before commit.
  Future delegated agents use the current user-selected GPT-6 Luna high profile.

- U333-8: `fix/issue-333-contract-publication` adds the self-contained immutable
  2.5.0 snapshot without editing 2.4.0; usage route/audit operation, typed
  response schemas, positive conformance fixture, consumer obligation, generated
  projections, evidence, compatibility record and manifest are present. The
  existing generator reports 202 artifacts / 17 checks. Strict RED first observed
  an old active version and absent 2.5.0 manifest; OpenAPI parity found FastAPI's
  nullable optional-query schema and inherited bearer security shape. Canonical
  2.5.0 now matches the runtime's selectors and security. Configured full Python
  runner: 1,250 passed / 1 skipped; lint/format, architecture, typing, repository
  contract checks and Alembic check passed. Tooling: 124 tests passed; all 11
  releases validate; canonical control-plane and responses OpenAPI lint passed.
  Exhaustive immutable-release validation confirms 2.4.0 unchanged. Local evidence
  only; hosted CI, screenshot/review artifact and human acceptance remain U333-10.
- U333-10 local evidence preparation: added `docs/evidence/issue-333-contract-publication.md`,
  guarded capture helper, actual sanitized OpenAPI/producer/read/SQL JSON, and
  native Chromium screenshot of the actual usage HTTP response. Capture was a
  controlled integration with the existing provider stub and isolated
  `python-checks-db`; Chromium emitted a background GCM `DEPRECATED_ENDPOINT`
  diagnostic. Helper Ruff lint/format passed; report records the full local
  runner results, hashes, all eight historical thread dispositions, CA1–CA7,
  and prior-run CI links. U333-10 remains unchecked: current hosted CI and human
  acceptance/publication of the reconciled report are pending the parent.

- U333-8 follow-up on PR #429 finding `4141907709` (current local changes atop
  parent-committed/pushed `1445ad9f82698842ec2e2a4071a6f9790c7ac609`): verified
  that the old 2.5.0 audit schema admitted non-`admin.read` actions and missing
  or leaked auth context across persisted usage outcomes. Strict TDD matrix RED
  rejected real 403/413/503 events and admitted wrong-action 401/fake-principal
  variants. Only the new 2.5.0 audit domain schema and its permanent tooling
  conformance test/positive fixtures were changed; runtime is unchanged. Updated
  only 2.5.0 projection goldens, evidence, and manifest through the existing
  release CLI; older releases were not edited. GREEN: focused tooling 2/2,
  usage/audit PostgreSQL/FastAPI acceptance 74/74, full tooling 125/125, all 11
  releases validate, OpenAPI lint passes, and `git diff --check` passes. Recheck
  exact full candidate size and hashes at parent handoff. The existing rendered
  HTTP screenshot and sanitized capture remain fresh because runtime/OpenAPI HTTP
  response code is unchanged; the contract projection itself has been regenerated.
  U333-8 remains delivered; U333-10 is pending current-candidate hosted CI,
  parent verification, and human acceptance. Prior hosted CI/governance for
  parent head `1445ad9` is historical and not evidence for these uncommitted changes.

- U333-8 reopened before publication by independent finding: the previous
  usage.read 403 contract admitted only `grant_not_applicable`, but a scoped
  owned-DB probe observed persisted denial rows for `principal_inactive`
  (inactive principal), `resource_inactive` (active principal), and
  `resource_missing` (active principal). Strict test-first RED observed all
  three positive cases rejected; permanent tests also pin their contexts and
  reject mismatched principal status. The new 2.5.0 denial branch now admits the
  four runtime causes while preserving `admin.read`, authenticated identity,
  resource, deny decision, and cause/status compatibility. Only the 2.5.0 schema,
  outcome fixture/test, projections, manifest/evidence, and evidence/task docs
  are in scope; runtime and earlier releases are unchanged. Focused usage schema
  tests: 2 passed; focused usage/audit Python acceptance: 74 passed; full
  tooling 125/125, all 11 release validations, and OpenAPI lint passed
  sequentially. All 1.0.0–2.4.0 release paths retain exact bytes and modes.
  The final complete candidate diff and refreshed hashes are recorded in
  `docs/evidence/issue-333-contract-publication.md`; no commit, push, current CI,
  or human review is claimed. U333-8 is complete; U333-10 remains pending.

## Next step

Independent U333-7 verification passed: 74 Python, 123 tooling, ten releases;
2,168 file hashes/modes unchanged. Parent focused spot check: 27 passed.
U333-7 is committed and published as PR #428 at
8965cb1978f9363a807279b6ec1b60c76d739e42, based on PR #421; 394 changed lines.
User explicitly authorized current GitHub reads/publication through gh.
Live Project 8 remains Todo / Sprint 4; main and related open PRs have no
competing 2.5.0 publication claim. U333-8 is complete locally on
`fix/issue-333-contract-publication`, based on PR #428. Preserve immutable 2.4.0
and exclude unimplemented #334 reservations/enforcement; compatibility with its
future settlement remains that issue's coordination dependency. Continue with
U333-10: publish sanitized evidence and reconcile touched PRs; hosted CI and
human acceptance are not claimed by U333-8. Preserve recovery roots.

Independent final publication verification passed: 1,250 Python / 124 tooling,
11 releases, guarded fresh HTTP/SQL capture, and zero file hash/mode drift.
Parent OpenAPI parity spot check passed. Publish this verified candidate next;
hosted CI, current PR reconciliation and human review remain pending.

PR #429 automated finding `4141505117` was reproduced on base `47673b9b4e9306c3c40aec638874b5505d002de6`:
the standalone `2.5.0/openapi/usage-read.yaml` omitted explicit nullable branches
for all three optional query selectors. Permanent test RED observed for
`request_id`; fixing only this unmerged 2.5.0 artifact restored parity with the
proposal, canonical control-plane schema, and FastAPI runtime. The 2.5.0 evidence
and manifest were regenerated through the existing release tool; no older
release changed. GREEN: focused two Python tests, sequential configured Python
1,251 passed / 1 skipped, tooling 124 passed, all eleven releases validate,
OpenAPI lint passes; `git diff --check` and 2.4.0 immutability pass. A concurrent
full-run attempt showed unrelated auth/control DB failures; sequential rerun
passed. The 150-line candidate count and parent-freeze instruction above were
historical at that checkpoint; parent subsequently committed/pushed
`1445ad9f82698842ec2e2a4071a6f9790c7ac609`, whose eight-job hosted CI and
governance checks passed. They do not cover the further uncommitted audit-cause
correction recorded above. `docs/evidence/issue-333-contract-publication.md`
contains the current hashes, reproduction, and finding disposition.


Final independent audit verification passed: focused tooling2/2, targeted
Python setup/append-failure2/2, real three additional403cause HTTP/SQL probes,
all11releases/lint, and zero drift in2,375candidate files/1,579oldrelease files.
Sanitized actual denial-context output is published with the report separately
from faithful projected fixtures. Append-only audit DELETE attempt rejected;
successful probe preserved audit rows. Parent is freezing this correction next;
new hosted CI and human evidence acceptance remain U333-10 dependencies.
Parent guarded repeat helper: one setup test and all three actual403 SQL contexts
passed; missing project guard rejected safely; Ruff lint/format passed no-cache.
Public JSON and safe Docker replay helper accompany the final report.


## Reopened publication corrections — authorized 2026-09-30

The frozen `6ed5335ab91f0056ccb4f93bb6f961ac0e25728a` passed all eight
hosted CI jobs in run36693220835 and governance36693219129. Later live reviews
4142861478/4142861488 found input-month and pre-authorization503 contract gaps;
these invalidate final publication completeness, not the earlier verified work.
The user explicitly chose early rejection of unrepresentable input months.
Current Project8 is consulted live before edits; one writer retains this owned
publication candidate, and the dirty recovery root remains read-only.

- [x] **U333-8a — Reject unrepresentable input months before authorization.**
  Supported selectors have year0001..9999, excluding9999-12 because the exclusive
  following-month bound is unrepresentable. Match Query validation, typed input
  filter and all proposal/proposed2.5 selector schemas. Leave observed output
  month-list shape unchanged. Prove HTTP422 precedes authorization, persists a
  context-free validation event, and does not invent identity; normal and valid
  boundary months still work. Permanent behavior/conformance tests first with
  observed RED, then GREEN using the existing owned Docker/Python/Node runners.
  RED: focused Docker tests were 3 failed / 3 passed: `0000-01` and `9999-12`
  reached authorization and returned 503 under the guard; standalone selector
  constraint parity failed. GREEN: added a portable shared supported-month
  pattern (years 0001–9999 excluding 9999-12) to the FastAPI query, typed filter,
  proposal and 2.5.0 selector/filter schemas; an explicit pre-authorization
  runtime check is necessary because FastAPI's Query pattern is emitted to
  OpenAPI but did not reject these query strings at runtime. The month-list
  output schema/model remains unchanged. Invalid selectors now return 422 and
  persist context-free validation audit rows; `0001-01`, `9999-11`, and `2026-09`
  remain successful. Focused configured Docker/Python acceptance + release/runtime
  OpenAPI parity: 6 passed. Full release tooling/manifest normalization remains
  to be performed after U333-8b.
- [x] **U333-8b — Admit real pre-authorization storage503 audit context.**
  Inject an authorization/credential storage fault before context exists and
  observe HTTP503 plus an independently persisted usage.read event with absent
  identity/resource/policy; distinguish audit append failure503 with no row.
  Add permanent test-first conformance positive/negative coverage and allow only
  complete authenticated or complete context-free503 shapes, not partial context.
  Conformance RED was observed against the real stale 2.5.0 schema: the complete
  context-free `usage.read/admin.read` 503 event was rejected. Runtime behavior
  was already delivered; new PostgreSQL/FastAPI acceptance GREEN passed and
  confirmed persisted JSON-null identity/resource/policy context. The existing
  append-failure cases still return `audit_unavailable` with zero rows. Added an
  explicitly labeled faithful positive schema fixture, strict partial-context,
  wrong-action and `audit_unavailable` negatives, and a separate sanitized actual
  HTTP/SQL observation at `docs/evidence/issue-333-preauth-storage-503.json`.
  The focused conformance test passed 1/1, and the scoped HTTP/SQL test plus
  existing append-failure parameter cases passed 5/5. The fixture remains a
  faithful schema projection; the JSON evidence is the distinct real observation.

Constraints: strict TDD enabled by the handoff; exact focused runner above,
plus tests/test_usage_read_contract.py and tests/test_usage_read_openapi.py as
applicable. Preserve all older release bytes/modes. Refresh only unmerged2.5
projections before evidence/manifest using the existing release tools. No new
calendar mechanism, billing, admission enforcement, live provider, browser or
remote deployment. About400 authored lines/task is advisory, never code-golf;
the publication-only exception remains scoped and actual count is disclosed.

After each task, record observed outcomes/checks here and parent-mirror the full
document. U333-8a and U333-8b now have focused local GREEN evidence; refresh only
2.5.0 generated projection/evidence/manifest and run full sequential local checks
before independent verification. Independent sequential verification, current frozen-head CI/watch,
real sanitized evidence and updated PR/review dispositions remain U333-10.
Human review is still pending; do not mark the whole issue accepted.

Final reopened-correction checks (candidate still uncommitted at base
`6ed5335ab91f0056ccb4f93bb6f961ac0e25728a`): sequential rebuilt configured
Python runner passed **1,257 tests, 1 skipped** in 101.81s, Ruff lint/format,
five import contracts, typing (12 source files), and Alembic no-new-upgrade
check. Skip: `tests/test_openrouter_live.py::test_openrouter_gateway_live_smoke`
(live provider intentionally disabled). Release tooling **125/125**, all 11
releases validate, OpenAPI lint/bundles pass; focused usage-release **2/2**,
focused usage acceptance/OpenAPI **82/82**, month RED **3 failed / 3 passed**
then GREEN **6/6**, preauth schema RED then GREEN **1/1**, actual preauth and
append failure acceptance **5/5**. Older release byte/mode snapshot comparison
reported zero drift across 1,579 files. U333-10 stays pending parent independent
verification, current-candidate hosted CI, PR reconciliation and human review.
No commit/push/remote provider/browser run was performed. See
`docs/evidence/issue-333-contract-publication.md` for evidence paths, exact
scope, findings, hash identities, and reproduction details.

Final independent 8a/8b verification: 82 Python, two Node conformance tests,
all11releases/lint/whitespace passed;1,579oldreleasepaths/2,380candidateentries
hash/mode/status zero drift. Current2.5inventory199files/204artifacts/17checks.
Parent rebuilt focused actual Docker spot: both forbiddenmonths pluspreauth503
threepassed. OriginalrawREDwasnotindependentlyreviewed; writerobservedsequence
reported honestly. Freeze/push newcandidate next; exactheadCI/humanpending.
