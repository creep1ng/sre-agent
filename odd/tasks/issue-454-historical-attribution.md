# Issue #454 — Historical request attribution

## Objective, problem and why

Deliver the backend producer for all CA1–CA11 of #454: authorized historical
request attribution survives mutable alias reassignment without exposing content.
Existing usage accounting and audit navigation are not historical attribution.

## Scope and authority

- Route: delegated direct Organic Driven Development; no SDD artifacts.
- Branch: `codex/issue-454-historical-attribution`.
- Current base: `23e1a42dd1f3c0ad98b76ee6f5f25906570d50c2` (fetched main).
  Main's #541 and #568 evidence/proof work retained without source conflicts.
  Rebased design-first provenance commit is `3adefc2`.
- Live GitHub Projects consulted: midnight.agent; #454 Todo, #143 In progress.
- Scope authority: #454 and approved comment 6073849454; #143 comment 6073854153.
- Backend owner Ricardo/creep1ng; consumer UI belongs to Mario/Mariog89.
- Authorized current gh session for this repository, branch publication, draft
  PRs and Codex GitHub review. No merge, issue closure, paid provider calls,
  new credentials, personal Mario branch, or unrelated remote destinations.
- Immutable separate per-request snapshot; AuditEvent remains HMAC protected.
- Dedicated bounded `/v1/usage/requests` projection to formalize, exactly one
  request/incident/month selector; reuse authoritative selection and accounting.
- Legacy attribution explicitly unavailable; never reconstruct from current alias.
- Document historical storage/resolution and projection BEFORE production edits.
- Immutable published releases unchanged. Repository PR size limit applies:
  additions plus deletions over 400 require cohesive slicing or explicit approval.
- RDD off, global deciding source; ordinary checks and human review remain.

## Testing configuration and checks

Effective TDD mode: ON, explicitly authorized by the user on 2026-10-09 for #454.
Observe RED -> GREEN -> REFACTOR. Prioritize E2E/API/PostgreSQL acceptance with
verifiable repeatable artifacts; no tautological or change-detector tests. Write
behavior/failure scenarios BEFORE production code, following AGENTS.md.

Safe configuration prerequisite: run `scripts/bootstrap-worktree.py` (host Python3)
to prepare ignored `.env`/`.env.worktree` from public defaults; use only local
non-production values and never print or attach those files.

Exact focused runner (after isolated safe local configuration):

```sh
docker compose --env-file .env --env-file .env.worktree --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_issue_454_attribution_acceptance.py'
```

Applicable checks: Ruff lint/format, configured mypy, import boundaries, Alembic
upgrade/check, schema release/conformance/OpenAPI checks, response/OpenRouter/usage
authorization and accounting regressions, full Python checks, diff hygiene.
Use current candidate's isolated checks database only. Local controlled provider
evidence is not a paid/live external call; hosted CI is not human acceptance.

## Tasks and acceptance criteria

- [x] **A454-1 — Record storage, authorization and projection decision.**
  Publish repository-visible design before source changes; requested vs credited
  evidence, legacy absence, immutable capture, navigation admissibility and atomic
  acceptance semantics. Checks: read back, reconcile approved decisions CA10/11.
- [x] **A454-2 — Preauthor behavior scenarios and formalize contract.**
  Closed bounded selection/attribution/error/navigation contract; immutable-release
  governance; preauthor real HTTP/PostgreSQL tests for CA1–CA9 and alias races,
  canonical OpenRouter credit, legacy/no evidence, denied and invalid reads.
  Checks: observed RED if TDD enabled; new-release schema/conformance validation.
- [x] **A454-3 — Implement immutable capture and provider evidence.**
  Migration, separate append-only persistence, exact routing snapshot, distinct
  requested/credited fields and explicit absence; audit HMAC behavior unchanged.
  Checks: capture/race/rollback/migration behavior and relevant adapter regressions.
- [x] **A454-4 — Implement authorized dedicated request projection.**
  Reuse authoritative bounded selection/dedup; no duplicate accounting; server-only
  historical resolution; no current alias inference; contract-admitted navigation.
  Checks: selectors/auth/sanitization/legacy/overflow and consumption regressions.
- [x] **A454-5 — Verify current integrated candidate.**
  Lint/types/contracts/full applicable tests/migration and recoverable corrections.
  Checks: actual commands/results at exact source SHA; record skipped/failed checks.
