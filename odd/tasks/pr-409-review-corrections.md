# PR #409 stack review corrections

## Objective
Resolve all live Codex review findings across the ten-PR issue #331 stack, mark corrected review threads resolved, and verify current-head CI green on every PR.

## Authorized scope
- Authorized GitHub CLI session for reading the stack, publishing corrections, resolving threads, and monitoring CI (user confirmed "Sí, autorizo ese alcance").
- Work isolated in `/tmp/sre-agent-pr409-recovered`; the original dirty worktree stays untouched.
- Preserve stack order #387 → #388 → #397 → #403 → #402 → #404 → #405 → #406 → #407 → #409. No merges, no issue #331 closure, no auto-applied labels.

## Tasks
- [x] PR387 — adopt compatible pre-existing catalog Skill rows; refuse foreign owners and non-draft lifecycle states.
- [x] PR403 — restore the surviving parent's `usage.read` constraint on downgrade to revision 17; block only unsupported operations.
- [x] PR402 — recovery read for the lifecycle CAS token (`GET /v1/skills/{skill_id}/{version}/status`, admin.write); audited 404 retained for absent versions.
- [x] PR404 — restrict the resolution migration downgrade blocker to resolution evidence and restore the revision-18 constraint.
- [x] PR405 — audited 422 for malformed paths, documented success/error envelopes, Bearer 401 challenge, normalized persistence failures, retryable 503.
- [x] PR406 — declare 422/503 with the runtime error model and fail persistence closed while reusing one authenticated context.
- [x] PR407 — attach the referenced lifecycle-proof evidence artifact.
- [x] PR409 — replace SQL/repository call-count spies with observable HTTP/PostgreSQL denial and correlated-audit assertions.
- [x] STACK — corrections published onto current remote heads with lease-protected force pushes; exact-SHA evidence refreshed; all review threads resolved.
- [ ] HOSTED CI — green on all ten current heads (blocked: GitHub stopped creating `pull_request` CI runs repo-wide at 15:18 UTC).

## Current remote heads (2026-09-30)
| PR | head | base |
| --- | --- | --- |
| 387 | `402ff6e` | `5b6109b` (main) |
| 388 | `c0d8076` | `402ff6e` |
| 397 | `892e802` | `c0d8076` |
| 403 | `e36b04e` | `892e802` |
| 402 | `87710c6` | `e36b04e` |
| 404 | `18669cb` | `87710c6` |
| 405 | `803910e` | `18669cb` |
| 406 | `44c2033` | `803910e` |
| 407 | `fdc1520` | `44c2033` |
| 409 | `7acf7a2` | `fdc1520` |

Every PR body now records its exact current `Tested SHA` and `Base SHA`.

## Review threads
- First inventory: 18 unresolved Codex threads (#397 2, #403 1, #402 3, #404 2, #405 5, #406 2, #407 1, #409 2). All 18 resolved after their fixes were published.
- A second review wave produced 5 more findings (evidence/SHA accuracy, size approval, lifecycle-state adoption, governed-operation inventory, retryable 503). All 5 fixed and resolved.
- Current live inventory across all ten PRs: **0 unresolved threads**.

## Local verification (disposable Compose project `pr409-owner-checks`, subnet 10.253.248.0/28, cached checks image, candidate mounted read-only at `/candidate` with `PYTHONPATH=/candidate/src`)
- #397 publication: 8 passed (adoption + refusal of active/inactive/revoked states, RED verified before the fix).
- #402 activation/scope/inventory: 5 + 15 + governed-operation contract passed.
- #403 migrations + compatibility: 22 passed; #404 migrations + compatibility: 30 passed.
- #405 resolution: 6 passed; #406 resolution: 11 passed; #407 lifecycle proof: 1 passed; #409 resolution + demo: 12 passed.
- #387 head: 38 focused passed, 1222 passed / 1 skipped full. #388 head: 47 focused passed, 1224 passed / 1 skipped full. The single skip is the optional OpenRouter smoke (`RUN_OPENROUTER_LIVE_SMOKE`).
- Ruff lint/format and `git diff --check` clean on every touched path.

## Hosted CI status
- `pr-governance` and `reconcile` pass on all ten PRs at their current heads.
- Since 2026-09-30 15:18 UTC GitHub has not created any new `pull_request` CI run for this repository on any branch (verified with an empty-commit push to #409 that produced no run, and a close/reopen cycle that produced only `pull_request_target` runs). `pull_request_target` and GitGuardian runs continue normally; workflow state is `active`; no GitHub platform incident is published.
- Therefore current-head hosted CI is **not yet green** for the eight updated PRs, and the objective is not complete.

## Next step
Re-check CI once GitHub resumes creating `pull_request` runs; if it does not, escalate to the user for a decision (for example an explicit re-dispatch once the workflow can be triggered manually). Do not merge or close issue #331.