# Issue #330 CA1 — integrated HTTP creation and application restart

## Technical outcome

**PASSED controlled integration**, not human acceptance or issue closure.
The same run `run_084284a4f8a41001`, created exclusively by authenticated TCP
HTTP, survived a real packaged API restart. Its public state/events, authoritative
SQL rows, cursor and version were preserved. Replay and resume returned that run
without another run, event, snapshot or transition commit.

Tested HEAD: `c7d297cbb11059b1b958e2dece8d54d9db016e1c`.
Branch: `codex/triage-23-integrated`.
Checkout: `/tmp/triage23-publish/integrated` (explicitly confirmed by user).
Execution: 2026-10-07 America/Bogota; artifact timestamps use UTC (2026-10-08).
Candidate includes uncommitted verification tooling. No production source,
migrations, dependency lock or public contract was changed.
`verified/source-manifest.json` records SHA-256 hashes of all 3,083 tracked/new
files; `verified/implementation.patch` contains this task's changes.
The preexisting modified `odd/tasks/triage-23-stack-review.md` was preserved;
its diff hash is `9cd67e2b4c3ff327f9447029865f8618b39286333c708a8ca2d520c51cef30b3`.

## Real and controlled components

Real: packaged `sre_agent.main:app` under uvicorn; FastAPI TCP requests; bearer
credential authentication and persisted authorization grants; gateway and
IncidentRuntime; PostgreSQL 17.4; named Docker volume; actual process restart;
Chromium capture of live authenticated HTTP responses.
Controlled: synthetic local principals/credentials, one schema-valid incident,
workflow/grant provisioning through the existing ControlService, and the triage
objective. The base seed provisions governance prerequisites, **not the evaluated
run**. Incident preparation calls only the incident repository's `add` method.
No TestClient, SQL run insertion, previously seeded run, mock authorizer or
in-memory persistence participates in the evaluated journey.

No provider or mitigation invocation was performed. Runtime networks are internal,
provider credentials absent, configured routing values `controlled/no-model` and
`controlled` are placeholders. CA6 / #567 and external exactly-once are excluded.

## Expected versus observed

| Step | Expected | Observed / evidence |
|---|---|---|
| Preconditions | Human with real `run.start` / `run.read`, valid incident, no run | Synthetic `demo-human`; two persisted active grants and valid credential. Schema-valid incident. HTTP detail `runs=[]`; SQL runs/events/snapshots/commits empty in `verified/ca1-before.json` preflight. |
| HTTP create | Unique Idempotency-Key and admitted body; 201 | TCP POST `/v1/incidents/inc-ca1-http-restart/runs`, body `{"workflow_version":"1.0.0","objective":"triage"}`. Unique key retained in before JSON; run ID extracted from schema-valid 201 response. |
| Immediate reads | 200 state/events, SQL agrees | `triage`, `running`, `seq:0`; version **1 from SQL only**. One run, event sequence 0, snapshot version 1 / event_sequence 0, transition commit correlated to original key/run. Public event IDs/order match SQL; snapshot run/incident states match their rows. |
| Real restart | Old process ends; new process uses same DB/volume | Scoped `docker compose ... restart --no-deps api`; API PID and StartedAt change below. DB identity, PID, StartedAt, image and volume mount match exactly. No re-provisioning or second create after restart. |
| Durable reads | Same IDs, state, cursor and all durable records | Post-readiness HTTP state and event page equal baseline; immediate post-restart SQL comparison passes before replay/resume. Final SQL also equals baseline including timestamps, state, version, event IDs/sequences, snapshots and transition commits. |
| Replay | Original key/body returns 200; no duplicate | Same full run-state response, one run/event/snapshot/commit. |
| Resume | `resume_from_run_id` returns 200 and same identity | Same full run-state response. New resume key, no added durable records. This implementation **rereads state/cursor**, not automatic execution or new transitions. |
| Persisted denial | Anonymous and credential without read permission rejected | Both state and events: anonymous 401, existing `restricted-harness` credential 403. No credentials or grants regenerated for after-phase checks. |