- [x] **A454-6 — Demonstrate CA1–CA11 with repeatable real evidence.**
  Docker Compose real API/PostgreSQL run/read/reassign/reread, negative responses,
  sanitized actual screenshot, exact SHA/environment/preparation/commands and
  expected-vs-observed matrix. Clearly identify controlled provider and pending
  independent human review. Checks: repeat reproduction and inspect artifacts.
- [x] **A454-7 — Prepare review-ready draft delivery.**
  Cohesive PRs within size policy or explicit exception; Refs #454/143 only.
  Request Codex GitHub code review for every PR, fix P0/P1, check candidate/CI and
  attach PRs. No merge/closure or invented human acceptance. Checks: remote readback.

## Progress and next step

Live issues/comments/Projects read and main fetched; existing mechanisms inspected.
A454-1 decision recorded in `docs/design/issue-454-historical-attribution.md` before
production edits; parent readback/approved-comment reconciliation/diff hygiene PASS.
No independent human acceptance claimed. Production implementation now exists;
final exact-SHA integrated contract/verification evidence remains pending.
Baseline Responses/OpenRouter/usage acceptance: 120 passed in 62.69s, exit 0,
real isolated PostgreSQL and controlled providers, unchanged source at base878a0b2.
Original design-first commit `de9701d` rebased to `52f43b0` records A454-1.
Default Docker address pools exhausted; temporary network
overlay `/tmp/sre-agent-issue454-network.yaml` uses inspected free 10.253.144.0/28
without removing unrelated networks. Logs: `/tmp/issue454-baseline.log`.
Next: A454-2 delegated preauthor acceptance scenarios/contract; TDD enabled.
Writer must produce observable API/PostgreSQL failures before production edits;
controlled provider is explicit, not a claimed live external/E2E provider call.
Initial A454-2 Docker run: proposal YAML/JSON Schema syntax PASS; pytest RED
11 failed / 39 passed in 14.90s, exit 1 (`/tmp/issue454-red.log`). Missing route
and credited-model assertions fail as intended, but legacy and duplicate fixtures
failed AuditEvent validation before behavior; correct fixtures and rerun RED before
production edits. Do not present these two setup failures as valid TDD proof.
Corrected-fixture rerun: proposal syntax/schema PASS; verified RED 11 failed /
39 passed in 15.60s, exit 1 (`/tmp/issue454-red-verified.log`). All failures are
missing requests route or missing adapter credited-model evidence, not setup
errors. Tests/proposal preauthored before production. A454-2 remains partial until
the new immutable release/conformance is published and validated. Next A454-3:
immutable capture and explicit credit, then A454-4 shared authorized projection.
Contract publication research: 2.7.0 baseline is 199 files / 7,460 lines; 2.8.0
must be self-contained under current tooling. A focused size-exception question
was approved by the user on 2026-10-09 exclusively for the contract 2.8.0 PR;
Verified actual GitHub label `size:exception-contract-update`; apply it only to
that contract PR as explicitly authorized. No label applied or PR created yet.
Other PRs remain <=400; no transferred exception or auto-approval implied.
Keep existing 2.7.0 unchanged; synchronize canonical control-plane + standalone
usage-read + new schema/fixtures; register issue-454 conformance only for >=2.8.
Generate projection/evidence/manifest for the NEW unpublished release; never edit
historical manifest hashes. Runtime activation follows verified new contract.
Mirror status: PENDING. Host lost registered runtime session identity on resume;
agent-attributed Engram writes are forbidden until host re-registers the same ID.
Retain local progress; read mirror9911 as older state, do not invent a new session.

## Resume verification update

