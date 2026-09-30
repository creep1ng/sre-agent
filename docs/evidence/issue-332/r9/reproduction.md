# Issue #332 — Current-head evidence reproduction

This bundle is portable beside the source checkout's `compose.yaml`. It documents the frozen candidates below; use an exact SHA and the matching mode. It never reads/prints `.env` or `.env.worktree`. Prepare those ignored local files from the repository examples with only safe synthetic local settings, blank provider credentials, and live-provider smoke disabled. The probe generates API keys in memory and does not write them to JSON.

Before starting, verify `10.254.239.0/28` does not overlap a local route or Docker network. Docker must fail closed on a conflict; do not change global Docker IPAM, prune unrelated resources, or run two named evidence projects at once. Commands use only existing Compose `api`, `python-checks`, and `python-checks-db` services. `python-checks-db` is the checks-profile PostgreSQL service backed by tmpfs and has no host DB port. The isolation guard is run before migration and probes. No external provider, paid API, Jev, cloud, OTel, SSH, production, or concurrent writer is used.

Copy this bundle beside `compose.yaml` as `./evidence-issue332`; create its `results/` directory writable by your local UID. Source checkouts:

- Foundation F: `ea74a6e8970ff6b3cbf7ebef885fc97c5816da89`, base main `5b6109bd2c8100455136cf12ce91c52830833c7f`.
- Retrieval M: `c2f064f76e42e3257a21a261fe16b035d888fc7e`, base F `ea74a6e8970ff6b3cbf7ebef885fc97c5816da89`.

The two commands below run sequentially, not concurrently. Each creates a fresh checks-profile tmpfs database. The API runs attached in Terminal A; run the probe in Terminal B. Stop API with Ctrl-C after the probe completes, then execute that project's scoped `down` command. Do not use `-v`; project-created named-volume metadata is intentionally left untouched, while the test database contents themselves are tmpfs.

## Foundation F

```sh
PROJECT=issue332-foundation-r9
COMPOSE='docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml'
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks build api python-checks
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && alembic upgrade head'
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks run --rm --no-deps --service-ports --use-aliases --name issue332-foundation-r9-api -e DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e TEST_DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e OPENROUTER_API_KEY= api
```

While API is attached, in Terminal B:

```sh
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence:ro" --volume "$PWD/evidence-issue332/results:/results" -e EVIDENCE_RESULTS_DIR=/results python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py foundation ea74a6e8970ff6b3cbf7ebef885fc97c5816da89'
```

Observed exit 0: 16 observations, all assertions passed, schema `20260929_15`. This includes four owner activation/readiness cases and four separate persisted-child replay-drift cases. Read [`foundation-results.json`](results/foundation-results.json). After Terminal A Ctrl-C, clean only this project:

```sh
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks down
```

## Retrieval M

Only after the F project is down and its owned containers/network are gone, repeat with:

```sh
PROJECT=issue332-retrieval-r9
COMPOSE='docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml'
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks build api python-checks
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && alembic upgrade head'
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks run --rm --no-deps --service-ports --use-aliases --name issue332-retrieval-r9-api -e DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e TEST_DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e OPENROUTER_API_KEY= api
```

While API is attached, in Terminal B:

```sh
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence:ro" --volume "$PWD/evidence-issue332/results:/results" -e EVIDENCE_RESULTS_DIR=/results python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py retrieval c2f064f76e42e3257a21a261fe16b035d888fc7e'
```

Observed exit 0: 38 observations, including 22 HTTP outcomes and 20 persisted audit rows. Eight owner checks (four activation cases and four replay-integrity cases) are separate SQL observations and are not HTTP/audit counts. Read [`retrieval-results.json`](results/retrieval-results.json). After Terminal A Ctrl-C, clean only this project:

```sh
$COMPOSE --project-name "$PROJECT" --env-file .env --env-file .env.worktree --profile checks down
```

## R8 locked-cause focused test and source checks

This distinct source-level PostgreSQL/TestClient test is not part of the network producer and makes no TCP race claim. It verifies the actual locked cause, generic denial, zero extra per-collection content reads, content-free audit, and restored subsequent allow. Run in a fresh project after M cleanup:

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-r9-retrieval-tests --env-file .env --env-file .env.worktree --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_bok_http.py tests/test_governed_authorization.py tests/test_bok_persistence.py'
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-r9-retrieval-tests --env-file .env --env-file .env.worktree --profile checks run --build --rm python-checks
```

Then remove only this named project with the same command and `down` (without `-v`). The current locked-cause test is [test_bok_http.py lines 620–725 at M](https://github.com/creep1ng/sre-agent/blob/c2f064f76e42e3257a21a261fe16b035d888fc7e/tests/test_bok_http.py#L620-L725). The writer-run focused result was `43 passed in 17.40s`; an independent M focused rerun was `43 passed in 15.29s`. The independent F full result was `1234 passed, 1 intentional live-provider skip`; the implementation writer’s configured M full/static result was `1260 passed, 1 intentional live-provider skip`, both exit 0. No independent M full rerun is claimed. These local results do not substitute for hosted CI.

Current exact-head hosted CI: [F run 36711627164](https://github.com/creep1ng/sre-agent/actions/runs/36711627164) and [M run 36711631324](https://github.com/creep1ng/sre-agent/actions/runs/36711631324), 8/8 required jobs successful each.

The supplied PNGs are actual local Chromium screenshots of HTML rendered from the recorded JSON by `render-captures.py`, not product UI. External hostname resolution was blocked and background networking disabled during capture. Re-render from the JSON, review the displayed outputs and capture screenshots locally; do not use generated/fabricated captures. The R8 cause card is explicitly a sanitized assertion summary from the current-source TestClient test, not a serialized audit-row dump; it is separate from the 20 TCP-producer audit rows.

## Limits and interpretation

All data is synthetic. The persisted-audit projection scanned the query, credential and content values for absence. The TCP producer does not measure per-collection SQL read counts during the R8 locked transitions; those are asserted by the separate TestClient test. The probes do not establish privileged DB immutability, admin-write prevention, concurrency stress, production readiness or platform-wide authorization hardening. Green producer results and green CI are not human approval or integration acceptance.
