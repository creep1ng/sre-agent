# Pull-request acceptance audit — 2026-09-29 UTC

**Result: 7 merged; 28 left open with actionable reviews.** Every one of the 35 initial ready PRs has a posted report. **Final-main hosted CI passed all eight jobs**, including contracts and production-browser. [Run](https://github.com/creep1ng/sre-agent/actions/runs/36521826587) · [Exact-SHA hosted report](results/hosted-ci.md).

Initial scope: **35 open, non-draft PRs** in `creep1ng/sre-agent`. Six drafts were excluded: #365, #366, #367, #368, #382, #420. The inventory was captured before any audit merge.

This branch contains **evidence only**, not application changes. Reports separate actual source/SQL/HTTP/browser observations, controlled faults, mocked browser transport, real provider calls, hosted CI, and unperformed checks. Automated review is not represented as independent human assessment. Integration, where later recorded, follows the maintainer’s explicit conditional instruction for this audit.

## Results by PR

| PR | Audit disposition | Full report and evidence |
| --- | --- | --- |
| [#370](https://github.com/creep1ng/sre-agent/pull/370) | Pending: Grafana browser CA5 not demonstrated; cause unattributed. | [Report](runtime/pr-370.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#371](https://github.com/creep1ng/sre-agent/pull/371) | **Merged** — [`e81c66b8`](https://github.com/creep1ng/sre-agent/commit/e81c66b8c3132b32bb3be090fc93dcc15863c49b) | [Report](triage/pr-371.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#372](https://github.com/creep1ng/sre-agent/pull/372) | **Merged** — [`5b6109bd`](https://github.com/creep1ng/sre-agent/commit/5b6109bd2c8100455136cf12ce91c52830833c7f) | [Report](triage/pr-372.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#373](https://github.com/creep1ng/sre-agent/pull/373) | Blocked: conflict with current main. | [Report](triage/pr-373.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#374](https://github.com/creep1ng/sre-agent/pull/374) | Blocked by conflicting parent #373. | [Report](triage/pr-374.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#378](https://github.com/creep1ng/sre-agent/pull/378) | Blocked: conflict and published path contract mismatch. | [Report](triage/pr-378.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#379](https://github.com/creep1ng/sre-agent/pull/379) | Blocked by #378; injected failure evidence is labeled. | [Report](triage/pr-379.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#380](https://github.com/creep1ng/sre-agent/pull/380) | Blocked by #373/#374 dependency integration. | [Report](triage/pr-380.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#385](https://github.com/creep1ng/sre-agent/pull/385) | Changes: routing references missing from audit detail. | [Report](triage/pr-385.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#386](https://github.com/creep1ng/sre-agent/pull/386) | Changes: routing visibility coverage and parent fix pending. | [Report](triage/pr-386.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#387](https://github.com/creep1ng/sre-agent/pull/387) | Blocked: conflict with current main. | [Report](skills/pr-387.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#388](https://github.com/creep1ng/sre-agent/pull/388) | Blocked by #387. | [Report](skills/pr-388.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#389](https://github.com/creep1ng/sre-agent/pull/389) | Changes: same alert can declare two incidents. | [Report](triage/pr-389.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#390](https://github.com/creep1ng/sre-agent/pull/390) | Changes: live proof passes, but authored guide recommends destructive teardown and host-only demonstration. | [Report](runtime/pr-390.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#391](https://github.com/creep1ng/sre-agent/pull/391) | Changes: invalid types persist or return503; duplicate declaration inherited. | [Report](triage/pr-391.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#392](https://github.com/creep1ng/sre-agent/pull/392) | Changes: stale fields leak across UI operations. | [Report](triage/pr-392.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#393](https://github.com/creep1ng/sre-agent/pull/393) | Changes: inherited operation-switch failure remains. | [Report](triage/pr-393.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#396](https://github.com/creep1ng/sre-agent/pull/396) | **Merged** — [`e0f2f3e8`](https://github.com/creep1ng/sre-agent/commit/e0f2f3e8fabff57bcfcea7ae95ce810f0b9d45f4) | [Report](runtime/pr-396.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#397](https://github.com/creep1ng/sre-agent/pull/397) | Changes: long version returns500. | [Report](skills/pr-397.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#402](https://github.com/creep1ng/sre-agent/pull/402) | Changes: audit failure leaves lifecycle mutation committed; missing version500. | [Report](skills/pr-402.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#403](https://github.com/creep1ng/sre-agent/pull/403) | Blocked by #397/#387. | [Report](skills/pr-403.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#404](https://github.com/creep1ng/sre-agent/pull/404) | Changes: non-LLM Skill audit accepts provider consumption. | [Report](skills/pr-404.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#405](https://github.com/creep1ng/sre-agent/pull/405) | Changes: audit/correlation, response schema and401 challenge. | [Report](skills/pr-405.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#406](https://github.com/creep1ng/sre-agent/pull/406) | Changes: repeated costly credential authentication per dependency. | [Report](skills/pr-406.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#407](https://github.com/creep1ng/sre-agent/pull/407) | Blocked by prior Skill-stack findings. | [Report](skills/pr-407.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#409](https://github.com/creep1ng/sre-agent/pull/409) | Blocked: inherited defects and no-read evidence limitation. | [Report](skills/pr-409.md) · [Docker reproduction](skills/REPRODUCE.md) |
| [#410](https://github.com/creep1ng/sre-agent/pull/410) | Changes: isolated provisioning test fails. | [Report](runtime/pr-410.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#411](https://github.com/creep1ng/sre-agent/pull/411) | Changes: resume cursor, JSON types, idempotency contract;509 lines without exception. | [Report](runtime/pr-411.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#412](https://github.com/creep1ng/sre-agent/pull/412) | **Merged** — [`9d7aaf17`](https://github.com/creep1ng/sre-agent/commit/9d7aaf1743e970542b79d1af82682431d557b422) | [Report](runtime/pr-412.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#413](https://github.com/creep1ng/sre-agent/pull/413) | Changes: isolated authorization test fails. | [Report](runtime/pr-413.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#414](https://github.com/creep1ng/sre-agent/pull/414) | **Merged** — [`5b7c9994`](https://github.com/creep1ng/sre-agent/commit/5b7c9994c2d8253c9fc906a791e86924d5e828ac) | [Report](runtime/pr-414.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#415](https://github.com/creep1ng/sre-agent/pull/415) | **Merged** — [`c5f6c153`](https://github.com/creep1ng/sre-agent/commit/c5f6c1532569ea8b14b27b1d50800d260833f852) | [Report](runtime/pr-415.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#416](https://github.com/creep1ng/sre-agent/pull/416) | Changes: actor contract and conflict-recovery reason loss. | [Report](runtime/pr-416.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#417](https://github.com/creep1ng/sre-agent/pull/417) | **Merged** — [`618ce227`](https://github.com/creep1ng/sre-agent/commit/618ce227d7ee2d1a274cdf0c7951ce8751d6e760) | [Report](runtime/pr-417.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#418](https://github.com/creep1ng/sre-agent/pull/418) | Changes: stale run response overwrites selected provenance. | [Report](runtime/pr-418.md) · [Docker reproduction](runtime/REPRODUCE.md) |

## How to reproduce

1. Use Git to check out the exact candidate SHA named in its report, separately from this evidence-only branch.
2. Read the relevant group’s `REPRODUCE.md` and inspect the supplied proof driver before execution. Use only a fresh, isolated non-production database/project.
3. Run the documented Docker commands. The guide identifies synthetic fixtures, explicitly injected faults, network/provider prerequisites, and known skipped checks.
4. Compare actual responses/SQL/screenshots with expected behavior. Do not infer semantic acceptance from a green check or a screenshot of source code.

The actual screenshots and sanitized logs are next to each report. Source worktrees were not corrected by this audit. No global volume teardown was used. The audit-created OTel session was shut down and the launcher reported absent; provider proof used bounded synthetic requests.

## Integration status

Seven scoped candidates merged in verified order: #396, #414, #415, #417, #412, #371, #372. Every actual merge tree and parent pair matches the independently tested sequence. #390 remains open for unsafe authored documentation. [Integration report](integration/integration-report.md) · [Verified merge commits/trees](results/merges.json) · [All 35 posted reviews](results/reviews.json) · [Docker reproduction](integration/REPRODUCE.md).

Observed final-seven proof: **1220 Python passed /1 optional provider skip; 27 focused UI browser passed; 31 full static browser passed /58 connected-only skips; all 15 Python/static/type/migration commands passed.** The optional unchanged historical contract suite was bounded after 49 passing tests; its remainder is incomplete, not PASS. Deliberately offline showcase failures reproduce on starting main; normal-network static browsers pass. Parent Ruff spot-check passed independently. Final dispositions and merge SHAs are recorded above. Separately, final-main hosted CI passed all eight jobs; its contract job completed successfully. One failure-only diagnostic step was skipped, and hosted test-level skip counts were not established. [Hosted details](results/hosted-ci.md).

Live main at initial integration: `4b0c8740a042a8654979dd43481c7ad4f9992ea1`. GitHub’s PR-reported base can lag the actual main ref; prospective-tree verification does not rely on that cached base.


## Integration record and proof limits

Final main: `5b6109bd2c8100455136cf12ce91c52830833c7f`; source tree `5ee5fd41bfa4c8fb588b147641a04f72d03f9df1`. All seven merges used exact expected heads and ordinary GitHub paths. No branch rules, required checks, exception labels, source branches or source fixes were changed by the reviewer. PR #372 is the bottom of a native stack; the synchronous endpoint refused without mutation, so only that verified bottom PR was submitted through the documented [asynchronous merge API](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request-asynchronously), with `merge_action=default` and confirmed `bypass_rules=false`. Upstack PRs were not selected for merge.

The five PR descriptions that used an Actions URL instead of an image now link actual captures; the UI descriptions link Docker browser reproduction. #417's CA1 wording was corrected: a labeled fixture does not demonstrate durable generation/versioning. These are reviewer-supplied evidence/scope metadata corrections, not application source changes. No human-review checkbox was checked and no independent human review is claimed. Earlier evidence-only review objections on #371/#372 were reassessed against the newly captured behavior before approval.

Merged slices do **not** close #189, #25, #330, #40, #41 or #43. Their outstanding producers, HTTP/authorization, durable artifacts and end-to-end criteria remain visible in the per-PR reports. No blocked child was approved by association with a merged parent.


## Publication verification

[Independent readback](results/final-audit.md) verified all 35 exact review IDs and 203 evidence links, with all 28 pending heads unchanged and no newly ready PR outside the original scope. Review states: 7 approvals, 15 change requests, 13 comments (including self-authored PRs that cannot receive a change-request review from the same account). [Outcome comments](results/outcome-comments.json) record actual merges and updated blocked-child dependencies. [Issue readback](results/issues-open.json) confirms all six partially delivered issues remain open.


## Suggested repair order

1. Fix deterministic integrity defects first: duplicate declaration in #389 and non-atomic mutation/audit in #402. Their failing HTTP/SQL probes are published.
2. Resolve #373/#378/#387 integration conflicts, preserving the reviewed behaviors, then retest every affected stack at its new exact heads. Do not inherit approval from a green child or a newly merged parent.
3. Address remaining validation/contracts, UI races, test isolation and safe demonstration documentation using each PR's expected/actual cases. #370's Grafana cause remains unattributed; do not call it an established PR regression.
4. Request review of the corrected candidates with new Docker evidence. Do not close partially delivered issues based only on these seven merges.

Audit-owned containers and temporary OTel cloud resources were cleaned up. Existing user files and shared resources were preserved. The six drafts were not reviewed. The reports preserve all failed/skipped/partial evidence alongside successful runs.