Acceptance scenarios reorganized without dropping assertions into shared support,
roundtrip, evidence and guards. Runner includes
`tests/test_issue_454_attribution*.py tests/test_openrouter.py`.
A454-3 capture source written; DTO correlation access and UUID serialization bugs
found during parent review and corrected before checks. No capture/E2E GREEN yet.
New Docker build failed ENOSPC during image export, before tests ran; log
`/tmp/issue454-capture-check.log`. No unrelated resources pruned by this task.
Temporary verification uses existing dependency image
`sha256:f2df24f6c4a8b001c0d647a7cca36431a60572e1ac397a01b902eaf3c9ad9274`
with current src/tests/migrations/schemas mounted read-only and tmpfs /tmp; not
freshly rebuilt candidate evidence. Mounted check: 40 OpenRouter passed, 10
acceptance fixture errors from organization losing decorators/imports; Alembic
not current (255). Refactor corrections pending; all failures recorded honestly.
Task file unexpectedly found zero bytes after failed image export; preserved
empty copy `/tmp/issue454-task-empty-preserved.md` and restored committed state
plus these verified updates. Cause of truncation unconfirmed. Readback required.
Latest replacement AGENTS and ODD workflow reference read; delegate only useful
independent/complex work, not by file count. Engram mirror remains pending.

Corrected refactor verification: 10 acceptance scenarios execute and fail ONLY
because GET requests is absent; 40 OpenRouter tests passed in 21.87s and
Alembic check PASS (migration status 0), log
`/tmp/issue454-capture-mounted-verified.log`. Shared support/roundtrip/evidence/
guards keep all assertions; worker Ruff+format and collection checks passed.
Parent capture/test lint PASS; two source files needed standard formatting.
A454-4 projection writer and A454-2 contract writer now work in disjoint scopes.
Contract-only size exception explicitly granted; no PRs or labels applied yet.
No full GREEN/capture atomicity/CA demonstration claim until integrated checks.

## Integrated projection verification

Current mounted candidate: 50 acceptance/OpenRouter tests PASS in 24.46s;
Alembic PASS (tests_status=0 migration_status=0), actual log
`/tmp/issue454-projection-check.log`. This validates roundtrip, in-flight alias
reassignment, canonical OpenRouter credit (mocked HTTP), legacy, authorization,
selectors, snapshot immutability, audit rollback and outage scenarios. No live
paid provider calls. Contract RED observed in container: two failures, missing
manifest and composed-schema closure; `/tmp/issue454-contract-red-current.log`.
Earlier worker Docker-denial report contradicted by actual TAP output; corrected.
First parent lint failed on unwritable Ruff cache, types broad unconfigured run
hit mypy internal error; retry uses no cache and repository configured scope.
Shell status variable is readonly in zsh; actual inner results/logs were retained,
so shell wrapper exit1 does not invalidate observed tests_status=0.
Full regressions, contract GREEN, types/lint, network demo and review remain pending.
Engram mirror remains pending because authoritative runtime identity unavailable.

Regression attempt: 10 new E2E passed, 80 existing fixture errors in 123.30s,
`/tmp/issue454-regression-artifact.log`; root cause verified DuplicateTable:
existing teardown drops audit_events but leaves new request_attributions table.
Updated existing fixture cleanup only to include the new dependent table, and
TRUNCATE lists to preserve FK invariants; no assertions removed or new post-code
unit tests. Repository configured mypy PASS (12 files); projection Ruff formatting
corrected, final quality rerun pending. Genuine loopback HTTP/PostgreSQL controlled
provider demo driver added (no live provider), sanitized API/SQL output pending.

Corrected regression candidate: 90 tests PASS in 84.31s, with E2E roundtrip
artifact printed from the actual container (`/tmp/issue454-regression-demo.log`).
Demo driver initially incorrectly expected only `error`; governed ErrorEnvelope
also requires safe request_id and retryable. Corrected driver to the published
closed envelope; no backend relaxation. HTTP/SQL rerun pending.
Final Python Ruff+format PASS (216 files), configured mypy PASS (12 files),
`/tmp/issue454-quality-final.log`. Broad unconfigured mypy internal error remains
separate from repository-supported type scope. All outcomes are local, not CI.

Real HTTP (Uvicorn loopback, not TestClient) + isolated PostgreSQL demonstration
PASS exit0: `/tmp/issue454-http-sql-proof.log`. Same request's before/after JSON
identical despite current alias becoming anthropic/claude-3.5-haiku; snapshot SQL
still openai/gpt-4o-mini/openai/triage-agent. Actual401/403/422/422 closed errors;
no content/credentials/raw HMAC. Explicit controlled credited provider (no paid
or external call). Provisional working tree evidence; exact committed SHA rerun,
screenshot and durable sanitized artifact still required before delivery.
Full regression suite launched serially, log `/tmp/issue454-full-regressions.log`.

