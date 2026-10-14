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
this publication work. Runner: `docker compose --profile checks build python-checks` followed by
networkless `docker run ... pytest -q ...`; Compose `run` cannot allocate a
subnet on this host. Tests from exact detached SHA checkouts use synthetic
AWS runners and no credentials.
RDD: disabled by the global setting; ordinary policy applies.

## Tasks

- [x] **OTEL-PR-1** Isolate/sanitize the candidate and define stable module and
  stack boundaries; confirm each proposed PR diff is at most 400 lines.
- [x] **OTEL-PR-2** Publish independently valid IAM/network infrastructure
  slice with scoped operator access and containerized structural checks.
- [x] **OTEL-PR-3** Publish the Scheduler/instance and monthly-budget
  infrastructure slices, preserving least-privilege references.
- [x] **OTEL-PR-4** Publish the account bootstrap/profile lifecycle with
  fail-closed identity and secret handling checks.
- [x] **OTEL-PR-5** Publish the pinned guest bootstrap and cost/deadline
  primitives with applicable checks.
- [x] **OTEL-PR-6** Publish the AWS adapter in cohesive, independently checked
  slices (identity/network/cost, then lifecycle/SSM/Scheduler).
- [x] **OTEL-PR-7** Publish the session controller and CLI in cohesive slices,
  demonstrating shared reuse, bounded extension, SSM-only access, and cleanup.
- [x] **OTEL-PR-8** Publish sanitized operator documentation, full
  containerized verification, and final #494 criterion mapping.
- [x] **OTEL-PR-9** Close #494 acceptance gaps found in post-publication audit:
  `up` reuses a live scheduled session, and `down` is idempotent when absent;
  observe failing behavior checks before the fix and repeat focused Docker checks.
- [x] **OTEL-PR-10** Address PR #513 review finding: a first empty EC2 lookup
  during `down` must not signal success if a just-launched shared instance
  becomes visible on retry. Observe RED before implementation; keep retries
  bounded and preserve the absent-session no-op; repeat exact-SHA Docker checks,
  refresh PR evidence and respond to the review comment.

## Acceptance and progress

Each PR is <=400 additions+deletions against its actual base; has a unique
head SHA, `Refs #494` until the final complete PR, complete evidence fields,
real HTTPS screenshot, Docker reproduction, and explicitly pending criteria.
No PR claims live AWS validation from this publication session. Final PR may
close #494 only when all criteria and independent human review are satisfied.

Current progress: issue #494 is in GitHub Project #8. Published stacked PRs
#495, #496 and #503–#512, each with distinct feature branch, real screenshot,
Docker reproduction and no live-AWS claim. All observed PR diffs are under
400 additions plus deletions against their current base. PR #504 fixed the
CI pytest import path after the hosted unit job failed collection; the fix
was merge-forwarded without force-pushing through PR #512. Original behavior
source and tests stayed unchanged during propagation. PR #513 on `codex/otel-demo-ec2/13-shared-reuse` verifies shared reuse
and idempotent teardown. An exact-checkout networkless Docker run passed
59 focused tests and Ruff across 17 files with no PYTHONPATH override or
infra mount after the inherited CI fixes. #494 criterion mapping is recorded
at https://github.com/creep1ng/sre-agent/issues/494#issuecomment-6039022455. Two new
acceptance checks were observed RED before the fix; at source SHA
`641a713`, exact-checkout networkless Docker reported 59 focused passes and
Ruff passed 17 files without a PYTHONPATH override.

Next: obtain independent human review and, with separate authorization, live
AWS validation. PR #505 also copied infra
into the checks image after hosted unit tests found a missing template; the
fix was merge-forwarded through PR #513 without force-push. Live AWS
provisioning, Scheduler firing, SSM forwarding and billing controls are
not validated in this publication session; the issue remains open.

Review finding in #513 (discussion_r4207554947): EC2 `DescribeInstances`
is eventually consistent, so the first empty lookup after launch is not
reliable evidence of absence. The two updated behavior checks were RED against
the prior controller (`2 failed` because only one lookup occurred). `down` now
uses the same host lock as `up` and retries absent lookups with 2/4/8/16-second
backoff before returning an absent-session no-op. Exact behavior-source SHA
`c58b70314c509d385994f6e2e28e9b072bcad033` passed 60 focused tests,
Ruff lint and format in networkless Docker; three named teardown checks also
passed. A real screenshot was inspected and committed; PR #513 evidence was
refreshed, validated with the local governance parser (under 400 changed lines,
no metadata errors), and the reviewer comment was answered at
https://github.com/creep1ng/sre-agent/pull/513#discussion_r4207780039.
Repeated empty responses are still not proof of absence; Scheduler and guest
deadline remain fallbacks. Hosted live AWS behavior and human acceptance remain
pending.
