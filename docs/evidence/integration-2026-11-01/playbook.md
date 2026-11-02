# Merge playbook: the M1 demo stacks (2026-11-01)

Rehearsed on `t3/integration-2026-11-01` (draft PR #924, **do not merge**), built from `main`
`41d9ca9d` (#891/#892 already merged). Every stack head below was merged with
`git merge --no-ff` in this order; the extra commits are on that branch, so each one can be
cherry-picked or replayed with `git show <sha>`.

| Step | Stack (head merged) | Merge commit |
| --- | --- | --- |
| 1 | #858 → #868, which carries all of #765 (#816–#820) since GitHub merged that stack into `t3/704-dispatch-recovery` (`1926483f`) | `864fb11d` |
| 2 | #771: #904 → #905 → #906 → #907 (`t3/771-4-evidence`, `6d89f4d7`) | `30c3336c` |
| 3 | #767: #894 → #884 → #885 (`t3/767-decide-from-telegram`, `5edc5999`) | `35c54d5e`, then `ae3e0bac` |
| 4 | #895 → #896 (`t3/870-incident-list`, `e314105d`) | `474c75fa` |
| 5 | RC-2 foundation #887 → #888 → #889 (`3173eb61`) | `c8220d3c` |
| 6 | Navigation #915 → #916 → #917 (`2e43f990`) | `b259564b` |
| 7 | Inbox #899 → #900 → #901 → #902 (`8e5f1755`) | `d37f4135` |
| 8 | Incident page #908 → … → #914 (`dfb18563`) | `b5a8d19a` |
| 9 | Landing #876 → #877 → #878 (`68d5c5a1`) | `d09292a1` |
| 10 | Integration commits (see [Fixes found by the checks](#fixes-found-by-the-checks) and [New PRs](#new-prs-to-open)) | `937a991d`, `e5a33ac8`, `14f2898e`, `31702ca8`, `f24283bb`, `ffcc0d11`, `7392d349`, `4e66f9ea` |

Excluded: the RC-1 UI PRs (#852, #853–#856, #859–#861) and #841.

## Merge order for `main`

The repository merges with merge commits only, and a stack lands with
`gh stack merge <top> --merge --yes`. Before each step, update the bottom PR branch so `main`
never holds a broken state: `git merge origin/main` into it, resolve as listed, add the listed
commits, push (each upper layer then merges its lower one, bottom-up), wait for CI, then merge.
Two revisions that share a `down_revision` give Alembic two heads, and `/health/ready` answers
`503`, so every rename travels with its PR.

The chain for `main` is `_04` → `_05` (#765) → `_06` (#767) → `_07` (#767) → `_08` (#771), so
**#767 merges before #771**, even though the integration branch merged them the other way
round (the textual result is the same).

| # | Merge | Before merging | Re-run |
| --- | --- | --- | --- |
| 1 | #858 → #868 (with #765) | #858 merges cleanly. **#868 conflicts with `main`** since #891: in `t3/704-dispatch-recovery`, merge `origin/main` and resolve [R1](#r1-srcsre_agentgatewayinvestigationpy-868-against-891). Its migration `20261030_05` already chains on `_04`. | unit; `run_real_journeys.sh incidents` (intake journey) |
| 2 | #894 → #884 → #885 (#767) | In `t3/767-chat-principal` (#894): merge `origin/main`. The head pins conflict; keep any side, then apply [M1](#m1-rename-767). In `t3/767-decision-message` (#884): apply [M2](#m2-rename-767b). Add [J1](#j1-link---principal-in-the-intake-journey) to #894 (needs #765 on `main`). #885's E2E needs [J3](#j3-the-telegram-e2e-after-771) once #771 is on `main`; carry it with step 3. | unit; `run_telegram_e2e.sh`; `run_real_journeys.sh incidents` |
| 3 | #904 → #905 → #906 → #907 (#771) | After step 1, GitHub retargets #904 to `main`. In `t3/771-1-policy`: merge `origin/main`, resolve [R2](#r2-srcsre_agentchatoutboxpy-771-against-767) and [R3](#r3-srcsre_agentchattelegrampy-771-against-767), keep `main`'s head pins, apply [M3](#m3-rename-771-and-the-gate) and [J3](#j3-the-telegram-e2e-after-771) (the gate breaks #767's E2E without it). In #906: [J2](#j2-the-interrupt-policy-e2e-after-767). | unit; `run_interrupt_policy_e2e.sh`; `run_telegram_e2e.sh` |
| 4 | #895 → #896 | In `t3/870-incident-list-contract`: merge `origin/main`; in #896, resolve [R4](#r4-scriptsrun_real_journeyssh-896-against-765). Then open [P2](#new-prs-to-open) right after: the inbox depends on it. | unit; `run_real_journeys.sh incidents` (incident-list-real) |
| 5 | #887 → #888 → #889 | Nothing. | console Playwright (shell) |
| 6 | #915 → #916 → #917 | Nothing. | console Playwright (shell, account) |
| 7 | #899 → #902 | #901 deletes the RC-1 `web/incident-console/e2e/live-real.spec.ts`, which #765 (`main`) edited: resolve [R5](#r5-the-rc-1-live-inbox-spec-901-against-765) by deleting it. Add [J4](#j4-governancespects-after-900) to #900. | `web/incident-console/e2e/run-inbox-real.sh` |
| 8 | #908 → #914 | `web/incident-console/README.md`: resolve [R6](#r6-web-incident-consolereadmemd-914-against-917). Add [J5](#j5-the-rc-2-incident-journeys-after-858) to #914. | `scripts/run_incident_console_e2e.sh` |
| 9 | #876 → #878 | Nothing (it is based on `main`). | console Playwright (landing, proxy); compose-smoke |
| 10 | New PRs P1–P3 | See below. | as listed |

### Resolutions

#### R1. `src/sre_agent/gateway/investigation.py` (#868 against #891)

#891 imports `select` and `authorize_governed_access_for_context`; #868 imports `text` for
`_INTERRUPTED_RUNS`. Keep both: `from sqlalchemy import select, text` and the authentication
import (commit `864fb11d`).

#### M1. Rename #767

`migrations/versions/20261030_767_bind_chats_to_principals.py` →
`20261030_06_bind_chats_to_principals.py`, `revision = "20261030_06"`,
`down_revision = "20261030_05"`. Every head pin (`git grep -n 20261030_0 -- ':!docs'`) becomes
`20261030_06` in #894 and `20261030_07` in #884:
`src/sre_agent/gateway/health.py` (`REQUIRED_SCHEMA_VERSION`), `scripts/grant_regrant_e2e.py`,
`tests/test_health.py`, `tests/test_migrations.py`, `tests/test_skill_migration_compatibility.py`,
`tests/test_bok_http.py`, `tests/test_consumption_reservation_persistence.py`,
`tests/test_demo_seeds.py` and `tests/test_incident_persistence.py`.

#### M2. Rename #767b

The brief named one #767 migration, but #884 adds a second one, `20261030_767b`.
`migrations/versions/20261030_767b_queue_chat_decisions.py` →
`20261030_07_queue_chat_decisions.py`, `revision = "20261030_07"`,
`down_revision = "20261030_06"`. Head pins move to `20261030_07`.

#### M3. Rename #771 and the gate

`migrations/versions/20261030_771_add_event_decisions.py` → `20261030_08_add_event_decisions.py`,
`revision = "20261030_08"`, `down_revision = "20261030_07"`; head pins move to `20261030_08`
(also the docstring of `src/sre_agent/gateway/event_decisions.py` and
`docs/interrupt-policy.md`). The same migration adds the condition #771's PR bodies spell out:
`CREATE OR REPLACE FUNCTION incident.enqueue_mitigation_decision()` with
`IF NOT EXISTS (SELECT 1 FROM incident.event_decisions WHERE event_kind = 'investigation' AND
event_id = NEW.run_id AND decision = 'interrupt') THEN RETURN NULL; END IF;`. Its downgrade
restores #767's body. Commit `ae3e0bac` holds M1, M2 and M3 at once.

Why the gate holds: the agent's `propose_mitigation` transition and the run's `outcome`
dispatch receipt are written by one runtime command
(`src/sre_agent/gateway/investigation.py`, `_runtime_command` with the outcome and receipt as
`extra_events`), and #767's trigger is deferred to the commit. When it runs, #771's
`investigation` decision already exists. A run a person started is recorded as
`interrupt`/`requested`, so it still gets its decision message.

#### R2. `src/sre_agent/chat/outbox.py` (#771 against #767)

`RENDERERS` keeps #767's `Rendered` return type and `mitigation_decision`, plus #771's
`daily_digest` and its link-confirmation text «Chat vinculado. Te escribo aquí cuando haga
falta tu decisión y te mando un resumen diario de lo demás.» (the policy's promise). #767's
`link_private_only` stays.

#### R3. `src/sre_agent/chat/telegram.py` (#771 against #767)

Imports: `UTC, datetime, timedelta` (#771) and `Path` (#767); `queue_digest` (#771) and
`ChatDecisions`, `Keyboard`, `RunCommandService`, `IncidentRuntime`, `load_incident_workflow`
(#767). In `gateway()`: `tasks = [asyncio.create_task(_poll(bot, store, decisions,
poll_seconds))]`, then #771's daily-digest task. Both CLI changes stay (`link --principal`,
`digest --until`).

#### J1. `link --principal` in the intake journey

#767 makes `python -m sre_agent.chat.telegram link --principal ID` required. #765's
`alert_intake()` in `scripts/run_real_journeys.sh` calls `link` without it and would fail:
add `--principal demo-human` (commit `e5a33ac8`).

#### J2. The interrupt-policy E2E after #767

Same flag in `scripts/run_interrupt_policy_e2e.sh`. In `scripts/interrupt_policy_e2e.py`
(commit `e5a33ac8`), the spike is tagged `[e2e:spike] [e2e:broken]`, so it also proposes a
rollback and the gate is exercised (without the gate, a second message goes out). A new check
requires the broken deploy's single message to carry the decision buttons, so it is #767's
message, not #771's conclusion.

#### R4. `scripts/run_real_journeys.sh` (#896 against #765)

The header comment names `incident-list-real` (#896) and the Grafana alert intake journey
(#765). Both journeys stay where each PR put them (commit `474c75fa`).

#### R5. The RC-1 live inbox spec (#901 against #765)

#765 edited `web/incident-console/e2e/live-real.spec.ts` to follow an intake card; #901
retires the RC-1 live inbox specs. Delete it (`git rm`): the RC-2 inbox E2E (#902) replaces it.

#### R6. `web/incident-console/README.md` (#914 against #917)

Both PRs add a section in the same place: keep «Navigation and account menu (RC-2, #870)» and
then «Incident page (RC-2, #870)».

### Fixes found by the checks

None of these is a textual conflict. Each one is a semantic break between two stacks that only a
run of their checks shows.

#### J3. The Telegram E2E after #771

`scripts/telegram_e2e.py` (#885) builds its five proposals directly through the runtime, with
no investigation result or outcome receipt. With the gate (M3) the policy has not decided those
runs, so no decision message goes out, and the `proposals` phase timed out after 30 s. The
synthetic `propose_mitigation` now carries the `investigation_result` and `dispatch_receipt`
(`outcome`, `success`) the investigator writes in the same transaction (commit `ffcc0d11`).

#### J4. `governance.spec.ts` after #900

`web/incident-console/e2e/governance.spec.ts` (on `main`) opened `./` and expected the inbox
headline «3 cosas necesitan tu atención». RC-1's keyless live inbox showed it; the RC-2 inbox
asks for the API key. It now opens `./?mock`, as `journey.spec.ts` does (commit `7392d349`).
CI does not run the console's Playwright suite, so this never showed on #900–#902.

#### J5. The RC-2 incident journeys after #858

`web/incident-console/e2e/incident-live.spec.ts` (#914) declared an incident and expected
«sin investigar», then clicked «Investigar». Since #858 the declaration starts the
investigation on the server. The journeys now follow «Investigando…» to the proposal, and the
decided-elsewhere journey no longer starts a second run by hand (commit `4e66f9ea`).

### Shared shell files of the RC-2 stacks

#917, #902, #914 and #878 all branch from #889 (or `main`). Git merged
`src/App.tsx`, the sidebar, `src/i18n` (registered by `import.meta.glob`), `compose.yaml` and the
Playwright config without conflict, and every feature is present: navigation with fold and
account menu, the inbox, `/app/incidentes/:id` and the landing at `/`. Live mode shows
«Bandeja» only: the live «Incidentes» list stays hidden, as #917 left it.

## PR bodies to change before each merge

| PR | Change |
| --- | --- |
| #868 | Record the merge of `main` and R1. It now carries #765, whose PRs (#816–#820) are already merged into it: name them and migration `20261030_05`. |
| #894 | Migration `20261030_06` (`down_revision` `20261030_05`), head pins `20261030_06`; J1. |
| #884 | Migration `20261030_07` (`down_revision` `20261030_06`), head pins `20261030_07`. |
| #885 | Nothing on migrations; mention that #771's gate (in `_08`) decides when its message goes out, and J3. |
| #904 | Migration `20261030_08` (`down_revision` `20261030_07`), head pins `20261030_08`, the gate is applied, and the "One gap remains at merge" paragraph becomes resolved. R2, R3. The same text in #905–#907. |
| #906 | J2: `link --principal`, the spike that proposes, the decision-buttons check (17 checks instead of 16). |
| #896 | R4; the latest-run tie and its fix (P2). |
| #900 | J4. |
| #902 | R5; `pending_decision` depends on P2 for incidents intake opens. |
| #914 | R6, J5. |

## New PRs to open

| PR | Commits | What | Base |
| --- | --- | --- | --- |
| P1 | `14f2898e` | **Maintainer decision of 2026-11-01**: an incident an alert opened is not attributed to a person. `triage_declare` accepts actor `system` (`agent/workflows/incident-response.yaml`), only with the responsible system's reference (`IncidentRuntime` precondition). Intake's declaration runs as `system`/`grafana`, and the triage decision's actor is `grafana`. `scripts/alert_intake_journey.py` checks the declaration's actor; `docs/alert-intake.md` updated. `validate_incident_contracts.py` passes unchanged (not a protected transition). | `main` after step 1 |
| P2 | `31702ca8` | **Bug found here**: an automatic declaration (#858) creates the triage run and the investigation run in one transaction with the same `created_at`, so `GET /v1/incidents` (#896, `ORDER BY created_at DESC, run_id DESC`) and the run list pick the "latest" run by its random id. About half the time the inbox shows the triage run, with no `pending_decision`, while a mitigation waits («Nada te espera.»). It happened in the second real-model run. The investigation run now starts 1 µs later. | `main` after steps 1 and 4 |
| P3 | `937a991d`, `f24283bb` and the evidence | The local full-flow stand-in (`compose.local-flow.yaml`, `scripts/local_flow_upstreams.py`) and its guide. Optional: only if the maintainer wants to keep the local rehearsal. | `main` at the end |

`e5a33ac8` (J1, J2), `ffcc0d11` (J3), `7392d349` (J4) and `4e66f9ea` (J5) belong to the
existing PRs named in the merge order, not to a new PR.

## Checks

As in #841, all in containers. Python: CI's `checks-image` command (shellcheck, ruff, ruff
format, `uv lock --check`, lint-imports, mypy, the five validators), then
`docker compose --profile checks run --build --rm python-checks`. E2E, one stack at a time:

```sh
COMPOSE_PROJECT_NAME=journeys-inc scripts/run_real_journeys.sh incidents
COMPOSE_PROJECT_NAME=telegram scripts/run_telegram_e2e.sh
scripts/run_interrupt_policy_e2e.sh            # in a worktree from scripts/bootstrap-worktree.py
docker compose up -d --build --wait web && docker compose --profile e2e run --build --rm incident-console-e2e
COMPOSE_PROJECT_NAME=inbox web/incident-console/e2e/run-inbox-real.sh
COMPOSE_PROJECT_NAME=incident scripts/run_incident_console_e2e.sh
```

## Results on the integration branch

All in containers on one 8-CPU host, on the branch tip; the first full pytest ran on the
merged tree before the integration commits, the second on the final tree.

| Check | Result |
| --- | --- |
| CI's `checks-image` command: shellcheck, ruff, ruff format, `uv lock --check`, lint-imports (6 contracts kept), mypy (11 files), the five validators | pass |
| Full pytest in `python-checks`, merged tree | `2011 passed, 1 skipped` in 7 min 44 s |
| Full pytest in `python-checks`, final tree (`4e66f9ea`) | `2011 passed, 1 skipped` in 8 min 2 s |
| Focused pytest after P1 and P2 (triage, workflow, runtime, intake, contracts) | `161 passed`, then `98 passed` |
| `run_real_journeys.sh incidents` | war-room-runs 5, war-room-reasoning 2, review-mitigation 2, incident-list 5, war-room-follow 2, postmortem 1, change-events 1 passed; consumption `22 checks, 0 failed`; provider-retry `24 checks, 0 failed`; alert-intake PASS (declaration and investigation start are `system`/`grafana`, no acknowledgment) |
| `run_telegram_e2e.sh` (#766, #767) | first run: timed out in `proposals` (J3); after J3, 72 PASS |
| `run_interrupt_policy_e2e.sh` (#771), with J2 | 17 PASS, among them "a single immediate message" and "it is the decision message, with its buttons" |
| Console Playwright, plain stack (landing, proxy, shell, account, theme, language, design, mock journeys) | 30 passed, 12 skipped (opt-in live specs), 1 failed (`governance.spec.ts`, J4); after J4, it passes |
| `web/incident-console/e2e/run-inbox-real.sh` (#902) | 7 passed |
| `scripts/run_incident_console_e2e.sh` (#914) | first run: 1 failed, 3 not run (J5); after J5, 4 passed |
| Local full flow, scripted model ([local-flow.md](local-flow.md)) | passed 4 times (Telegram and console decisions), and once more by replaying the guide's commands from a clean clone |
| Local full flow, real model (`anthropic/claude-haiku-5.5`, `anthropic`, timeout 30 s) | 2 runs, $0.00758; the second found the latest-run bug (P2) |
