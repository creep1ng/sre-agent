# Governance rollout and recovery

Issue #183 delivers governance configuration, reproducible container checks, and minimal browser harness coverage. Public contracts and migrations remain unchanged; no architectural reorganization is part of this rollout. RDD is optional and is
not enabled by this rollout. The implementation starts at integrated main
`a21d8914cafbf2a291d78b1ac641726b48f12501`; recheck the current default branch before
publication instead of assuming another task's work has landed.

## Deployment state

- Shared workflow, evidence template, metadata policy, locked images, import/type gates, production-image browser stage and diagnostics: published as a draft PR stack. Local verification includes the static browser lane (2/2), production-image browser lane (4/4) with no API/web source mounts or host ports, and a bounded authorization mutation run (83/83 killed); hosted checks are pilot evidence, not active merge protection.
- Native GitHub secret scanning and push protection: enabled with API readback.
- Required quality/evidence checks, stale-approval dismissal and governance review:
  **enforcement partial**, pending administrative activation after the live pilot.
- Team onboarding, responsible reviewers and estimation: human coordination remains
  required. Keep assignees/labels in GitHub, SP and capacity in Projects, and
  dependencies in native `blocked by`/`blocks`; do not invent planning metadata.

The current quality ruleset is `20580391`; merger authorization is separately
controlled by `21689570`. Do not remove the latter's administrator exception or
silently expand who may integrate. Neither ruleset was changed in this delivery.

## Publish in reviewable work units

The current worktree totals **3,082 additions + 270 deletions = 3,352 changed
lines across 34 files**, including untracked files. Count again against each PR
base before publication. Use these cohesive slices; every slice except the locked
dependency slice is at or below 400 changed lines.

| Order | Slice | Changed lines | Dependency / rollback boundary |
| --- | --- | ---: | --- |
| 1 | PR evidence guide | 139 | Standalone policy reference; no runtime change |
| 2 | Team baseline and OpenSpec context | 289 | Depends on 1 because it links the guide; revertable documentation/configuration |
| 3 | Template and trusted PR metadata policy | 365 | Depends on 1; the helper, workflow and fixture land together |
| 4 | CI control inventory | 120 | Documentation-only inventory for later CI slices |
| 5 | Locked runtime/check dependencies | 1,286 | `uv.lock` contributes 1,154 lines; includes the 6-line pinned database-image hunks and the minimum checks-image configurations that Docker copies |
| 6 | Import-boundary regression proof | 86 | Depends on 5, which supplies the copied Import Linter configuration |
| 7 | Production-image browser topology | 130 | Depends on 5; includes the 52-line `compose.yaml` E2E hunks, runner and browser seams |
| 8 | Mandatory CI DAG and final gate | 373 | Depends on 5–7; workflow integration and its container-interface regression proof |
| 9 | Informational diagnostics | 357 | Depends on 5; separate Node/Python audits, coverage and authorization mutation reporting |
| 10 | Pilot record and rollout | 207 | Depends on completed local/hosted evidence; documentation only |

Slice 5 needs the explicitly authorized `size:exception`: the overage comes from
the generated lockfile, while its non-lock companion changes are the minimum
consumer/configuration changes needed to validate that lock. Do not use that
exception for any other slice. Stage `compose.yaml` by hunk: its three digest
replacements (6 changed lines) belong to slice 5; its 51-line E2E block belongs
to slice 7. Do not combine the total worktree into a wholesale exception.

The trusted `pr-governance` workflow loads its helper from the default branch,
not the PR candidate. It therefore cannot validate its own first landing. Bootstrap
slice 3 through ordinary independent review, then run the hosted pilot before
requiring `pr-governance` as a protected context.

Publication planning for #183 is authorized, but every actual PR still needs
current-base metadata and ordinary independent review. The only requested
size exception is slice 5; record its live label, rationale and maintainer
approval on that PR only. Partial deliveries reference, rather than close, #183.