Provisional actual Chromium screenshot captured from the sanitized JSON output,
`/tmp/issue454-proof-provisional.png`, viewed/inspected successfully. This is real
browser capture of actual API/SQL evidence, not a fabricated UI or SVG. Do not
publish as final: report says working-tree, must rerun at final tested SHA.
Runtime contract activation RED (existing contract test adjusted BEFORE changing
version): 1failed1passed10.43s, `/tmp/issue454-activation-red.log`, active2.7.0
versus required2.8.0. Version remains2.7.0 pending contract publication checks.
Full-suite first attempt26passed5fixtureerrors30.63s; three other explicit
teardown lists omitted dependent table, corrected without assertion changes.
Full-suite retry ongoing; no whole-suite PASS claim.

Second full-suite run143passed5fixtureerrors88.15s; BOK reset used a differently
ordered cleanup list. Corrected that pattern in BOK/health/skill/triage isolated
fixtures; inspected all remaining explicit full-schema reset files for omission.
Third whole-suite run pending `/tmp/issue454-full-regressions-corrected.log`.
Contract consumer conformance now passes, generation revealed ownership/ADR
2.8 allowlist omissions; scoped writer extension authorized for version additions
only, not governance relaxation.

Additional Docker quality checks PASS exit0 (`/tmp/issue454-boundaries-lock.log`):
repository-wide Ruff check/format (255 files), uv locked dependency resolution
(93 packages), five import contracts kept/zero broken, ShellCheck entrypoint and
worktree wrapper. Memory context/full observation9911 read on resume; stale mirror
predates TDD authorization/base rebase/implementation, so preserved local actual
progress instead of overwriting with old memory. Writes remain host-prohibited.
Draft CA matrix/reproduction file: `docs/evidence/issue-454-historical-attribution.md`;
explicit final-SHA/contract/full-suite/media/PR-review pending markers retained.

Third full suite: 774passed5failed207.26s (not fixture errors). Readiness probe
still required previous schema head, so real migrated API returned503. Existing
health behavior test provided RED before fixing REQUIRED_SCHEMA_VERSION to the
new migration head. Updated existing current-head assertions/restore values to
new head (no historical migration targets existed in replaced occurrences), and
existing exhaustive governed-route matrix with the new admin.read usage scope.
No new post-code unit/regression tests; preserved existing checks and rollback
assertions. Final suite rerun required.

Projection refactor separates public DTOs (`usage_requests_models.py`) from SQL
projection (`usage_requests.py`), preserving closed fields/behavior and enabling
cohesive focused review. First Ruff pass found unused import after separation;
removed, then import spacing flagged and standard formatting applied. Refactor
GREEN repeat pending. Contract manifest/evidence now persisted; new-release
validate exit0, focused test1PASS/test2 required correcting test harness filesystem
path API. Writer finishing focused/full contract suite; runtime still2.7 pending.

Contract focused suite2/2PASS85.8s; generation/new-release validation PASS at
216artifacts18checks. Runtime activation changed to2.8.0 only after observed
activationRED and publishednewtreevalidation; GREEN repeat pending. Public
route prose now distinguishes old invocationlegacy from pre-invocationabsence,
matching implemented explicit states. Contractwriter regenerating hashes for
matching prose and running fullNode/new+historicalreleasechecks.

Activation repeat failed before behavior check because contract writer was
regenerating the tree and manifest temporarily absent (1failed1passed7.38s).
Not a runtime compatibility PASS. Serialize final activation checks after writer
freeze. DTO refactor Ruff lint passed, format required new models file formatting;
mechanical formatter applied. No behavior run in that invocation.

Refactor GREEN22testsPASS38.27s, including attribution, health and governed
contract behavior; `/tmp/issue454-refactor-behavior.log`. Ruff+formatPASS256files,
five importcontractsPASS. Actual provisional HTTPbefore/after and four negative
error bodies validate against the 2.8 release JSONschemasPASS exit0:
`/tmp/issue454-actual-contract.log` (not merely fixture schema checks).
Contractwriter reports 2.8 tree stable/persisted, generation+validatePASS after
prose refresh. Whole active2.8 candidate suite+Alembic launched serially at
`/tmp/issue454-full-active-candidate.log`. No source/test mutation until run ends.

