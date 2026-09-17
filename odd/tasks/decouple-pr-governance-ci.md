# Decouple PR governance failures

## Objective

Keep the repository-wide PR governance reconciliation while preventing one invalid open PR from making the aggregate workflow check appear to fail for every other PR.

## Problem and rationale

The trusted governance job validates every open PR and publishes a candidate-bound `pr-governance` commit status, but it also calls `core.setFailed` when any candidate has policy errors. That conflates an individual PR's policy result with the reconciler's operational health and makes unrelated PRs look broken.

## Authorized scope

- Local source and test changes for the PR governance reconciler.
- Preserve candidate-bound `pr-governance` statuses and global scheduled reconciliation.
- Add focused regression coverage for policy failures versus operational failures.
- Do not modify remote rulesets or other PRs without separate authorization.

## Constraints

- Strict TDD is enabled by `AGENTS.md`: observe RED, then GREEN, then REFACTOR for the implementation task.
- Preserve the existing trusted-default-branch checkout and metadata-only validation boundaries.
- Do not weaken candidate policy statuses; invalid candidates must remain `failure`.
- Keep unrelated uncommitted work untouched.
- RDD is user-owned and remains unchanged.

## Verification

- RED/GREEN focused runner: `node --test tests/pr-evidence-policy.test.cjs` (or the repository's equivalent Node invocation if the test file remains assertion-style).
- Run the broader governance/CI tests selected by the implementation worker.
- Structural readback of the workflow and validator after normalization.

## Checklist

- [x] **T1 — Separate policy and operational outcomes.** Refactored `run()` so candidate policy failures publish candidate-bound statuses and summaries without failing the aggregate job; API/snapshot/status publication failures still fail the job.
- [x] **T2 — Add regression tests.** Proved an invalid candidate does not call `core.setFailed`, while an operational error does; preserved existing validation coverage.
- [x] **T3 — Verify repository boundaries.** Ran focused checks, performed structural readback, inspected the diff, and documented that live branch-protection ruleset verification remains a separate remote operation.

## Acceptance criteria

- A policy-invalid open PR receives `pr-governance: failure` on its own head SHA.
- The aggregate governance workflow remains successful when reconciliation completes despite policy-invalid candidates.
- A failure to inspect a candidate or publish its status still fails the aggregate workflow.
- The functional CI workflow remains isolated by PR number.
- Existing status deduplication, duplicate-SHA fail-closed behavior, and trusted-code boundaries remain unchanged.

## Progress

- Exploration verified that `.github/workflows/ci.yml` isolates functional CI by PR number, while `.github/governance/pr-evidence.cjs` aggregates all open-PR policy failures into one `core.setFailed` result.
- Task document created before source edits; prior unrelated worktree changes are preserved.
- Added RED regression coverage for policy-invalid and operational candidates; the focused test initially failed because policy errors called `core.setFailed`.
- Implemented the smallest separation: only operational reconciliation failures increment the aggregate failure count; policy-invalid candidates still publish `failure` and summary entries.
- GREEN/refactor checks passed with `node --test tests/pr-evidence-policy.test.cjs`, `node --check .github/governance/pr-evidence.cjs`, and `git diff --check`.
- Broader Python governance tests were attempted with `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run --frozen pytest -q tests/test_governance_dto.py tests/test_governed_authorization.py` but could not run because the sandbox could not download the uncached `websockets==17.0.1` dependency (DNS unavailable).
- Structural readback confirmed the trusted governance workflow still checks out the resolved default branch and that functional CI remains keyed by PR number in `.github/workflows/ci.yml`.
- Live branch-protection ruleset verification was not performed because remote authorization was not provided.

## Next step

Local implementation and verification are complete. A maintainer may authorize a separate remote ruleset readback before delivery; no commit or remote operation was performed.
