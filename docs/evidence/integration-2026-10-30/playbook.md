# Merge playbook: open PRs of 2026-10-30

Rehearsed on `t3/integration-rehearsal-2026-10-30` (draft PR #841, **do not merge**), built from
`origin/main` `687a30e1ba2685ff52aa09186abc57b16f36dc01`. Every PR head below was merged with
`git merge --no-ff` in this order; the extra commits are on that branch, one per playbook entry,
so each can be cherry-picked or replayed.

Skipped: #816-#820 (#765, stacked on the unmerged #704) and #826 (#762, still being fixed).

## How to use it

The repository allows merge commits only and deletes the head branch on merge, so a stacked PR
is retargeted to `main` once the PR under it merges. For every step:

1. Merge the PR on GitHub, unless the step lists an extra commit or a conflict.
2. If it does, update the PR first so `main` never holds a broken state: in the PR branch,
   `git merge origin/main`, resolve as described, add the extra commit, push, wait for its CI,
   then merge. Two `20261030_01` revisions on `main` at once make Alembic report two heads and
   `/health/ready` answer `503`, so a renumbering must never wait for a follow-up PR.
3. Re-run the listed checks (all run in containers; see [Checks](#checks)).

The rehearsal commits are the reference resolutions: `git show <sha>` gives the exact diff.

## Steps

| # | PR (head) | Before merging | Re-run |
| --- | --- | --- | --- |
| 1 | #823 grants (`8e03d308`) | Nothing. Keeps `20261030_01` (`down_revision = 20261018_01`). | unit; grants E2E |
| 2 | #800 chat outbox (`c276e72e`) | Rename its migration to `20261030_02` and chain it after #823: commit `e29185e8`. No textual conflict. | unit; Telegram E2E after #802 |
| 3 | #801 Telegram gateway (`bb5fa782`) | Nothing. | unit |
| 4 | #802 Telegram E2E (`85a18988`) | Nothing. | Telegram E2E |
| 5 | #804 change events (`b2d9e1f3`) | Conflicts on the head pins only (8 files); keep `main`'s value, then rename its migration to `20261030_03` after `_02`: commit `6e84f4dc`. | unit; `run_real_journeys.sh incidents` |
| 6 | #805 record-change action (`69151d48`) | Nothing. | none beyond CI |
| 7 | #806 investigator changes (`1a4141b0`) | Nothing. | unit |
| 8 | #824 executor rollback change (`504c7998`) | Nothing. | `run_real_journeys.sh executor` |
| 9 | #808 consumption bounds (`d8776350`) | Nothing. | unit |
| 10 | #809 consumption E2E (`37145953`) | Nothing. | unit |
| 11 | #833 consumption journey (`2cbfd1bd`) | Conflict in `scripts/run_real_journeys.sh` (merge `d6010e7f`), see [R1](#r1-scriptsrun_real_journeyssh-833-and-828-against-804). | shellcheck; `run_real_journeys.sh incidents` |
| 12 | #828 provider retry (`ad97b2d4`) | Conflict in the header comment of `scripts/run_real_journeys.sh` (merge `3fcfc143`), see R1. | shellcheck; `run_real_journeys.sh incidents` |
| 13 | #822 dispatch terminal (`214aa454`) | Nothing. | unit |
| 14 | #834 run endings (`e0ad2bca`) | Nothing. | unit |
| 15 | #825 dispatch reason (`633e887a`) | Conflict in `src/sre_agent/gateway/investigation.py` (merge `55833e35`), see [R2](#r2-gatewayinvestigationpy-825-against-828). Then its merge note plus #828's new code: commit `6ad1859d`, see [N1](#n1-commit-6ad1859d-after-825). | unit (`tests/test_incident_investigator_http.py`); provider-retry E2E |
| 16 | #829 denied run retry (`fad0a61b`) | Nothing. | retry E2E |
| 17 | #830 evidence verdict (`4df1709e`) | Nothing. `incident-state` becomes 1.2.0; no PR in this set claims 1.2.0. **If #722 merges first, #830 must move to 1.3.0** (its own merge note). | unit; contracts |
| 18 | #831 empty citations (`9e774c78`) | Conflict in `gateway/investigation.py` (merge `f2384efe`), see [R3](#r3-gatewayinvestigationpy-831-against-the-r2-resolution). Then the #825 merge note for it: commit `5a6aaf57`, see [N2](#n2-commit-5a6aaf57-after-831). | unit; evidence-verdict E2E |
| 19 | #812 memory index (`5b8f682d`) | Conflicts on the head pins only (8 files); keep `main`'s value, then rename its migration to `20261030_04` after `_03`: commit `7dd52d3d`. | unit (migrations, health) |
| 20 | #813 incident recall (`6f60f64d`) | Conflicts in `public/console/incident-reasoning.js` and `gateway/investigation.py` (merge `2a087d77`), see [R4](#r4-813-against-830-and-831). | unit; recall E2E |
| 21 | #814 recall E2E (`34d59192`) | Nothing. | recall E2E |
| 22 | #811 contracts lock (`99af65ce`) | Nothing. | contracts |

Full heads are in the PR body of #841. No other PR adds a `20261030_<issue>` revision. The final
chain is `20261018_01` → `20261030_01` (#823 grants) → `_02` (#800 chat outbox) → `_03` (#804
change events) → `_04` (#812 incident memories), and `REQUIRED_SCHEMA_VERSION` is `20261030_04`.

### Renumbering commits (steps 2, 5, 19)

Each one renames the file, sets `revision` and chains `down_revision` to the previous head, and
replaces the old head pin with the new one everywhere outside `migrations/` and `docs/`:
`src/sre_agent/gateway/health.py:9`, `scripts/grant_regrant_e2e.py:138` (#823's E2E pins the
head), `tests/test_health.py:22,47,79`, `tests/test_migrations.py:636,668`,
`tests/test_skill_migration_compatibility.py:119,184,199,265`, `tests/test_bok_http.py:835`,
`tests/test_consumption_reservation_persistence.py:140`, `tests/test_demo_seeds.py:241` and
`tests/test_incident_persistence.py:708`. Find them with `git grep -n 20261030_0 -- ':!docs'`.
`docs/evidence/issue-759/issue-759-e2e.txt` keeps `20261030_01` on purpose: it is #823's
recorded evidence. The new tables live in the `incident` schema, so the test reset lists need no
change (the full suite passed).

### R1. `scripts/run_real_journeys.sh` (#833 and #828 against #804)

#804 appended the change-events journey; #833 appended the consumption E2E at the same place and
#828 extended it with the provider-retry E2E. Keep both: the change-events journey runs before
`consumption` (`scripts/run_real_journeys.sh:136-138`), because `consumption` restarts the API
against the OpenRouter stand-in and must stay last. The header comment (lines 5-13) names all
journeys, including #804's executor sentence.

### R2. `gateway/investigation.py` (#825 against #828)

#828 sets `reason_code="tool_timeout"` when the diagnostic stage is `tool_timeout`; #825 sets
`investigation_tool_unavailable` for any `upstream_unavailable` whose detail starts with
`tool failed:` (a timeout is one of those). Both PRs test their code: #828's
`scripts/provider_retry_e2e.py` check 4 expects `tool_timeout`; #825's
`tests/test_incident_investigator_http.py` expects `investigation_tool_unavailable` for a lost
or rejected MCP answer, which is not a timeout. Resolution: `tool_timeout` first, then
`investigation_tool_unavailable`, then `investigation_<status>`. After step 18 this chain lives
in `_ended_reason` (`src/sre_agent/gateway/investigation.py:948-957`).

### N1. Commit `6ad1859d` after #825

- #825's merge note: `investigation_tool_unavailable` in #800's Spanish `REASONS`
  (`src/sre_agent/chat/outbox.py:268-270`).
- Not in any merge note: #828 adds the code `tool_timeout`, which no vocabulary knows, so the
  timeline cause and the Telegram notice would project it as `null`/"la investigación no
  terminó". Added to `DISPATCH_CAUSES` (`src/sre_agent/incident/reasons.py:22`), the war room
  (`public/incident-ui/war-room.js:50`) and `REASONS` (`src/sre_agent/chat/outbox.py:271`).

### R3. `gateway/investigation.py` (#831 against the R2 resolution)

#831 replaced the inline expression with `reason_code=_ended_reason(result)`. Keep its call
(`investigation.py:344`) and move the R2 chain into `_ended_reason`, after #831's own
`investigation_no_measured_evidence` branch.

### N2. Commit `5a6aaf57` after #831

#825's merge note for #831: `investigation_no_measured_evidence` in `DISPATCH_CAUSES`
(`reasons.py:25`), the war room's `DISPATCH_CAUSES` with a Spanish sentence (`war-room.js:53`)
and #800's `REASONS` (`outbox.py:265`).

### R4. #813 against #830 and #831

- `gateway/investigation.py` imports: keep `UNMEASURED` (#831) and `CollectedEvidence` (#813),
  lines 32-33.
- Receipt: keep `agent_principal_id` (#825) and the outcome `notes` (#813), lines 803-806.
- Helpers: keep `_terminated_reason` (#822/#834) and `_cited_memories_only` (#813), lines 925-941.
- `public/console/incident-reasoning.js:187-188`: keep #830's finding under a shown verdict and
  #813's rule that a recalled memory shows no query line.
- Semantics checked: #831's `UNMEASURED_SOURCES` already contains `incident_memory`
  (`src/sre_agent/investigator/contract.py:272`), so a hypothesis citing only a recalled memory
  is rejected like one citing only BoK.

## Checks

Python checks run exactly as `.github/workflows/ci.yml` (job `checks-image`, then `unit`):

```sh
docker build --target checks --tag sre-agent-checks:local -f docker/api.Dockerfile .
docker run --rm -e TEST_DATABASE_URL=postgresql://python_checks@checks-db:5432/python_checks \
  -e DEMO_DATABASE_URL=postgresql://demo@demo-db:5432/demo sre-agent-checks:local sh -c \
  'python scripts/assert_test_database_isolated.py && shellcheck docker/harness-entrypoint.sh scripts/worktree-compose scripts/run_real_journeys.sh && ruff check --no-cache . && ruff format --check --no-cache . && uv lock --check --no-cache && lint-imports --no-cache && mypy --cache-dir=/tmp/mypy src/sre_agent/incident/persistence.py src/sre_agent/incident/runtime.py src/sre_agent/governance/dto.py src/sre_agent/governance/authorization.py src/sre_agent/investigator && python scripts/validate_incident_contracts.py && python scripts/validate_incident_authorization.py && python scripts/validate_run_api.py && python scripts/validate_incident_queries.py && python scripts/validate_ci_hardening.py'
docker compose --profile checks run --build --rm -e "PYTEST_ADDOPTS=-p no:cacheprovider" python-checks
docker compose --profile checks down -v --remove-orphans
```

E2E commands, one stack at a time (the `.env` is the CI one: `.env.example` with synthetic keys):

```sh
COMPOSE_PROJECT_NAME=journeys-inc scripts/run_real_journeys.sh incidents
COMPOSE_PROJECT_NAME=journeys-exe scripts/run_real_journeys.sh executor
COMPOSE_PROJECT_NAME=telegram scripts/run_telegram_e2e.sh
```

The grants (#823), run-retry (#829) and evidence-verdict (#831) E2Es use the reproduction
commands of those PRs; the recall E2E (#814) is `tests/test_incident_recall_e2e.py` in the
checks container.

## Results on the combined branch (head `38c7ad79`)

### Step 4: local verification

| Check | Result |
| --- | --- |
| ruff, ruff format, `uv lock --check`, lint-imports (6 contracts kept), mypy (11 files), 5 validate scripts, shellcheck | pass |
| Whole pytest suite | `1994 passed, 1 skipped` in 11 min 17 s |
| `run_real_journeys.sh incidents` | war-room-runs 5, war-room-reasoning 2, review-mitigation 2, war-room-follow 2, postmortem 1, change-events 1 passed; consumption `22 checks, 0 failed`; provider-retry `24 checks, 0 failed` |
| `run_real_journeys.sh executor` | executor, executor-changes, executor-socket-down: 1 passed each |
| Grants re-grant (#823) | 9 PASS; `/health/ready` 200 on `20261030_04` |
| Telegram (#802) | 25 PASS (linking, dispatch ack in 0.263 s, pending across two restarts, unlink) |
| Run lifecycle retry (#829) | PASS: a denied run ends `terminated_reason=denied` and a human retry opens a new run |
| Evidence verdict (#830/#831) | 18 PASS: logs-only and BoK+logs hypotheses rejected, receipt names "no cited evidence had measured data" |
| Incident memory and recall (#812/#814) | 2 passed, artifacts `recall.json`, `memory-change.json` |

### Step 5: one real-model scenario (2 real-LLM investigations, the cap)

Local OTel Demo (`scripts/demo_env.py`), `scripts/setup_sre.py` with paid LLM enabled
(`z-ai/glm-5.3-flash`, provider `relace`, `OPENROUTER_TIMEOUT_SECONDS=60`), the fake Bot API and
the Telegram gateway in the same project, chat `424242` linked with a one-time code.

1. `demo_env.py fail --service sre-checkout` deployed `demo/checkout:1.5.0`; `POST /v1/changes`
   (deploy, by the `deploy-executor` principal) answered `201`.
2. The live alert `checkout-orders-error-rate` fired; `triage_declare` opened incident 1.
3. Real investigation 1: the model called `midnight_recent_changes` and `query_prometheus`, and
   recorded a hypothesis citing both (both judged `supports`), then a mitigation.
4. `approve_mitigation`, `demo_env.py reset --service sre-checkout` (1.4.0), the rollback recorded
   as a change event, `verification_passed`, a postmortem run, postmortem v1 written and
   approved, `close_incident`: `closed`. The memory was indexed at once.
5. The first episode resolved; `fail` deployed 1.5.0 again, recorded as a second deploy change
   event; the new alert opened incident 2.
6. Real investigation 2 (76 s):
   - The hypothesis cites **measured evidence** (`query_prometheus`, 500s only on 1.5.0) and
     **the recalled memory** (`ev_mem_341893009477aa8f`, judged `supports`). It does **not**
     cite the change event: this time the model did not call `midnight_recent_changes`.
   - **#831's guard was not exercised:** the model never cited memory alone. Its first
     hypothesis (Prometheus + memory) came back as truncated JSON and was rejected as
     `Invalid JSON`; the retry turn recorded the hypothesis.
   - The next model call (the mitigation) exceeded the investigator's fixed 45 s gateway timeout
     (`src/sre_agent/investigator/client.py:57`), so the run ended `unknown`,
     `investigation_upstream_unavailable`, and `run_terminated`. The 60 s provider timeout from
     the 2026-10-19 demo runbook is longer than that client timeout. The abandoned gateway call
     left no access-log line and no `audit_events` row. #828's provider retry did not apply: no
     503 was observed.
7. The fake Telegram transcript received 5 messages: the link confirmation; for incident 1 the
   acknowledgment and "Mitigación propuesta, pendiente de tu aprobación en la consola."; for
   incident 2 the acknowledgment and "Sin conclusión: el proveedor del modelo no respondió
   (investigation_upstream_unavailable)."

The key was removed from `.env` afterwards and both projects were torn down.

### Step 6: hosted CI on #841

Run `41074733735` on `38c7ad79`: changes, configuration-lock, checks-image, unit, contracts,
compose-smoke, static-web, production-browser, real-journeys, triage-review, deploy-executor,
Quality gate and GitGuardian pass. `pr-governance` fails because #841 is a draft whose body is
not an evidence template. That failure belongs to the rehearsal PR, not to any PR in the set.

## Findings for the maintainer

- `tool_timeout` (#828) is missing from every cause vocabulary until commit `6ad1859d`; without it
  the war room and Telegram show no cause for a tool timeout.
- An `OPENROUTER_TIMEOUT_SECONDS` above 45 s makes the investigator give up before the gateway;
  keep it at or below 45 s for the demo, or make the investigator's gateway timeout follow it.
  The 2026-10-19 demo runbook recommends 60.
- The memory indexed from the incident declared from the live alert has `signal: null`; the
  #812/#814 E2Es insert their incidents with an origin signal (`checkout.requests`). The
  declaration in this run sent the same `alert_context` fields the console sends (service,
  summary, observed_at, source, severity). Recall still found the memory through the alert's
  words, but #813's same-signal ranking never applies to such incidents. Not traced further.
