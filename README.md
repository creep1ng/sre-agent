# Pull-request acceptance audit — 2026-09-29 UTC

Initial scope: **35 open, non-draft PRs** in `creep1ng/sre-agent`. Six drafts were excluded: #365, #366, #367, #368, #382, #420. The inventory was captured before any audit merge.

This branch contains **evidence only**, not application changes. Reports separate actual source/SQL/HTTP/browser observations, controlled faults, mocked browser transport, real provider calls, hosted CI, and unperformed checks. Automated review is not represented as independent human assessment. Integration, where later recorded, follows the maintainer’s explicit conditional instruction for this audit.

## Results by PR

| PR | Audit disposition | Full report and evidence |
| --- | --- | --- |
| [#370](https://github.com/creep1ng/sre-agent/pull/370) | Pending: Grafana browser CA5 not demonstrated; cause unattributed. | [Report](runtime/pr-370.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#371](https://github.com/creep1ng/sre-agent/pull/371) | Source checks pass; final integration pending. | [Report](triage/pr-371.md) · [Docker reproduction](triage/REPRODUCE.md) |
| [#372](https://github.com/creep1ng/sre-agent/pull/372) | Source checks pass; final integration pending. | [Report](triage/pr-372.md) · [Docker reproduction](triage/REPRODUCE.md) |
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
| [#396](https://github.com/creep1ng/sre-agent/pull/396) | Atomic runtime/SQL proof passes; final integration pending. | [Report](runtime/pr-396.md) · [Docker reproduction](runtime/REPRODUCE.md) |
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
| [#412](https://github.com/creep1ng/sre-agent/pull/412) | Command translation/SQL proof passes; final integration pending. | [Report](runtime/pr-412.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#413](https://github.com/creep1ng/sre-agent/pull/413) | Changes: isolated authorization test fails. | [Report](runtime/pr-413.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#414](https://github.com/creep1ng/sre-agent/pull/414) | Scoped UI checks pass; final integration pending. | [Report](runtime/pr-414.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#415](https://github.com/creep1ng/sre-agent/pull/415) | Scoped read-only UI checks pass; final integration pending. | [Report](runtime/pr-415.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#416](https://github.com/creep1ng/sre-agent/pull/416) | Changes: actor contract and conflict-recovery reason loss. | [Report](runtime/pr-416.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#417](https://github.com/creep1ng/sre-agent/pull/417) | Fixture-only presentation checks pass; durable generation remains out of scope. | [Report](runtime/pr-417.md) · [Docker reproduction](runtime/REPRODUCE.md) |
| [#418](https://github.com/creep1ng/sre-agent/pull/418) | Changes: stale run response overwrites selected provenance. | [Report](runtime/pr-418.md) · [Docker reproduction](runtime/REPRODUCE.md) |

## How to reproduce

1. Use Git to check out the exact candidate SHA named in its report, separately from this evidence-only branch.
2. Read the relevant group’s `REPRODUCE.md` and inspect the supplied proof driver before execution. Use only a fresh, isolated non-production database/project.
3. Run the documented Docker commands. The guide identifies synthetic fixtures, explicitly injected faults, network/provider prerequisites, and known skipped checks.
4. Compare actual responses/SQL/screenshots with expected behavior. Do not infer semantic acceptance from a green check or a screenshot of source code.

The actual screenshots and sanitized logs are next to each report. Source worktrees were not corrected by this audit. No global volume teardown was used. The audit-created OTel session was shut down and the launcher reported absent; provider proof used bounded synthetic requests.

## Integration status

Seven scoped candidates passed final actual-main sequential integration verification: #396, #414, #415, #417, #412, #371, #372. #390 is excluded for unsafe authored documentation. No merge is claimed at this publication stage. [Integration report](integration/integration-report.md) · [Exact source trees and checks](integration/integration-summary.json) · [Docker reproduction](integration/REPRODUCE.md).

Observed final-seven proof: **1220 Python passed /1 optional provider skip; 27 focused UI browser passed; 31 full static browser passed /58 connected-only skips; all 15 Python/static/type/migration commands passed.** The optional unchanged historical contract suite was bounded after 49 passing tests; its remainder is incomplete, not PASS. Deliberately offline showcase failures reproduce on starting main; normal-network static browsers pass. Parent Ruff spot-check passed independently. The final disposition and actual merge SHAs will be recorded here and in the PR conversations.

Live main at initial integration: `4b0c8740a042a8654979dd43481c7ad4f9992ea1`. GitHub’s PR-reported base can lag the actual main ref; prospective-tree verification does not rely on that cached base.
