# Issue #454 — Bounded feature-branch delivery

## Objective and authority

Split the accumulated #569 producer stack into cohesive reviewable PRs on a
feature branch. The maintainer rejected an aggregate size exception and requested
this split on 2026-10-13. Route: direct; no SDD or new behavior.

- Repository and authorized credential: creep1ng/sre-agent, current gh session.
- Feature baseline: `ef6b328fe75494a9b77d9ddd9a330cbaa22ac1b6` (fetched main).
- Preserve source: `e0c7fe313ac07812273437b30c189d3f46859a5f`, the actual
  `codex/issue-454-design` branch; PR API metadata still reports its old head.
- Live GitHub Projects consulted: midnight.agent / #454 Todo.
- Initial draft scope excluded main integration; superseded by explicit approval below.
- No issue closure, paid provider calls, new credentials,
  unrelated remote access, automatic size labels, or inherited size exceptions.
- Keep all files, preauthored tests, provenance, immutable historical releases,
  and current main behavior. No minification or arbitrary artifact truncation.
- Count additions plus deletions against each PR's actual declared base.
- A feature branch does not exempt its eventual main integration from size policy.
- On 2026-10-13 the maintainer authorized `size:exception-update-contract`
  exclusively for the new contract PR. Every other PR remains at most 400 lines.

## Tasks and acceptance checks

- [x] **F454-1 — Inventory the actual accumulated candidate.**
  Compare live Git refs and Projects, enumerate complete changes and conflicts.
- [x] **F454-2 — Establish the feature and bounded design delivery.**
  Start feature at current main; preserve the accumulated source. Make #569's
  role explicit without overwriting or hiding source intended for later PRs.
- [x] **F454-3 — Partition complete cohesive units.**
  Separate contract, capture, selection, read projection, provider/E2E scenarios,
  evidence, and historical tracking. No blanket size exception. Apply the
  indivisible generated-contract exception only to its explicitly authorized PR.
- [x] **F454-4 — Reconcile main and verify the complete candidate.**
  Preserve consumption-policy provenance AND atomic attribution capture; retain
  both alert_triage and request_attributions in existing isolated DB resets.
  Run existing real HTTP/PostgreSQL E2E checks and relevant contract checks;
  retain exact command/environment/SHA/output. Do not claim old CI is current.
- [x] **F454-5 — Publish drafts and independently read back the split.**
  Attach every new PR. Record base, head, size, dependencies, actual checks,
  pending integration and human review. Initial drafts did not authorize main; superseded by the later explicit decision.

## Verification boundaries

Original #454 scenarios were authored before production code. This operation
preserves them, resolves integration conflicts, and restructures delivery; it
does not author post-code unit tests or claim a new RED cycle from syntax errors.
Existing controlled providers remain controlled, never live-provider evidence.

## Progress and next step

Observed accumulated delta: 317 files, 13,753 additions + 124 deletions.
Conflicts: gateway/responses.py and two incident DB fixture resets. The main-only
investigation/external-effects fixture also needs the new attribution-table reset.
The generated contract includes a 2,508-line schema and a 1,015-line fixture;
arbitrary line fragments are not cohesive accepted delivery. The maintainer
authorized the exact contract-only label above, not an aggregate exception.
Feature codex/feature-454 is published at the verified main baseline. Draft #596
contains the design and initial plan (318 lines); #569 remains a draft/provenance
reference. All original source and remote PRs remain preserved.

Memory mirror: PENDING. No authoritative registered runtime session identity;
agent-attributed Engram writes are forbidden. Observation 9911 is an older
producer plan, not current scope or verification authority.

Next: submit the assembled feature to main and wait for current hosted CI and
governance before merging. App attachments are confirmed; persistent memory mirroring remains unavailable.

Partition verified: 13 cohesive cuts; only contract is above 400 lines. Every
original runtime/test/schema/script file is accounted for and matches source
0bfadf958f941ec61889daef4e207c2284801aa4. Current 82 E2E checks, repeated13 attribution
checks, real HTTP/SQL and contract222-artifact validation pass. Initial demo401
after unrelated fixtures is recorded; correct-fixture repeat passes. Full Python
suite passes1847/1opt-in paid skip; Alembic passes. Hosted CI and human acceptance remain pending.

All 14 drafts were created; exact GitHub head/base/size/label readback PASS.
Initial App attachment calls did not return. Later retries confirmed all fourteen
slice attachments and final main PR #616 on 2026-10-13.
Current review index: docs/evidence/issue-454-feature-split/README.md; only #601
has the explicitly authorized size:exception-update-contract label.

## Approved integration — 2026-10-13

The maintainer accepted all evidence and slices, requested their merge, then
explicitly authorized the aggregate size exception and final main integration.
This supersedes the initial no-main scope, not the no-paid-call/no-issue-closure
boundaries. The contract retains its specifically requested exception label.

- [x] **F454-6 — Integrate all fourteen approved slices into the feature.**
  All PRs #596 and #601–#613 report merged. Assembled feature499ef81 has exactly
  the reviewed final75dfec6 tree. GitHub required asynchronous merges without
  rules bypass, and updated stack SHAs automatically; candidate trees were
  checked against original cuts. #613 first merged into #612; its later769-line
  aggregate contains both previously reviewed cuts, under the explicit aggregate
  exception. #611 needed an ancestry-only base update; its actual cut remained229.
  Every slice passed current governance before integration. Intermediate CI
  failures were dependency-prefix tests/unused imports, not accepted main builds.
- Main advanced to2f022e6 with unrelated MCP changes. A clean merge preserves
  those changes; source and tests for #454 are unchanged. The final main PR
  requires new hosted CI at its actual assembled candidate, not old-prefix CI.
- Independent human acceptance and size exception are the explicit decisions
  in this chat; no automatic approval/exception labels were added.
- Persistent memory writes remain prohibited by absent runtime identity.

Final main PR: https://github.com/creep1ng/sre-agent/pull/616. All App attachments
are now confirmed. Hosted CI for the final actual candidate is pending; final
merge identity will be recorded in the PR after observed success.