The [local validation record](governance-pilot.md) separates executed checks from
remaining hosted and human acceptance evidence.

## Pilot before required checks

The trusted metadata helper must first land on the default branch. Its workflow
never loads helper code from a PR even during bootstrap. Do not change that rule
just to make the first PR green. Use a team-authorized sandbox for hosted negative
cases, or a real contribution for the positive path; do not manufacture noisy PRs
against production. Local API simulations complement but do not replace this pilot.

Record candidate/base/tested SHA, workflow URL, observed status and a sanitized screenshot of the actual acceptance result for these scenarios. A video is optional while media storage is unavailable; use its real link or the documented deferral, never a fabricated URL:

- 400 lines pass; 401 without exception fail; valid exception passes only size.
- Remove the label or edit/delete the approving comment: the status fails again.
- Missing screenshot or commands fails; a video passes only as a real link or the documented storage deferral; empty templates fail.
- Change base/head: recompute size and require current evidence/confirmations.
- Wrong-role, bot and self approvals cannot satisfy independent review.
- Manifest/lock mismatch, direct/indirect forbidden import against a copied candidate, and scoped type mismatch fail their respective stage.
- Candidate API/web images run with no source mount or host ports; the ordinary and bad-proxy browser scenarios pass/fail as designed.
- Failure, cancellation, skip or missing mandatory CI job fails Quality gate.
- A later push dismisses approval after ruleset activation.
- PR commands/URLs containing shell syntax never execute or get downloaded.
- A reviewer rejects structurally present but irrelevant evidence.
- Another contributor reproduces the result without author assistance.

GitHub status updates are asynchronous. Base/permission changes are additionally
reconciled on a 15-minute schedule that GitHub may delay. Manually dispatch and
wait for a fresh result after revocation; do not claim an atomic merge-time check.

## Administrative activation

Only after the hosted pilot succeeds, obtain the maintainer's explicit activation
confirmation. Export both rulesets and repository security settings to a private,
durable operator backup. The initial local pre-state is in
`/tmp/issue183-admin-backup`; temporary storage is not a disaster-recovery archive.

1. Read the live check-run/status names and GitHub App identities on the exact pilot
   head. Require `Quality gate` (check run) and `pr-governance` (commit status),
   binding each to the observed GitHub Actions integration. Never guess a display
   prefix or use a similarly named check from another application.
2. In quality ruleset `20580391`, require current-base successful checks, one
   independent approving review, stale-review dismissal, latest-push approval and
   resolution of conversations. Remove blanket quality bypass. Preserve existing
   deletion, force-push and allowed-merge-method rules.
3. Preserve merger-authorization ruleset `21689570` unchanged. The metadata policy
   separately requires a human write/maintain/admin collaborator's candidate-bound
   confirmation when governance files change; it does not grant merge permission.
4. Read both rulesets back and exercise a real blocked integration. Export the
   effective rule and evidence. Only then replace "enforcement partial" with the
   exact activated state. Never assert protection from YAML presence alone.

**Recovery:** if a required check name or rollout is broken, an authorized admin
restores only the affected quality-rule fields from its reviewed pre-state,
records the reason and marks enforcement partial. Leave unrelated merge authority
and security settings intact. Do not add a permanent emergency bypass.

Secret-scanning enablement had its pre-state recorded and was confirmed by API.
Do not routinely disable it as rollback for a workflow issue. If a secret leaks,
revoke/rotate it first and follow incident response; deleting a screenshot does not
revoke a credential. A maintainer triages security alerts and the weekly diagnostic
findings, assigning remediation separately rather than hiding failures.

## Retention and diagnostics

CI retains sanitized candidate-bound aggregate results for 30 days. Keep acceptance
media in durable, access-appropriate links reviewed by a human. Do not upload raw
request/response traces, production data, environment files or entire service dumps.
Coverage and dependency audits are informative, with no invented thresholds or
automatic dependency edits. See [CI controls](ci-controls.md).