Schemas actually inspected/used: `agent/api/incident-runs.openapi.yaml`,
`agent/schemas/run-start-request.schema.yaml`, `run-state.schema.yaml`,
`run-event.schema.yaml`, and `incident-state.schema.yaml`.
The public state schema has no `version`; no HTTP version field was invented.
SQL captures use `SET TRANSACTION READ ONLY`, filtered to this synthetic incident
in the real `incident.incidents`, `incident.runs`, `incident.run_events`,
`incident.snapshots` and `incident.transition_commits` tables.

## Restart and storage identities

Project: `ca1-01a118c1-verified`.
API container: `f4d0b11566cb0b8bb9ad92b25a05a585b2672faaf5d1adf3864c4b4c71f50d27`.

| Field | Before | After |
|---|---|---|
| API PID | 289577 | 307918 |
| API StartedAt (UTC) | 2026-10-08T00:14:30.112656943Z | 2026-10-08T00:15:24.348037006Z |
| DB PID | 278089 | 278089 |
| DB StartedAt | 2026-10-08T00:13:56.705306352Z | Identical |
| DB volume | `ca1-01a118c1-verified_postgres_data` | Identical |
| DB mount | `/var/lib/postgresql/data`, type `volume`, driver `local` | Identical |

DB container: `d57b51cf279c0ab2e342d3159549d858cc71bf8fc8660d31d94a5351ec41c23d`.
`verified/containers-before.jsonl` and `containers-after.jsonl` retain full narrow
identity/mount comparisons. `verified/checks-db-storage.json` independently shows
that the **different** `python-checks-db` uses tmpfs, with no persistent mounts.
Destructive pytest fixtures were confined to that checks database, never the
persistent demonstration database.

API image: `ca1-01a118c1-verified-api@sha256:63f46bfa4f927e4efba920fa468602a0cc163c1dc859d79bf41a6a84342bded4`.
Checks image: `ca1-01a118c1-verified-python-checks@sha256:848c45bbb52f9728761794428ab653b8b488b46932498ac6c008e7e056ff093e`.
PostgreSQL image: `postgres:17.4-alpine@sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5`.
Python base is pinned in `docker/api.Dockerfile` to
`python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.
Docker client/server 29.8.2; Compose 5.6.0; runtime Python 3.12.14; PostgreSQL 17.4;
pytest 8.3.5; ruff 0.11.7; locked application dependencies.
Application 0.1.0, schema release 2.7.0, incident workflow/run schemas 1.0.0.
Non-secret configuration: internal `10.253.142.0/28` network; local API port
58142, PostgreSQL port 58143; database `ca1_http_restart`, role `ca1_local`.
`verified/runtime-source-hashes.txt` matches host hashes for gateway runs/reads,
persistence incidents and uv.lock, confirming packaged source provenance.

## Reproduction

Check out PR branch `codex/ca1-http-restart-proof` and run the following from the
repository root. The publication head may receive documentation-only updates;
the historical integration result above is tied to tested SHA
`c7d297cbb11059b1b958e2dece8d54d9db016e1c`; later reproduction tooling and this
report do not change that historical result. `verified/implementation.patch` is
an archival record, not an additional patch to apply to the PR branch. Use a **new
exclusive** project, unused ports and unused subnet for every complete repetition.
The runner refuses to overwrite an existing synthetic incident.

Host prerequisites are Git, Python 3, and Docker Compose. Before setup, inspect
Docker networks read-only and choose an unused private IPv4 `/28`, project name
starting with `ca1-`, distinct unused API/database ports, and two non-overlapping
directories outside the repository for private config and evidence. The generator
validates the project, subnet, ports, required Compose variables, isolated tmpfs
checks database, and evidence mount. It creates `local.env` exclusively at mode
0600 and refuses to replace either generated file. Secrets are not printed. By
default `SRE_AGENT_BUILD_REVISION` is derived from the checkout's current Git HEAD;
`--build-revision` may pin an explicitly known hexadecimal revision. The historical
result below remains tied to the tested SHA and is not changed by this setup tool.
This standard-library host operation only prepares local configuration; all
application/schema/test tools execute in Docker. Do not attach the private env file.

Example safe setup (choose an unused subnet first by read-only Docker inventory):
run these commands from the checked-out PR repository root.

```sh
python3 scripts/prepare_ca1_config.py \
  --project ca1-local-repro --private-dir /tmp/ca1-local-repro-private \
  --evidence-dir /tmp/ca1-local-repro-evidence --subnet 10.253.143.0/28 \
  --api-port 58144 --db-port 58145