Local checkpoint commits preserve actual design/test-before-source chronology:
`aab4cf4` immutablecapture, `cdd2c99` publicDTOs, `8188c04` sharedselection/refactor,
`c427bf7` dedicatedroute+2.8activation, `775f088` existingfixturecompatibility,
`39eca71` assertion-preserving preauthoredE2E organization, `2d91f28` realHTTP/SQL
driver. These are LOCAL checkpoints, not review-ready exact-SHA evidence; contract
and tracking/evidence content remains uncommitted and whole-suite still running.
Sharedhelper stage was created as an index-only intermediate blob; working-tree
files/test inputs were not modified during the running suite. Planned PR review
slices: capture+fixturecompatibility358 lines, publicDTO+helper261, route280;
all counted additions+deletions, contract-only approved exception separate.
Test publication must preserve all assertions while each true base diff stays
<=400; unpublished prototype reorganization is not a size-waiver precedent.

Whole activecandidate: 1780passed4failed1skipped808.69s. No Alembic check ran
because pytest failed (`/tmp/issue454-full-active-candidate.log`). Failures:
1 historical2.7auditcontract test incorrectly equated currentversion with old;
2 old auditfailure injector patched PostgresAuditStore.append but response now
uses atomic append_response; 3 exacttableinventory omitted request_attributions;
4 defaultmetadata expected2.7. Corrected existing expectations and inject actual
AuditRepository.append failure, preserving quota-settlement/no-success behavior;
kept all2.7auditshape/schema fixtures unchanged. No source workaround for mocks.
No new post-code unit tests. Focused corrections and fullrepeat still required.

All four whole-suite corrections verified: 9testsPASS20.41s, RuffPASS and Alembic
PASS (`/tmp/issue454-regression-corrections-verified.log`). Current2.8runtime
activation/OpenAPI now passes, historical2.7auditshapechecks still pass. Single
whole-suite skip is the explicitly opt-in liveOpenRouter smoke (not enabled;
no authorization for paid calls/new credentials). Finalwhole-suite retry launched
`/tmp/issue454-full-corrected-active.log`, with -rs to record the exact skip.
Nodefullsuite54passes sofar, nested historicalreleasechecks slow but progressing;
not a concrete blocker and no checks skipped/cancelled.

Full contract npm suitePASS130tests/0failures/0skips1700.52s; includes2.8focused
and historicalimmutable-release checks (`/tmp/issue454-contract-npm-test.log`).
CLIhelp updated afterward to advertise2.8 (cosmetic only); invalidargs harness
proved correct help and exit2. Separatevalidate-all underway, no releasecontent
mutation. Authorizedmain refresh now23e1a42dd1f3c0ad98b76ee6f5f25906570d50c2;
fetchedonlymain. Four intervening commits add issueCA1 evidence/proofscripts,
no changes tosrc/tests/migrations/schemas. Preserve all main additions, integrate
only after active Python freeze ends, then recheck resulting candidate.

Final active candidate whole-suite GREEN: 1784passed1skipped655.92s and Alembic
check PASS, no new upgrade operations (`/tmp/issue454-full-corrected-active.log`).
Skip: opt-in live OpenRouter request, RUN_OPENROUTER_LIVE_SMOKE unset; no paid
call. Full Node tooling130/130PASS plus validate-all1.0.0–2.8.0PASS; immutable
historical releases unchanged. Contract writer finished, tree stable. Adding
only sanitized artifact output at the end of the already preauthored canonical
adapter E2E (no new assertions/tests), then targeted repeat before checkpoint.
Memory writes remain runtime-prohibited; local mirror pending.

Current-main integration rebase succeeded without conflicts; retained all CA1
HTTP/restart proof scripts/docs from main. Rebased original design3adefc2 and
preauthored testsb7a3bc5 precede source15325da; provenance branch published.
Existing canonical adapter E2E now emits sanitized actual closed item with
requestedopenai/gpt-4o-mini vs creditedopenai/gpt-4o-mini-20260915;1PASS8.35s.
Initial artifact-only Ruffline/format/fileownership failures fixed, not concealed.
Eight bounded stack drafts published#569–#576; each attached to Codex task and
@codex review requested. Diffs:218,9831,355,261,294,318,294,366lines.
Only contract#570 carries user-authorized size:exception-contract-update.
No merge/closure/human acceptance. Final integrated source tree5f3734277f918231
f7fd4bbff38ed8021239a579 equals original5554059 forsrc/tests/migrations/schemas/
scripts; task docs differ only. Exact-SHA whole quality/tests+actualproof repeat
active `/tmp/issue454-final-python.log`; frozen source until completion.
New2.8validation216artifacts18checks +issue454conformancePASS at exact subtree
(`/tmp/issue454-final-contract.log`); Node22.14/npm10.9.2. Media/finalmatrix and
Codex findings resolution still pending; prefixes not standalone deployments.

