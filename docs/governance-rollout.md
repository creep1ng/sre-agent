# Governance rollout and recovery

Issue #183 delivers governance configuration, reproducible container checks, and minimal browser harness coverage. Public contracts and migrations remain unchanged; no architectural reorganization is part of this rollout. RDD is optional and is
not enabled by this rollout. The implementation starts at integrated main
`a21d8914cafbf2a291d78b1ac641726b48f12501`; recheck the current default branch before
publication instead of assuming another task's work has landed.

## Deployment state

- Shared workflow, evidence template, metadata policy, locked images, import/type gates, production-image browser stage and diagnostics: published as a draft PR stack. Local verification includes the static browser lane (2/2), production-image browser lane (4/4) with no API/web source mounts or host ports, and a bounded authorization mutation run (83/83 killed); hosted checks are pilot evidence, not active merge protection.
- Native GitHub secret scanning and push protection: enabled with API readback.
- Required quality checks, stale-approval dismissal and governance review:
  **enforcement partial**, pending administrative activation after the live pilot.
- `pr-governance` metadata check: retired by #1081. It validated the shape of the PR
  description, not delivery. The slice table below still lists it as slice 3 because that table
  records how #183 was published.
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

Slice 5 exceeds the original 400-line planning target because
the generated lockfile, while its non-lock companion changes are the minimum
consumer/configuration changes needed to validate that lock. Stage `compose.yaml` by hunk: its three digest
replacements (6 changed lines) belong to slice 5; its 51-line E2E block belongs
to slice 7. Do not combine the total worktree into one review unit.

Do not change live settings or merge as part of this record.

Publication planning for #183 is authorized, but every actual PR still needs
current-base metadata and maintainer review. CI requires no approval comment,
label, or commit confirmation. Partial deliveries reference, rather than close, #183.

The [local validation record](archive/governance-pilot.md) separates executed checks from
remaining hosted and human acceptance evidence.

## Pilot before required checks

Use a team-authorized sandbox for hosted negative
cases, or a real contribution for the positive path; do not manufacture noisy PRs
against production. Local API simulations complement but do not replace this pilot.

Record candidate/base/tested SHA, workflow URL, observed status and a sanitized screenshot of the actual acceptance result for these scenarios. A video is optional; use its real link or the documented no-video sentence, never a fabricated URL:

- Manifest/lock mismatch, direct/indirect forbidden import against a copied candidate, and scoped type mismatch fail their respective stage.
- Candidate API/web images run with no source mount or host ports; the ordinary and bad-proxy browser scenarios pass/fail as designed.
- Failure, cancellation, skip or missing mandatory CI job fails Quality gate.
- A later push dismisses approval after ruleset activation.
- A reviewer rejects structurally present but irrelevant evidence.
- Another contributor reproduces the result without author assistance.

## Administrative activation

Only after the hosted pilot succeeds, obtain the maintainer's explicit activation
confirmation. Export both rulesets and repository security settings to a private,
durable operator backup. The initial local pre-state is in
`/tmp/issue183-admin-backup`; temporary storage is not a disaster-recovery archive.

1. Read the live check-run/status names and GitHub App identities on the exact pilot
   head. Require `Quality gate` (check run), bound to the observed GitHub Actions integration. Never guess a display
   prefix or use a similarly named check from another application.
2. In quality ruleset `20580391`, require current-base successful checks, `0` native
   required approvals, stale-review dismissal, latest-push approval and resolution of
   conversations. The maintainer's merge decision is the human acceptance step. Remove blanket quality
   bypass. Preserve existing deletion, force-push and allowed-merge-method rules.
3. Preserve merger-authorization ruleset `21689570` unchanged.
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