CA1_ENV_FILE=/tmp/ca1-local-repro-private/local.env \
CA1_OVERRIDE=/tmp/ca1-local-repro-private/compose.proof.yaml \
CA1_EVIDENCE_DIR=/tmp/ca1-local-repro-evidence \
CA1_PROJECT=ca1-local-repro scripts/prove-ca1-compose
```

The runner's container commands are: build `api` / `python-checks`, scoped
`up -d --no-build api` (its migrate/seed/db dependencies), then `python-checks`
`prepare` and `before` phases using the demonstration URL **only for this
non-destructive proof**. It records identities, restarts **only api**, waits on
`/health/ready`, and invokes `after`. Inside the proof runner the demonstration
URL is passed through environment, never placed in command-line text or logs.
No pytest or table-deleting fixture runs in these phases.

Actual final runner invocation used the same command structure with private inputs
under workspace `work/ca1-verified`, project `ca1-01a118c1-verified`, and evidence
under `outputs/ca1/verified`. `verified/journey.log` is the original stdout/stderr
capture, including the exact candidate SHA and real Docker actions.

To run ordinary checks, use a separate checks URL (Compose already does this):

```sh
docker compose --env-file /tmp/ca1-local-repro-private/local.env \
  -f compose.yaml -f /tmp/ca1-local-repro-private/compose.proof.yaml \
  -p ca1-local-repro --profile checks run --rm python-checks