Codex current-head reviews: design#569 P2 machine-local runner and stale TDD prose;
contract#570 P1 partial/unavailable status contradictions and P2 lifecycle prose;
roundtrip#574 P2 artifact retention; guards#576 P2 injection before audit insert
insufficient for atomic rollback. Provider#575 no major issues; other reviews
pending readback. Contract P1 correction delegated after current freeze ends.
Failure modes BEFORE correction: unavailable with any available requested/credit;
partial with all credits available or no requested assignment must reject, while
honest partial/missing evidence remains valid. Preauthor observable schema cases,
observe RED, only then tighten new2.8 contract and regenerate only2.8. No old
release changes. Existing rollback E2E has genuine coverage gap: inject AFTER
real AuditRepository.append/flush and assert neither response audit nor snapshot
survives; no new post-code unit test. Reproduction must emit artifacts before
--rm or persist via scoped output bind. Preserve initial checkpoints/reviews and
refresh current candidates/evidence; no semantic acceptance from successful CI.

Exact source5f37342 repeat PASS: Ruff/format258files, lock93packages, five import
contracts, configured mypy12files, full1784PASS1live skip531.25s, Alembic no new
operations; realHTTP/SQLdriver and canonical adapter artifact PASS, outputs
persisted via scoped /evidence bind (`/tmp/issue454-final/`). Python3.12.14,
uv0.8.14/Ruff0.11.7/mypy2.3.1. Contract P1 discovered afterward means these
outputs are honest predecessor evidence, not final corrected contract acceptance.
Current task runner now portable default Compose (no missing /tmp overlay);
actual historical logs used local inspected subnet overlay. Final evidence will
provide exact optional overlay contents without requiring that machine-local file.

Post-insert rollback correction GREEN1PASS9.71s, Ruff/formatPASS; original
preauthored E2E enhanced, no production change. Current-main exact predecessor
hosted#576 configuration-lock/checks-image/unit/static-web/GitGuardian SUCCESS;
contracts still running, pr-governance FAILURE for draft/incomplete evidence.
These statuses do not accept CA1–CA11. Authorized main readback still23e1a42.
Contract P1 RED: five contradictory attribution cases accepted and metadata
stale (`/tmp/issue454-p1-red-observed.log`). New schema rules implemented after
RED; official projection/evidence generation initially wrote only disposable
harness workspace, leaving old persisted projection hashes and causing semantic
drift. Persist NEW2.8 output only; no historic regeneration or validator waiver.
Generation now reports221artifacts18checks; persist/focused GREEN underway.

Corrected contract committed8456756 after five-case RED; only new2.8 schema,
negative fixtures, usage-read lifecycle metadata and regenerated projection/
manifest/evidence changed. Restacked owned drafts with explicit old-SHA leases:
223,10203,355,261,294,318,294,378lines. Complete corrected source candidate
377272ceda8f66e9410060233503b25ee587928f; all producer/tests/schema/script trees
match original provenance branch8456756. Design prefix now includes previously
preauthored TDD prose and portable default runner. Final frozen Python quality/
whole-suite plus actual proof rerun active `/tmp/issue454-final-corrected-python.log`;
contract worker read-only final checks. No source mutations until runners finish.

Second current-head review round: new P2s identify missing safe env preparation/
incorrect historical base in initial planning prefix, append-only injected audit
stores silently accepting provider results without snapshots, and live generated
OpenAPI missing state conditionals although runtime DTO/published schema enforce
these. Genuine consumer/capture gaps are in approved producer scope; fix narrowly,
not broad operational hardening. Pre-code failure scenarios: actual provider call
with an append-only injected store MUST fail closed503/no response audit/snapshot;
actual GET payload MUST validate with live OpenAPI while available/legacy/
unavailable contradictions and all-credit-available partial records reject.
Extend existing roundtrip E2E before live-schema code and preauthor real API/DB
injected-store E2E before changing fallback. Preserve other admin/MCP/pre-invoke
AuditStore append boundaries; no new post-code unit tests. Current frozen run
must finish first; predecessor proof remains traceable, not final acceptance.

