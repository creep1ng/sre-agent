# Shared OTel Demo EC2 PR stack

## Objective and authorization

Publish the existing temporary, shared OTel Demo EC2 launcher as a sequence of
feature-branch PRs that resolve #494 when integrated. The user authorized local
implementation and GitHub issue/PR publication in `creep1ng/sre-agent`; this
work does not authorize new AWS operations. Partial PRs reference, but do not
close, #494.

## Problem, scope, and constraints

The prepared launcher spans seven untracked files and 2,801 lines in another
worktree. No single PR may exceed 400 additions plus deletions under the
current contributor instructions. The repository is public: omit real AWS
account/resource IDs, email addresses, and credentials from committed files
and evidence. Preserve the unrelated dirty issue-45 worktree. Keep every PR
independently parseable, reviewable, and backed by a real screenshot and
containerized reproduction. The historical September AWS run is not fresh
October evidence. Use distinct stacked feature branches and tested SHAs.

## Route and verification

Route: delegated direct for multi-file implementation; no SDD requested.
TDD mode: no explicit mode setting found; supplied AGENTS.md requires tests
before new code, preferring E2E. Existing candidate tests were authored before
this publication work. Runner: `docker compose --profile checks run --build
--rm python-checks pytest -q ...` with safe local Compose configuration.
RDD: disabled by the global setting; ordinary policy applies.

## Tasks

- [ ] **OTEL-PR-1** Isolate/sanitize the candidate and define stable module and
  stack boundaries; confirm each proposed PR diff is at most 400 lines.
- [x] **OTEL-PR-2** Publish independently valid IAM/network infrastructure
  slice with scoped operator access and containerized structural checks.
- [x] **OTEL-PR-3** Publish the Scheduler/instance and monthly-budget
  infrastructure slices, preserving least-privilege references.
- [x] **OTEL-PR-4** Publish the account bootstrap/profile lifecycle with
  fail-closed identity and secret handling checks.
- [x] **OTEL-PR-5** Publish the pinned guest bootstrap and cost/deadline
  primitives with applicable checks.
- [ ] **OTEL-PR-6** Publish the AWS adapter in cohesive, independently checked
  slices (identity/network/cost, then lifecycle/SSM/Scheduler).
- [ ] **OTEL-PR-7** Publish the session controller and CLI in cohesive slices,
  demonstrating shared reuse, bounded extension, SSM-only access, and cleanup.
- [ ] **OTEL-PR-8** Publish sanitized operator documentation, full
  containerized verification, and final #494 criterion mapping.

## Acceptance and progress

Each PR is <=400 additions+deletions against its actual base; has a unique
head SHA, `Refs #494` until the final complete PR, complete evidence fields,
real HTTPS screenshot, Docker reproduction, and explicitly pending criteria.
No PR claims live AWS validation from this publication session. Final PR may
close #494 only when all criteria and independent human review are satisfied.

Current progress: issue #494 created and added to GitHub Project #8; source
candidate located and base `ef5ba500e673160aa73d92fffc61ee452c284bc6`
fetched. No PR branch pushed yet. Next: sanitize and split in this isolated
clone, then verify each candidate before publication. PR #495 published the
operator template at 350 changed lines; offline container YAML parse passed at
`698630568b9c5b6acc50e7f3ad1bce71ed5427a3`. Human review and AWS
validation remain pending. PR #496 published the runtime and budget
stacks at 206 changed lines; offline container readback passed at
`a24f4391bb4edfcecf03626186f2e40ccb779a3c`. PR #503 published
the no-apply-guarded bootstrap at 385 changed lines; full behavior checks
remain pending in the next slice. PR #504 published nine
bootstrap fake-runner scenarios at 330 changed lines; pytest and Ruff passed
at `c12407efe5578ab70c0773f0d17bfb90285bd57b`. PR #505 published
policy-template checks at 239 changed lines; 17 offline pytest checks passed at
`9265b864c501190d90c2e438774fa0312d7afa84`. PR #506 published guest
deadline primitives at 290 changed lines; networkless Docker confirmed Bash syntax,
expiry-before-network ordering, and 8019-byte user-data at
`fdf8d014ab86450af6dab9623cae07f39771fc6a`.
