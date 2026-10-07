# Issue 23 triage stack review

## Objective, problem and why
Review PRs #373 → #374 → #380 → #389 → #391 → #392 → #460 → #463 → #464 → #466 → #485, correct verified P0/P1 defects, and prove the complete current issue #23 with repeatable evidence. Green hosted checks and historical screenshots do not establish acceptance.

## Authorized scope and route
Delegated direct: one read-only exploration; one bounded writer per correction. Local P0/P1 corrections and evidence are authorized. Current gh session is authorized for scoped repository/Project reads and reference fetch only. No push, publication, merge or issue closure. Preserve unrelated work and containers. English artifacts; Spanish chat.

## Current authoritative evidence
- Live issue #23 OPEN, Project #8 midnight.agent Todo, Estimate 5 (2026-10-06 America/Bogota).
- Exact linear stack starts at `63ebc6198a0ca5ce257f1826060bb6345d96b095` and ends at PR #485 `df17a07edb8259671763f1ba9e8cfa4e763365bf`; all eleven PRs OPEN with successful current hosted checks.
- Original clean worktree HEAD `fe6fca024fec4f89f7538dc5dc03159a99f12a2a`; candidate is divergent, do not silently rebase onto main.
- Read-only metadata captured in `/tmp/triage23-review`; fetched refs `refs/remotes/triage-review/pr*`.

## Constraints and testing
- Strict TDD ON, source: local Gentle AI state `strict_tdd=true`. Observed RED before implementation, GREEN then refactor. Do not add unit tests after implementation. Prefer real E2E; isolated behavior testing must define failure cases first.
- Existing Python runner: `docker compose --profile checks run --build --rm python-checks pytest ...`; browser runner: Playwright 1.63.0 with `playwright.production.config.js`. All demonstration package tools run inside Docker.
- RDD OFF (global), disabled/unmanaged. Ordinary checks remain; no native review ceremony.
- Use synthetic data and isolated disposable database/network; no ambient credentials, no shared database resets, no global teardown. Sanitize screenshots, output and commands.
- Approximately 400 authored lines/task is advisory; PR acceptance limit remains 400 additions plus deletions unless explicitly approved. No publication requested.

## Acceptance criteria and checklist
- [x] **T23-1** Reproduce/fix P1 link-versus-close eligibility race. Real PostgreSQL RED2failed/3passed; target-row lock fix GREEN5passed, independent final complete triage checks50passed14.04s; Ruff and diff checks pass. Evidence below.
- [x] **T23-2** Reproduce/fix P1 stale-version recovery: authoritative GET refresh after 409, preserving operator context; no false success and repeat safely with fresh version. Browser behavior proof.
- [ ] **T23-3** Assess missing eligible-target listing (CA2); resolve scope/contract and correct if within authorized P1 scope. Reject closed destinations both UI and API.
- [ ] **T23-4** Resolve authoritative impact and external-decision origin requirements for CA3/CA6; never invent a rubric/evaluator or automatic decisions. Product decisions remain user-owned.
- [ ] **T23-5** Execute candidate-bound CA1–CA6 evidence matrix with durable dismiss/reload, eligible link, declare ID/severity/impact/event, idempotency/concurrency, stale recovery, 403/policy/evaluation failures and manual/automatic distinction. Produce real sanitized screenshot and repeatable commands without missing `/tmp` seeds.
- [ ] **T23-6** Complete full-stack review report and final requirement-by-requirement audit; separate local evidence from hosted checks and human acceptance. Report every failed/skipped/pending check.
- [ ] **T23-7** Correct verified P1 terminal decision rewrite: declare→dismiss→declare currently creates two incidents for one alert. Preserve authoritative terminal identity and idempotent replay; prove rejection/rollback for terminal mutations with real API/SQL.
- [ ] **T23-8** Complete inbox→triage handoff and domain-provided allowed actions. Existing inbox only emits an unconsumed event; direct-URL journeys do not prove the requested inbox paths. Define any missing read contract explicitly, not another browser state machine.

## Progress, verification and next step
Read-only exploration complete. Potential P1: link eligibility SELECT does not lock target incident; test before claiming defect. Confirmed gaps: no eligible-incidents handler/list UI, no GET refresh on 409, impact unresolved/null by contract, no origin distinction. Current production browser config omits new real persistence/recovery/403/session suites; PR #485 reproduction references missing `/tmp/seed-c3e.py`.

Local branch `codex/triage-23-stack-review` now uses fetched #485 as correction base; original HEAD is preserved. Own isolated Docker stack is healthy (API28423/web28424 loopback, internal network, disposable tmpfs database); separate checks database avoids resets of browser evidence.

Fresh baseline on df17a07: Python45passed18.32s; browser30passed51.8s (17real integration,13route-mocked; no skips). SQL readback confirms13durable triage rows,5declared incidents with severity but impactJSONnull and5initial runtime events. Logs/screenshots are under `/tmp/triage23-review`; interim repository report `docs/evidence/issue-23-stack-review.md` records identity, exact evidence scope and pending criteria. These temporary setup seeds are not final repeatable evidence. Initial ad-hoc SQL mistakes were corrected and are recorded separately from product defects.

T23-1 completed: plain MVCC eligibility SELECT allowed a close to commit before link persistence. Minimal `FOR UPDATE` serializes both orders. Failure cases were written first, RED observed on exact df17a07 service, then GREEN and cleanup/format refactor. Parent independently repeated RED with final tests (2failed/3passed9.61s) and current full triage suite (50passed14.04s). Final service SHA256 `e8931db283e8fd93ddce119f93c72375f4a9dbbda67b58055105cdd75c80bab5`, test SHA256 `a30050285d1f7816ea9bd644e69ec33c41a6d05000f9823b1c3110632e39e49d`; logs `/tmp/triage23-review/t23-1-parent-final-{red,green}.log`. Test harness early hangs were diagnosed and bounded cleanup corrected before final proof. Worker-owned resources removed; parent demonstration stack remains isolated and live.

Next: T23-7 terminal identity guard; T23-3 contracted eligible listing; T23-4 still needs authoritative product decisions. Keep cohesive local correction candidates within 400 lines for future PRs; no publication. No full issue criterion accepted yet. Engram mirror topic: `odd/triage-23-stack-review/tasks`.

Additional independent full-issue audit found no inbox handoff or domain action projection. Parent realHTTP reproduction `/tmp/triage23-review/terminal-probe.log`: same synthetic alert declare201v1→dismiss200v2/nullincident→declare201v3/differentincident. This confirms a P1, not a hypothetical edge case. T23-7 is within authorized P0/P1 corrections; T23-8 captures explicit unmet integration requirements. Impact assignment and external automatic decision origin remain real product/contract decisions; do not equate alert source or actor kind with decision origin without authority.

T23-2 completed: authorized GET after stale_version preserves command draft and never automatically retries; failed read clears unverified facts. CONNECT resets the new generation gate while old finally stays guarded. Worker observed RED before both fixes; final GREEN23passed. Parent independently ran all six browser suites:34passed56.4s (21real,13mocked, no skips); node syntax and diff checks passed. Verified UI SHA25675307d81f364cef6d4423d3a4f7e4e479111d9cc5921cbfd996c10c4ec5e78e1 and spec SHA25660083ba8b7d85933c9dfcbd4d89ac6c7b46d5be4d8acfb21c15f9a85cfb30267. Actual sanitized screenshot docs/evidence/issue-23-conflict-recovery.png; parent log /tmp/triage23-review/t23-2-parent-all-browser.log. Packaged seed/config and final full-criterion proof remain T23-5 pending.
