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
- No merge into main, issue closure, paid provider calls, new credentials,
  unrelated remote access, automatic size labels, or inherited size exceptions.
- Keep all files, preauthored tests, provenance, immutable historical releases,
  and current main behavior. No minification or arbitrary artifact truncation.
- Count additions plus deletions against each PR's actual declared base.
- A feature branch does not exempt its eventual main integration from size policy.
- A contract-only exception is a separate pending decision, not authorization.

## Tasks and acceptance checks

- [x] **F454-1 — Inventory the actual accumulated candidate.**
  Compare live Git refs and Projects, enumerate complete changes and conflicts.
- [ ] **F454-2 — Establish the feature and bounded design delivery.**
  Start feature at current main; preserve the accumulated source. Make #569's
  role explicit without overwriting or hiding source intended for later PRs.
- [ ] **F454-3 — Partition complete cohesive units.**
  Separate contract, capture, selection, read projection, provider/E2E scenarios,
  evidence, and historical tracking. No blanket size exception. Resolve the
  indivisible generated-contract policy choice before publishing that cut.
- [ ] **F454-4 — Reconcile main and verify the complete candidate.**
  Preserve consumption-policy provenance AND atomic attribution capture; retain
  both alert_triage and request_attributions in existing isolated DB resets.
  Run existing real HTTP/PostgreSQL E2E checks and relevant contract checks;
  retain exact command/environment/SHA/output. Do not claim old CI is current.
- [ ] **F454-5 — Publish drafts and independently read back the split.**
  Attach every new PR. Record base, head, size, dependencies, actual checks,
  pending integration and human review. No final main merge authorization.

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
arbitrary line fragments are not cohesive accepted delivery. Contract-only
exception decision pending. All source and remote PRs remain preserved.
Local feature and planning branches start at the verified main baseline.

Memory mirror: PENDING. No authoritative registered runtime session identity;
agent-attributed Engram writes are forbidden. Observation 9911 is an older
producer plan, not current scope or verification authority.

Next: publish the baseline feature and planning draft, then finish the cohesive
split when the contract decision is resolved. The eventual main integration
requires its own accepted, size-compliant route; no aggregate exception exists.
