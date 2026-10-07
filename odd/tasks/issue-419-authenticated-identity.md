# Issue 419 — authenticated identity

> **Current local reconciliation status (2026-10-07):** The record below was created for the superseded combined #488 candidate and is retained as historical provenance, not as evidence for the current split candidates. #458 is now merged normally; current main is `a3541a96d83364a126ceff418ed3cbf7dbdc2d82`, whose tree includes tested source `fe8608ce302672852362ef42ede364e5fb5bed96` unchanged. The #488 backend implementation commit is `a1b61838cee7624c1ef05abb406fc80069bc9cbe`, based directly on that main; a later docs-only commit records this reconciliation. The existing #488 frontend files and their behavior tests were moved to the local #416 candidate `161258165a0cd29e2243efae85cf8fb1fe71363c`; #489's Refresh lock is not included in either candidate. The historical replay and screenshot below are **not proof** for either current candidate or the final #419 criteria. The issue's combined acceptance remains pending until parent-owned PR updates/reviews and #489 integration produce a final main-bound candidate.

Current reconciliation checks: #416 UI RED was 5 failed / 7 passed, then its targeted Playwright suite passed 12 and its Python UI guard passed 4; the pre-existing 409/Refresh reason recovery was retained. The #488 endpoint RED was 9 failed / 19 deselected; the focused backend suite passed 92, and the full checks service passed 1,574 with 1 skipped. Exact commands, isolation settings, and limits are recorded in `odd/tasks/issue-419-chain-integration.md`. No refreshed packaged UI replay or screenshot has been produced for the current split candidates.

## Objective / problem / why
Expose safe current-principal lookup and make review commands satisfy run-command:1.0.0 without trusting client identity. The original base lacked command/UI dependencies; local dependency-first completion was explicitly selected.

## Scope / authorization / constraints
Local dependency integration and #419 implementation authorized; current gh session now authorized to publish #419, request/wait for Codex review and merge #419 subject to repository gates. No permission inferred to merge dependency PRs or waive size/evidence/human-review gates. Live Project #8 midnight.agent: #419/#330 Todo on 2026-10-06.
Route: delegated direct. Keep the required actor_reference contract; the #330 handler checks authenticated identity and server-resolved authority. Whoami returns principal_id only, with no admin.read, arbitrary lookup or identity cache. Imported dependency commits remain separate; the own delivery unit is under 400 additions+deletions. English artifacts and real sanitized evidence only; no new post-code unit tests.
TDD: ON, global gentle-ai state strict_tdd=true; exact runners: isolated PostgreSQL/cached checks image pytest, then original Compose python-checks recipe and containerized Playwright. RED before own source, GREEN/refactor observed. RDD: disabled/unmanaged (global).

## Acceptance / observed outcomes
Existing bearer lifecycle rejects missing/malformed/unknown/revoked/expired/inactive with generic 401. Original packaged application exposes typed, documented GET /v1/whoami with principal_id only and no-store. Browser resolves its own principal afresh for each command and invalidates outstanding UI work after credential clear/change. Real commands satisfy the published schema; mismatched principal is denied before any decision.

## Tasks
- [x] ID419-1: Import exact PR #458/#416 and provisioning #410/#413 locally; reconcile duplicate provisioned grants in existing fixtures and verify isolated dependency integration.
- [x] ID419-2: Test-first whoami acceptance for two principals/lifecycle/no leakage; implement shared-auth minimal endpoint and documented response; verify actual packaged mounting.
- [x] ID419-3: Test-first browser identity/command alignment; verify schema-valid command, mismatch rejection, credential change/clear, real sanitized receipt and applicable checks.

## Verification / checkpoints
- Original base: fe6fca024fec4f89f7538dc5dc03159a99f12a2a. Prepared dependency base: 683d1acc97adb3392e7b26e39b99c9c558a5c0bf. PR458 source5339f976; PR416 source7894a68c/738c86dd; PR410 source254f4254/30dc2b7a; PR413 sourced9c65537. PR410 test patch reconciled by three-way apply preserving existing cleanup.
- Baseline before grants: Python57/browser9 pass. New provisioning exposed duplicate manual run.command/run.approve and run.start fixture grants; removed only redundant fixture inserts. Obsolete static JS principal_id ban removed while keeping no editable identity in HTML.
- Genuine RED: endpoint9 failed/19 existing passed, browser4 failed/7 passed. Initial invalid expiry fixture was corrected and not counted as feature RED. Writer relevant GREEN78; independent browser GREEN11.
- Real original-Dockerfile API/web replay: whoami200, approve202/current_state verifying, mismatched claim403. SQL: accepted incident one decision; mismatch remained mitigating/zero decisions. PNG inspected and responses retained at docs/evidence/issue-419; packaged source hashes match current behavior source.
- First full suite1562pass/1skip/2fail/11errors: stale fixture/UI assumptions plus migration DROP ROLE blocked by demo DB on same cluster. PostgreSQL roles are cluster-global: preserved replay, removed only own resources and recreated checks-only cluster; no migrations/runtime changes to mask it.
- Final independent full suite:1575 passed,1 skipped in283.00s; skip is opt-in live OpenRouter smoke. Exact Compose reproduction:96 passed. Repository-wide Ruff lint/format, offline uv lock, run API validator, five import contracts, mypy13 source files, database isolation guard, shellcheck and Alembic check all passed. git diff --check passed.
- First API networkless build lacked uv download; normal locked-dependency build passed. First live replay raced Uvicorn startup (502); ready replay passed. No unresolved local failure. Hosted CI, live OpenRouter, human acceptance and remote integration not performed.

## Publication progress / next step
- [ ] ID419-4: Publish bounded dependent draft PR, attach real evidence, request Codex review and wait for its candidate-bound result.
- [ ] ID419-5: Integrate to main only after dependency PR integration, refreshed candidate/base/evidence, passing checks and human acceptance.
2026-10-06: user authorized publication/Codex review/merge of #419. Main remains fe6fca0; dependencies #458/#416/#410/#413 remain open (#416 CHANGES_REQUESTED). Entire chain to main is1468 lines; own candidate320. Publish supporting codex/issue-419-dependencies base (683d1ac) and own head as dependent draft, not an acceptance of imported dependencies. Do not merge into that supporting branch as a substitute for main integration. Existing local verification resources already cleaned.

- [x] ID419-6: Correct existing browser concurrency test synchronization exposed by hosted CI, then repeat browser checks. CI observed disabled submit before whoami completed; the test asserted the command array before the request arrived. Keep production behavior and test intent unchanged.
Published draft PR #488 (322 lines); Codex acknowledged review with eyes. Hosted static-web failed the existing in-flight test (0 requests at premature assertion); governance reports Policy incomplete. Other jobs pending.

- [ ] ID419-7: Reproduce Codex P2 action-switch race during pending whoami with browser test first; fix bounded submission state, verify RED/GREEN and request review on refreshed candidate. Review https://github.com/creep1ng/sre-agent/pull/488#discussion_r4201800448 bound to2e5284c.

ID419-7 implementation verified: genuine browser RED (two commands; enabled action during pending identity), GREEN12 passed; parent independently56 passed/59 skipped across offline static journeys, explicitly excluding two showcase cases requiring public assets. Submission action/comment/key now remain stable; review.js SHA2564ed113aceceafe65897b860007c6b790e1de065da3159556a2be1de9117cde01. Candidate re-review pending; original packaged PNG is historical, not refreshed web proof.