Consumer/capture gaps preauthored in ef0c43f BEFORE source fix a23567e: actual
live OpenAPI accepted four contradictory states; append-only injected audit store
returned200 without snapshot. Verified RED2fail17.20s, then GREEN41pass56.96s
with Ruff/format/Alembic. The runtime now fails closed503 when invocation evidence
cannot be stored atomically, without changing admin/preinvoke append boundaries.
Live OpenAPI carries the same closed state conditionals as runtime and new2.8.
Contract focused2/2PASS98.4s; new2.8PASS221artifacts18checks; all14immutable
releases1.0–2.8PASS (~17min). Earlier130/130 tooling run is predecessor-only,
not rerun after P1. No historical release altered or validator weakened.

Final owned drafts restacked/pushed with explicit leases, then @codex review:
#569 e75cb869 (227lines), #570926e0e90 (10203, sole approved exception),
#5714e9b30e3 (357), #572e2a164bb (300), #5734eb86a97 (294),
#5748adb050c (348), #5758bd6e56e (330), #5760f66f99d (378).
Exact complete candidate0f66f99de6636085b70633998e02ef89d8c22871 equals
provenance a23567e for src/tests/migrations/schemas/scripts. Whole quality/
Python suite/real HTTP SQL and canonical artifacts active in isolated Docker
(/tmp/issue454-final-delivery-python.log); freeze source pending result.
Parent ODD backups retained in /tmp; Engram mirror writes unavailable because
runtime identity is not registered. Do not omit session_id or invent a session.

Candidate0f66 verification completed PASS:1785tests1live skip565.72s;
allquality/AlembicPASS, roundtrip1PASS10.54s, canonical1PASS7.72s,
real HTTP/SQL proof persisted. Fresh Codex reviews six drafts no major issues;
contract/read new P2s: exact requested provider/router narrow valid source100
limits; two unavailable-credit negatives accidentally duplicate; audit route
still refers to2.7 error URN while advertising2.8. Fix consequential compatibility
within producer scope after preauthoring: router100 real aliasPUT/invoke/read
must succeed, actual denied-audit body must resolve against advertisedrelease,
and each unavailable credit is independently exercised. Existing activated
schema comparator updated to2.8 without removing assertions. Oldrunner ended;
preauthor tests BEFORE capture/DTO/migration/audit refs, then verified RED.

Compatibility fixture correction: router100 PUT is NOT valid in the current
control plane (router is literal openrouter, persisted CHECK agrees). Initial
3fail1pass12.76s included invalid fixture422 and is NOT claimed capture RED;
first unmounted-source run was also discarded. Broad routing is outside scope.
Reverted unnecessary capture/table widening; preserve those runtime boundaries.
Corrected live-consumer fixture from actual GET checks representability of valid
generic ModelAlias requested fields AzureOpenAI/router100, without pretending
that configuration is currently invokable. Verified consumer RED1fail14.42s
BEFORE requested-public-DTO fix; corrected preauthor commit recorded. Audit
consumer's unresolved2.7 URN was genuine RED; new2.8 reference fixes it. Existing
schema comparator assertions preserved; each unavailable-credit negative isolated.

Final source2a8a3599095bf363ee9c3fa8be4bf89756381813 (provenance2b79302):
quality/AlembicPASS,1785PASS1paid-smokeSKIP543.46s;roundtrip9.43s/canonical7.46s;
realHTTP/SQL/schemaPASS and ten scenario observations persisted before --rm.
Consumer gaps preauthored5ae7e37 before fix2b79302,RED2/GREEN63;UUID P1 false
(JSON-mode validation/dump then JSONResponse);artifact P1 fixed in#577.
CA1–CA11 matrix:docs/evidence/issue-454-historical-attribution.md;drafts569–577
plus bounded evidence/tracking follow-ups. Sole size exception570;no UI143,
merge,closure or human acceptance. Source scope verified;humanreview pending.
Engram mirror unavailable (unregistered runtime identity). App attach577 attempted
but not confirmed after tool hang;new draft attachment calls still required.
