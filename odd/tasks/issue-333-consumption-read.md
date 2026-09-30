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
- [ ] **U333-7 — Enforce cost and coverage contract invariants.**
  Reproduce contradictory cost metadata and coverage status/count examples;
  couple non-null amount to USD/exact and null amount to null metadata. Counts
  describe distinct requests and sum to request_count; status reflects counts.
  Use semantic validation for arithmetic, not a false JSON Schema claim.
  Checks: conformance negatives/positives plus runtime acceptance.
- [ ] **U333-8 — Publish and activate an additive contract.**
  Publish a self-contained next release containing the delivered usage route
  and usage.read audit operation; activate it without editing 2.4.0.
  Pending: next-version coordination and NEW publication-size exception.
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
  No issue-333-related PR remains open. Project 8 was read live before scoping.
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

## Next step

Independently verify the normalized candidate and bind/publish its tested SHA and evidence.
Keep U333-8 blocked on its scoped size/version decision; continue independent
safe tasks without narrowing the full objective.
