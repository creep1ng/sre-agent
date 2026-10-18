# Demo runbook — Monday, October 19, 2026, 17:00 Bogotá

Operator guide to run the demo end to end without opening pull requests for commands. Every
result below comes from a recorded run against the listed SHA; do not paraphrase them into
stronger claims. Demo slice ownership: T1 investigation (Daniel, #37/#651/#652), T2 decisions
(Daniel, #41/#653), T3 postmortem slice (producer Camilo, consumer Daniel, #43/#335).

**Hard rule at the podium:** the T2 fixture surface and the T3 view do not prove a backend
behavior. Say so before showing them. As of October 17, 17:41 COT the command contract
`run-command:2.1.0` is unpublished; on the release-candidate exploration (recorded in issue
#42/#52 vs `main aa789d9c`) the commands `verification_passed` and `close_incident` return
**422** on the published envelope `run-command:2.0.0`. If Camilo publishes the contract
before the demo: check the new SHA, rerun the affected commands once real, and update this
runbook with that evidence — never swap the script silently.

**Authoring limitation:** this runbook was assembled from the runs recorded in the cited
evidence; it was NOT re-executed end to end from a clean checkout while authoring. The
Sunday rehearsal below is the moment to confirm every command for real — do not mark that
checklist passed until someone executes it and records the actual outputs.

## Checkouts and SHAs (one worktree per slice)

```sh
git fetch origin
git worktree add ../sre-demo-37 e69f3750f59709d223f50864fb5b89c8d8edb0eb   # T1, PR #652 head
git worktree add ../sre-demo-41 b3cac7500425ab7d84b142e5c667153b1df360ec  # T2, PR #653 head
# T3 uses the T1 checkout (its postmortem view equals main's at that SHA).
docker compose --profile checks build python-checks
docker compose --profile e2e build e2e
```

Run the image builds from each worktree (`docker compose --profile checks build python-checks`
and `docker compose --profile e2e build e2e`); the images have no fixed tag, they are named
after the checkout folder (`<folder>-python-checks:latest`, `<folder>-e2e:latest`). The blocks
below resolve that name with `P=$(basename "$(pwd)")`.

Credentials come from the repo's `.env` via `set -a; source .env; set +a` (never printed).
Required names: `POSTGRES_*`, `ADMIN_HUMAN_API_KEY`, `AUDIT_HMAC_KEY`, `DEMO_HUMAN_API_KEY`
and `RESTRICTED_HARNESS_API_KEY` — compose interpolation carries them into the containers.

## Timeline (monday)

| Time (COT) | Step | Measured/estimated |
| --- | --- | --- |
| 16:15–16:20 | Preflight: checkouts, `.env`, free host ports (web 8091, api 8011, postgres 5439) | estimated |
| 16:20–16:23 | T1 stack up + provision + seed | provision and seed durations not recorded — plan for a few minutes |
| 16:23–16:25 | T1 real spec in the e2e container | recorded 4 passed in 7.8 s (run 39003786122, #652) |
| 16:25–16:27 | T1 war room live journey + evidence capture | capture script: single shot |
| 16:27–16:31 | T3 identical stack: postmortem fixture view | navigation only |
| 16:31–16:36 | T2 fixture captures from the e2e container | durations not recorded — plan for a few minutes |
| 16:36–16:40 | Contingency sweep and podium table review | — |
| 17:00–17:20 | Demo: T1 journey → T3 view → T2 captures → limits | — |
| after | Cleanup (no `-v`, no shared volume delete) | — |

## Preflight checks (do not skip)

```sh
docker ps --format '{{.Names}} {{.Status}}' | grep sre-agent-37   # nothing expected yet
git -C ../sre-demo-37 status --short && git -C ../sre-demo-41 status --short
nc -z 127.0.0.1 8091 || echo "port 8091 free"                     # also 8011, 5439, 4173
ls .env >/dev/null && echo "env present"                          # run inside the worktree dir
```

## T1 — real investigation (#652 head `e69f3750`)

**Monday stamps — the rehearsal stamps are consumed.** The stamps the October-18 rehearsals
already seeded and exercised — `2026-10-19-spec`, `2026-10-19-live` and `2026-10-19-cap`,
plus their `-r2` variants — carry persisted runs on the demo volume, so reusing any of them
fails by design (`#run-start` hidden for the real spec, runs already attached to the
presenter journey). For the demo use the fresh stamps `2026-10-19-spec-mon`,
`2026-10-19-live-mon` and `2026-10-19-cap-mon`, verified against the seed script's required
pattern `^[a-z0-9-]{4,32}$`; the commands below already carry them. Keep each stamp only in
its own step, coherent between its seed and the spec, journey or capture executed against
it. If another rehearsal consumes the `-mon` stamps too, seed with a different, unused
suffix — never delete volumes or data to force clean incidents. The `-mon` sequence has not
been executed yet; its first real run is the Monday flow itself.

Run from `../sre-demo-37`. Every independent Compose invocation of project `sre-agent-37`
must carry the port overrides ON the command line —
`WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose …` — because command-line
prefixes beat both the `.env` and a sourced environment. A one-time `export` is NOT
sufficient: the block below sources `.env` for the credentials, and that reload re-sets
`POSTGRES_PORT=55433` / `API_PORT=8000` / `WEB_PORT=8080` (the October-18 rehearsal hit the
resulting bind failure against the main `sre-agent` stack).

```sh
# Port overrides ride ON every compose invocation: command-line prefixes beat the
# .env defaults (POSTGRES_PORT=55433 / API_PORT=8000 / WEB_PORT=8080) and any
# sourced environment. Do NOT rely on a prior export — this block sources .env
# for the credentials, and that reload resets those ports (the October-18
# rehearsal hit the resulting bind failure against the main `sre-agent` stack).
P=$(basename "$(pwd)")
# 1) Stack up (recorded healthy in #652's acceptance runs)
WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 up -d --build db api web
# 2) Provision grants once per fresh database (fresh-db summary: catalog 201 and
#    five grants 201 active; on the persisted demo volume expect 409s — see the
#    note below the block)
set -a; source .env; set +a
WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 --profile checks run --rm \
  -e DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  -e ADMIN_API_KEY="${ADMIN_HUMAN_API_KEY}" -e AUDIT_KEY_HEX="${AUDIT_HMAC_KEY}" \
  python-checks python scripts/provision_incident_workflow.py
# 3) Seed the three stamped incidents (idempotent)
WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 --profile checks run --rm \
  -e DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  -e SEED_STAMP=2026-10-19 \
  python-checks python scripts/seed_war_room_runs.py
# 4) Seed and run the real acceptance spec on its OWN stamp: fresh ids are
#    "active with no runs" by construction; the spec asserts #run-start visible
#    first, so reused stamps that already carry runs fail by design.
WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 --profile checks run --rm \
  -e DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  -e SEED_STAMP=2026-10-19-spec-mon \
  python-checks python scripts/seed_war_room_runs.py
WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 --profile e2e run --rm \
  -e SRE_REAL_BACKEND=1 -e SEED_STAMP=2026-10-19-spec-mon \
  e2e npx playwright test --config=playwright.production.config.js \
  tests/browser/war-room-runs-real.spec.js
# 5) Seed the presenter's own stamp for the live journey: clicking Iniciar needs a
#    run-less incident; the spec's stamp already holds its run.
WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 --profile checks run --rm \
  -e DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  -e SEED_STAMP=2026-10-19-live-mon \
  python-checks python scripts/seed_war_room_runs.py
# 6) Seed the capture's own stamp, then capture (the script waits for #run-start
#    visible and derives inc-37-start-<stamp> from SEED_STAMP; evidence lands in
#    this checkout at SHA e69f3750).
WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 --profile checks run --rm \
  -e DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  -e SEED_STAMP=2026-10-19-cap-mon \
  python-checks python scripts/seed_war_room_runs.py
docker run --rm -e PLAYWRIGHT_BASE_URL="http://host.docker.internal:8091" \
  -e DEMO_HUMAN_API_KEY="${DEMO_HUMAN_API_KEY}" -e SEED_STAMP=2026-10-19-cap-mon \
  -v "$PWD/docs/evidence:/e2e/docs/evidence" -v "$PWD/scripts:/e2e/scripts-capture:ro" \
  -w /e2e "${P}-e2e:latest" node scripts-capture/capture_issue37_war_room_runs.mjs
```

**Provision result depends on the database state.** On a fresh database the recorded summary
is "catalog 201 and five grants 201 active". The demo never deletes data, so on the persisted
demo volume the same script can return **409 already-exists** for the catalog and grant
writes; the October-18 rehearsal recorded that case, and its printed summary confirmed
`run_read_active`, `run_start_active`, `run_command_active` and `run_approve_active` all
`true`. Accept a 409 ONLY after reading the script's printed summary and confirming there
that every required grant is present and active. A different conflict, a missing grant or an
inactive one: stop the flow and record the real error. That printed summary is the only
verification the harness documents for this step — this guide has no separate read-only
inspection command for grants, so do not improvise SQL.

Live podium journey: reuse step 5's seeded `2026-10-19-live-mon` stamp, open
`http://127.0.0.1:8091/public/incident-ui/war-room.html?incident_id=inc-37-start-2026-10-19-live-mon`,
connect the session with the demo human key, click *Iniciar investigación*, show the run strip,
then reload the tab — the created run stays selected (the real spec asserts this).
`inc-37-double-2026-10-19-live-mon` demonstrates the double-click idempotence; `inc-37-restricted-2026-10-19-live-mon`
with the restricted key shows the 403 with no success state.

**Real-recorded vs not:** start with reload persistence, double-click idempotence and the
restricted 403 are real (spec, containerized). **Resuming an existing investigation run and a
409 conflict stay covered by mock specs only** — say it if asked; do not demo them as backend
behavior. #42's exploration additionally observed that with the LLM disabled a run ends
`unknown / investigation_needs_human` while still `running` — the investigation strip of the
T1 branch does not change that (out of demo scope; known presenter answer below).

## T3 — postmortem fixture view (same stack)

```sh
# T1's stack is still up; open the Postmortem view for the seeded incident:
open "http://127.0.0.1:8091/public/incident-ui/postmortem.html?incident_id=inc-37-start-2026-10-19"
```

The page shows `pm_demo0001` with its own banner: "Sin artefacto persistido en el backend
(#335 pendiente): abajo, fixture de presentación." Present exactly that: **no persistence, no
restart survival, no versioning, no human review recorded** — the producer (Camilo) ships the
persisted artifact contract; consumer-side work cannot assume a transport. No file edits make
this view "real"; it stays fixture by design.

## T2 — decisions as fixtures (#653 head `b3cac750`)

Run from `../sre-demo-41`. This produces fresh fixture captures and screenshots of the UI
states — it does **not** touch any backend. The seven PNGs already committed at this SHA are
the fallback if the live capture run fails.

```sh
P=$(basename "$(pwd)")
docker run --rm -d --name demo-review-static -v "$PWD:/site:ro" --workdir /site \
  "${P}-python-checks:latest" python -m http.server 4173 --bind 0.0.0.0
docker run --rm --network container:demo-review-static \
  -v "$PWD/tests/browser:/e2e/tests/browser:ro" -v "$PWD/scripts:/e2e/scripts-capture:ro" \
  -v "$PWD/docs/evidence:/e2e/docs/evidence" -w /e2e "${P}-e2e:latest" sh -c \
  'PLAYWRIGHT_BASE_URL=http://127.0.0.1:4173 node scripts-capture/capture_issue41_review_states.mjs'
docker stop demo-review-static
```

Expect seven JSON lines tagged `fixture: "mocked-backend"`, writing
`docs/evidence/41-review-fixtures-{mitigating,verifying,resolved,closed,postmortem-panel,conflict,conflict-recovered}.png`.
Walk the states from the images: buttons gate by state; `postmortem-panel` shows the explicit
approval unchecked with the submit disabled; `conflict` shows the 409 alert; `conflict-recovered`
shows version 8 with the reason preserved and the approval unmarked. Podium sentences:

- "This is the sanctioned contract state gating, proved with fixtures; the transport is not
  exercised — on `main e5c542d7` these commands return 422 (recorded run in issue #42)."
- If the contract landed: run one real command from the ticketed checkout and replace this
  table row after that run; do not silently reuse the fixture captures.
- Do not open `review.html` directly in the podium browser: without the capture script's route
  mocks there is no console session, so the page will not reproduce these fixture states.

## Sunday rehearsal (October 18) — operator checklist

Run the Monday blocks above once today against the same pinned checkouts; the rehearsal is
not marked passed by this document alone — someone must execute it and record real results.

- [ ] Preflight at the pinned SHAs: builds done per checkout (tags `<folder>-…`), `.env` keys
      present, ports 8091/8011/5439/4173 free, `docker ps` without sre-agent-37 leftovers.
- [ ] T1 real flow with the inline port prefixes on every compose call: provision (fresh db
      prints the "201" summary; the persisted volume prints 409s whose summary must confirm
      every grant active), then per-stamp seeding — `…-spec` for the real spec (expect 4
      passed), `…-live` for the presenter journey, `…-cap` for the capture — three fresh
      stamps never reused across steps.
- [ ] Captures land inside the pinned worktrees: note the head SHA beside each generated PNG
      (T1 at `e69f3750`, T2 at `b3cac750`).
- [ ] T3 shows the fixture banner; T2 walks the capture images as fixtures, never backend.
- [ ] Record actual outputs and any failure verbatim (time, command, output); anything that
      deviates from this runbook enters the demo notes for Monday; old runs are never
      presented as new proof.

Recorded October-18 rehearsal outcome (real run on the persisted demo volume): the first
attempt failed on infrastructure — the block's one-time `export` was overwritten by
`set -a; source .env` (the `.env` carries `POSTGRES_PORT=55433`) and the e2e invocation
recreated db/api/web toward the busy port; re-running every compose call with the inline
port prefixes unblocked it. After that: the real spec passed 4/4 in 5.5 s on the fresh
`-spec` stamp, the live journey created `run_07ee18b58985f600` (POST 201, the same run
re-selected after reload) and the T1 capture recorded `run_c21e2276988d940d`; T2 regenerated
all seven fixture captures tagged `fixture: "mocked-backend"` and T3 showed the fixture
banner with `pm_demo0001 · draft`. The recovery does not excuse the failure above: the flow
as amended NOW is what the Monday operator executes, and this runbook is only declared
reproducible after that corrected flow runs end to end.

## Contingencies and known limits

| Symptom | Cause | Recovery |
| --- | --- | --- |
| Ports clash / db recreated on wrong port | missing `WEB_PORT/API_PORT/POSTGRES_PORT` flags | stop the project, redo every compose call with the inline `WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439` prefix — on the command line, never as a prior `export` |
| E2E container loses web reachability | compose.e2e.yaml overlay strips published ports | re-up WITHOUT the overlay: `WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439 docker compose -p sre-agent-37 up -d db api web` — the prefix rides on the command even mid-block, because a sourced `.env` resets the ports (55433/8000/8080) onto ones the main `sre-agent` stack already owns |
| Start / double-click tests fail with `#run-start` hidden | the stamped incidents already carry runs from an earlier rehearsal on this volume | seed and run the affected steps with a NEW `SEED_STAMP` (`…-spec` / `…-live` / `…-cap` per T1 below); never delete data, never use `down -v` |
| Real spec fails once cold | first-run transient recorded on an untouched test | rerun once; second failure = inspect honestly, do not hand-wave |
| `.env` key missing | operator lacks a secret | stop and pull the authorized `.env`; never echo keys |
| Cross-view navigation quirks (war room → decisions/postmortem back-link, per-tab credential) | pre-#486/#654 state in these checkouts | use the deep-links of this guide; note #654 (Mario) is open, not merged |

Cleanup (after the demo / before the tablets close):

```sh
docker compose -p sre-agent-37 down     # no -v: keeps shared volumes untouched
docker ps --format '{{.Names}}' | grep demo-review-static || true
git worktree list                        # leave the worktrees for the week; unlink only on request
```

Docker witnesses with read-only SQL exist in the repo (`scripts/issue45_live_denial_witness.sh`,
`scripts/demo_mcp_gateway_probe.mjs`) but belong to other issues; T1's own containerized spec
already covers the demo's real 403/404/401 claims — witnesses stay out of this demo unless the
PO requests them.

## Evidence index (commits are the record)

- T1 acceptance CI run on the #652 head: `https://github.com/creep1ng/sre-agent/actions/runs/39004116747`.
- T1 real-spec record: `https://github.com/creep1ng/sre-agent/actions/runs/39003786122` (4 passed in 7.8 s, run ids recorded in #652).
- T2 fixtures committed: `https://github.com/creep1ng/sre-agent/blob/b3cac7500425ab7d84b142e5c667153b1df360ec/docs/evidence/41-review-fixtures-postmortem-panel.png` (plus the other six at the same SHA).
- T1 evidence PNG: `https://github.com/creep1ng/sre-agent/blob/e69f3750f59709d223f50864fb5b89c8d8edb0eb/docs/evidence/37-war-room-run-start.png`.
- Scope decisions: #41 (commands contract) and #335 (postmortem cut), both October 16.

Nothing here claims real-accepted verification/closure criteria for #41/#43: those wait for
the unpublished `run-command:2.1.0` and the producer's persisted artifact, plus human review.
