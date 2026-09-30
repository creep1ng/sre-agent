# Policy-read evidence — issue #334

This slice exposes only protected `GET /v1/consumption-limits` and its singleton
policy. CA1 is partial; writes, admission, reservations and settlement are not
implemented here. CA2–CA8 remain pending. Delivery route: direct recovery/rebase.

## Reproduce locally

Prepare an untracked `.env` from `.env.example` with distinct synthetic keys,
synthetic routing values, an audit HMAC key, no provider credential and live smoke
disabled. Generate `.env.worktree` with `scripts/bootstrap-worktree.py`; keep its
unique Compose project. Never reuse a shared database. Run from the repository:

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_control_acceptance.py -k consumption_policy'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
```

The focused acceptance tests execute FastAPI requests and PostgreSQL readback.
Expect anonymous 401, restricted 403, administrator 200; a default row with
`policy_id=1`, `version=0` and both limits null; and readback of
`incident_token_limit=2147483648` after the test's explicit database update.
That update is a test fixture, not a supported policy-write API.

The full runner additionally checks isolation, ShellCheck, Ruff lint/format,
the locked dependency graph, five import boundaries, scoped mypy and Alembic.
A live-provider smoke skip is expected with the explicit opt-in disabled.

## Actual capture and provenance

Evidence kind: **controlled integration**. The [screenshot](issue-334-policy-read.png)
is an unmodified Playwright capture of the candidate's real Uvicorn/FastAPI
response over Docker networking, not Swagger or a generated response.
Chromium 153.0.8010.12 observed 401/403/200 with synthetic principals.
Only the administrator policy navigation received its Authorization header.
PostgreSQL returned one unset singleton at version 0, migration `20260929_15`;
token/version columns were BIGINT and monthly USD was NUMERIC(32,12).

Capture runtime source was rebased onto
`5b6109bd2c8100455136cf12ce91c52830833c7f`; subsequent fixture cleanup does not
change the API. The PR records the exact final tested commit, image IDs and
command results. Images use the digests in `docker/api.Dockerfile`,
`docker/e2e.Dockerfile` and `compose.yaml`; Python uses `uv.lock`, the contract
harness uses `schemas/tooling/package-lock.json`, and Playwright uses
`package-lock.json`. Builds are not evidence of hosted CI or human acceptance.

## Recovery finding and boundaries

After rebase, the existing human-command and run-start database fixtures left
the new policy table behind while resetting Alembic. The observed full-run RED
was 1209 passed, one skipped, 13 DuplicateTable setup errors. Adding the missing
table to those two cleanup lists preserved every existing assertion; the
focused repair run passed 41 tests. No new regression test was needed.

Rollback this policy-read unit and migration together; no released schema
snapshot or #333 usage behavior changed. Later PR publication remains sequential
to main; safe local descendant recovery may proceed before integration.
Sanitized: yes. No provider request, live credential, prompt or completion was
used. Deferred: media storage unavailable; screenshot evidence is mandatory.
