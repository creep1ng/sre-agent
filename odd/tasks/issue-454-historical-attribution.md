# Issue #454 — Historical request attribution

## Objective, problem and why

Deliver the backend producer for all CA1–CA11 of #454: authorized historical
request attribution survives mutable alias reassignment without exposing content.
Existing usage accounting and audit navigation are not historical attribution.

## Scope and authority

- Route: delegated direct Organic Driven Development; no SDD artifacts.
- Branch: `codex/issue-454-historical-attribution`.
- Current base: `23e1a42dd1f3c0ad98b76ee6f5f25906570d50c2` (fetched main).
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
- [ ] **A454-2 — Preauthor behavior scenarios and formalize contract.**
  Closed bounded selection/attribution/error/navigation contract; immutable-release
  governance; preauthor real HTTP/PostgreSQL tests for CA1–CA9 and alias races,
  canonical OpenRouter credit, legacy/no evidence, denied and invalid reads.
  Checks: observed RED if TDD enabled; new-release schema/conformance validation.
- [ ] **A454-3 — Implement immutable capture and provider evidence.**
  Migration, separate append-only persistence, exact routing snapshot, distinct
  requested/credited fields and explicit absence; audit HMAC behavior unchanged.
  Checks: capture/race/rollback/migration behavior and relevant adapter regressions.
- [ ] **A454-4 — Implement authorized dedicated request projection.**
  Reuse authoritative bounded selection/dedup; no duplicate accounting; server-only
  historical resolution; no current alias inference; contract-admitted navigation.
  Checks: selectors/auth/sanitization/legacy/overflow and consumption regressions.
- [ ] **A454-5 — Verify current integrated candidate.**
  Lint/types/contracts/full applicable tests/migration and recoverable corrections.
  Checks: actual commands/results at exact source SHA; record skipped/failed checks.
- [ ] **A454-6 — Demonstrate CA1–CA11 with repeatable real evidence.**
  Docker Compose real API/PostgreSQL run/read/reassign/reread, negative responses,
  sanitized actual screenshot, exact SHA/environment/preparation/commands and
  expected-vs-observed matrix. Clearly identify controlled provider and pending
  independent human review. Checks: repeat reproduction and inspect artifacts.
- [ ] **A454-7 — Prepare review-ready draft delivery.**
  Cohesive PRs within size policy or explicit exception; Refs #454/143 only.
  Request Codex GitHub code review for every PR, fix P0/P1, check candidate/CI and
  attach PRs. No merge/closure or invented human acceptance. Checks: remote readback.

## Progress and next step

Live issues/comments/Projects read and main fetched; existing mechanisms inspected.
A454-1 decision recorded in `docs/design/issue-454-historical-attribution.md` before
production edits; parent readback/approved-comment reconciliation/diff hygiene PASS.
No independent human acceptance claimed. No production implementation yet.
Baseline Responses/OpenRouter/usage acceptance: 120 passed in 62.69s, exit 0,
real isolated PostgreSQL and controlled providers, unchanged source at base878a0b2.
Design-first commit `de9701d9a85c06470fc796609d3a42f2db0ccb7a` records A454-1.
Default Docker address pools exhausted; temporary network
overlay `/tmp/sre-agent-issue454-network.yaml` uses inspected free 10.253.144.0/28
without removing unrelated networks. Logs: `/tmp/issue454-baseline.log`.
Next: A454-2 preauthor acceptance scenarios/contract; user authorized TDD.
Mirror status: PENDING. Host lost registered runtime session identity on resume;
agent-attributed Engram writes are forbidden until host re-registers the same ID.
Retain local progress; read mirror9911 as older state, do not invent a new session.

The runner above uses only checked-in Compose services. The exhausted-pool
workaround in historical logs is machine-local, not a required reproduction
input. If needed, select an unused subnet and use an optional Compose overlay;
the final evidence record provides the exact public YAML contents.
