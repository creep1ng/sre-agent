# Repeat the controlled producer evidence

Use only an isolated local checkout of the full tested source SHA named in each report.
Place this reviewed evidence bundle in `./evidence-issue332` alongside that checkout's Compose
file. Prepare ignored `.env` from the example with synthetic non-production values; keep
provider credentials empty and live smoke disabled. Use the repository's safe worktree bootstrap
to create `.env.worktree` and verify free loopback ports. Never print/source/attach either file.
The host supplies Git, Docker, safe configuration and an ordinary browser; no host package tools.

These are portable equivalents of the observed commands: only the transient local evidence
mount path is replaced with `./evidence-issue332`. Use the exact source SHA for the selected unit.
`api` is the existing runtime stage; `python-checks` is the existing checks stage. No source bind
mount or persistent demo database is used. Run only one proof project at a time.

## Foundation: source `1b70672629d0c65b393fc6d31022f6a04207b615`

Terminal A: build, migrate, then keep the API attached in the foreground:

```sh
docker compose --project-name issue332-foundation-proof --env-file .env --env-file .env.worktree --profile checks build api python-checks
docker compose --project-name issue332-foundation-proof --env-file .env --env-file .env.worktree --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && alembic upgrade head'
docker compose --project-name issue332-foundation-proof --env-file .env --env-file .env.worktree --profile checks run --rm --no-deps --service-ports --use-aliases --name issue332-foundation-api -e DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e OPENROUTER_API_KEY= api
```

Terminal B, from the same checkout while that API remains attached:

```sh
docker compose --project-name issue332-foundation-proof --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence" python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py foundation 1b70672629d0c65b393fc6d31022f6a04207b615'
```

Expected: `foundation-results.json`, all probe assertions passed; 8 observations.
The script generates synthetic keys in memory, never serializes them, and runs reversible faults
only against the owned tmpfs database. A failed fresh-seed assertion is not permission to reuse
another database. Stop and inspect it; do not work around the guard.

When finished, remove **only this named disposable proof project**, without `-v`:

```sh
docker compose --project-name issue332-foundation-proof --env-file .env --env-file .env.worktree --profile checks down
```

## Retrieval: source `c37c3403c374350be676a56e9989132fdc200c8d`

Terminal A: build, migrate, then keep the API attached in the foreground:

```sh
docker compose --project-name issue332-retrieval-proof --env-file .env --env-file .env.worktree --profile checks build api python-checks
docker compose --project-name issue332-retrieval-proof --env-file .env --env-file .env.worktree --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && alembic upgrade head'
docker compose --project-name issue332-retrieval-proof --env-file .env --env-file .env.worktree --profile checks run --rm --no-deps --service-ports --use-aliases --name issue332-retrieval-api -e DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e OPENROUTER_API_KEY= api
```

Terminal B, from the same checkout while that API remains attached:

```sh
docker compose --project-name issue332-retrieval-proof --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence" python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py retrieval c37c3403c374350be676a56e9989132fdc200c8d'
```

Expected: `retrieval-results.json`, all probe assertions passed; 30 observations.
The script generates synthetic keys in memory, never serializes them, and runs reversible faults
only against the owned tmpfs database. A failed fresh-seed assertion is not permission to reuse
another database. Stop and inspect it; do not work around the guard.

When finished, remove **only this named disposable proof project**, without `-v`:

```sh
docker compose --project-name issue332-retrieval-proof --env-file .env --env-file .env.worktree --profile checks down
```

## Checks and capture provenance

The exact default checks command remains `docker compose --env-file .env --profile checks run
--build --rm python-checks`. Any overridden test command must explicitly prepend
`python scripts/assert_test_database_isolated.py`.

PNG files are actual Chromium headless screenshots of the included HTML evidence views, rendered
from successful real probe JSON, not generated images or a simulated product UI. Rendering uses
`render-captures.py` (Python standard library only). The recorded browser invocation used
`--headless --disable-gpu --no-first-run --disable-background-networking --disable-component-update
--disable-sync --no-default-browser-check --disable-extensions --host-resolver-rules='MAP * ~NOTFOUND'`,
a fresh local profile, and a local HTML input. Capture sizes: foundation1600×1500,
retrieval1600×1650 and retrieval audit1600×1400. Existing host Chromium was explicitly authorized
for capture; it did not execute application/package tooling. Reopen the HTML in a browser to
inspect the exact rendered data; producer/test reproduction remains containerized above.