```

Additional scoped checks/captures are documented in `reproduction-commands.txt`.
For cleanup, stop **only your named project's** services; keep its volume.
Never `down -v`, `prune` or restart any other project. Failed rehearsal projects
and their volumes have deliberately been preserved in this environment.

## Captures and artifact review

`verified/http-state-after.png` and `http-events-after.png` are screenshots of
**live TCP responses from the actual API after restart**, using Chromium from the
existing built `e2e` service as a capture tool. `capture.js` uses the unchanged
demo credential in memory, checks HTTP 200 and exact semantic equality to the
verified JSON, then captures the response page. The body is native browser JSON,
not a drawn terminal, generated result card, mock server or reconstructed run.
Images were opened and visually inspected: run ID, triage state, cursor and event
are legible; no Authorization, credentials, prompts or sensitive payloads appear.
The `e2e` service's application/browser test suite was **not** run by this capture.
Capture image identity is recorded alongside API/checks identities.

Diff review: only the Python HTTP/SQL harness, Compose lifecycle runner and new ODD
task document were authored. No production behavior fix was necessary. Checked
schema/request boundaries, bearer handling, phase separation, SQL read-only mode,
exact restart comparisons, replay/resume row counts, scoped restart and absence
of volume deletion/remote operations. The two source units intentionally retain
readable checks (~505 lines combined); no lines/tests were hidden or minified.
No commit, push, PR, GitHub issue mutation, remote execution or file transfer occurred.

## Checks, failed attempts and limitations

- **PASSED:** final integrated journey, exit 0 (`verified/journey.log`).
- **PASSED:** related four suites: 34 tests initially (36.10s), then 34 on the
  exact verified image (66.62s), guard checked before fixtures. See
  `related-tests.log` and `verified/final-checks.log`.
- **PASSED:** full Python suite twice: 1,774 passed / 1 skipped on the initial
  checks image (715.02s, `full-tests.log`) and on the final HTTP/SQL harness image
  (663.70s, `final/repository-checks.log`). These are local, not hosted CI.
  The second full-suite image contains the final Python harness and unchanged
  application/test sources; its Compose runner predates only the ancillary
  empty-event-cache fallback. The exact passing runner is exercised by the final
  journey and shellcheck on the verified image. Full-suite image/hash provenance
  is in `final/full-suite-image.json` and `full-suite-source-hashes.txt`.
- **PASSED:** isolation guard, shellcheck (including new lifecycle runner), ruff
  lint/format, uv lock check, 5 import architecture contracts, mypy (12 source
  files), alembic check (no new upgrade operations), and Python incident contract,
  authorization, run API, incident query and CI hardening validators. The exact
  verified-image pipeline exited 0 (`verified/final-checks.log`).
- **PASSED:** native HTTP response captures (HTTP 200 and JSON equality), visual
  inspection, independent before/after JSON equality, runtime-to-host source hash
  comparison, diff whitespace review and actual private-secret-value scan.
- **SKIPPED:** `tests/test_openrouter_live.py::test_openrouter_gateway_live_smoke`,
  deliberately disabled (`RUN_OPENROUTER_LIVE_SMOKE=0`) to avoid external effects.
- **PENDING / RUNNING, not claimed passed:** broad npm schema-tooling `test` in
  `ca1-01a118c1-harness-run-a847b3381c59`. No final TAP summary was available at
  delivery; last emitted subtest was 52. `schema-tooling-progress.log` freezes that
  progress snapshot; `schema-tooling.log` remains the live output. This broader
  release-tooling diagnostic is separate from the passing run-API validators and
  the integrated CA1 assertions. The chained `validate`, `validate:releases` and
  `lint:openapi` stages have **NOT EXECUTED yet** while `test` runs. Collect its
  eventual result before claiming all repository-wide contract checks green.


- **FAILED, retained rehearsal:** the first runner used old Docker event template
  fields `.Status` / `.ID`; Docker 29's Message uses `.Action` / `.Actor.ID`. It
  stopped after a real restart and before after-phase verification. Original
  `journey.log` and container records at this report's directory remain intact.
- **FAILED, retained rehearsal:** the second runner required cached die/start events,
  but the cache query was empty. Its log and records are in `final/`. This was an
  unnecessary ancillary gate, not an observed application persistence defect.
- **SKIPPED ancillary evidence in passing run:** Docker lifecycle-event cache remains
  unavailable. `verified/restart-events.jsonl` is empty, explicitly acknowledged
  in the log. Required restart proof passed using changed PID/StartedAt and actual
  scoped restart, with unchanged database process and named persistent volume.
- **FAILED preparation, recovered:** Docker's default subnet pools were exhausted;
  selected unused explicit internal subnets by read-only network inventory.
  No networks/volumes were deleted and no other project's services were touched.
- Initial harness lint/format checks failed; corrections precede the passing final
  image and proof. Final check results are recorded separately, not normalized.
- **NOT EXECUTED:** external provider/effect smoke (CA6), production, browser UI E2E
  suites, hosted CI, remote exact-head review, RDD review and independent human
  acceptance. RDD remains off, deciding source global: **disabled/unmanaged**.
- Public GitHub issue/Projects lookup was unavailable; no authorized authenticated
  remote session was supplied or used. The user's scenario bounds this local proof;
  no claim about live Project status or human CA1 acceptance is made.
- Scope is one triage start transition, persistence across API process restart,
  safe reads, replay and state/cursor reread on resume. This does not prove database
  disaster recovery, automatic continuation, later transitions or external
  exactly-once. No contract was changed or broadened.

Sanitized: yes — private input files excluded; evidence fields deliberately selected;
actual secret-value scan and visual capture inspection performed before delivery.

Next step: collect the pending broad npm diagnostic result, then independent local
review/reproduction of the technical CA1 evidence. No issue closure or acceptance
has been performed.
