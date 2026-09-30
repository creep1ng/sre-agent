# Issue #332 — current-source reproduction and evidence provenance

This document describes the verified frozen F and M source heads. Copy the bundle to `./evidence-issue332` beside the source checkout's `compose.yaml`; use only the exact SHA named in each section. Prepare ignored `.env` from `.env.example` with safe local synthetic values and `.env.worktree` with the repository bootstrap. Keep provider credentials empty and live smoke disabled; never print or publish either config file.

The bundle includes `producer-probe.py`, `render-captures.py`, and `compose-proof-network.yml`. Its subnet is `10.254.239.0/28`; first verify no overlap with local routes or Docker networks. Docker must fail closed if it conflicts—do not alter global IPAM, prune unrelated resources or create a second evidence network. Run only one named project at a time. Existing Compose API and `python-checks` services only; use the existing `python-checks-db` tmpfs PostgreSQL service (no host DB port). Always run the test-DB isolation guard before migration or probe.

## Foundation F

Exact source `9fb91f725e5c292346b930e3dae787cc05fe1a71`; base main `5b6109bd2c8100455136cf12ce91c52830833c7f`.

Terminal A (leave API attached):

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r6 --env-file .env --env-file .env.worktree --profile checks build api python-checks
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r6 --env-file .env --env-file .env.worktree --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && alembic upgrade head'
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r6 --env-file .env --env-file .env.worktree --profile checks run --rm --no-deps --service-ports --use-aliases --name issue332-foundation-r6-api -e DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e OPENROUTER_API_KEY= api
```

Terminal B, while API is attached:

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r6 --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence" python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py foundation 9fb91f725e5c292346b930e3dae787cc05fe1a71'
```

Observed current result: exit 0, 12 scenarios. Four labeled committed child-row changes (chunk UPDATE, chunk DELETE, document title UPDATE, document `content_sha256` UPDATE) each preserved the parent manifest, caused exact replay to raise `BoKVersionCollision`, survived replay without silent repair, restored in `finally`, and then allowed intact replay to return `False`. Read [`foundation-results.json`](foundation-results.json); do not use historical results as current evidence.

Stop the attached API with Ctrl-C, then remove only this project (no `-v`):

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r6 --env-file .env --env-file .env.worktree --profile checks down
```

## Retrieval M

Only after F containers/network are gone, use source `34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d`, base F `9fb91f725e5c292346b930e3dae787cc05fe1a71`, and project `issue332-retrieval-r6`. Repeat the three Terminal A commands above substituting the M project name and API name `issue332-retrieval-r6-api`. Run Terminal B:

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-retrieval-r6 --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence" python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py retrieval 34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d'
```

Observed M result: exit 0, 34 scenarios; 22 HTTP outcomes and 20 persisted audit rows. Four replay-integrity SQL scenarios are separately counted owner checks, not HTTP or audit rows. Read [`retrieval-results.json`](retrieval-results.json). Stop API with Ctrl-C and run scoped `down` for `issue332-retrieval-r6`, without `-v`, before any other project.

## Current checks, hosted CI and captures

Independent local source verification: F full `1227 passed, 1 intentional live-provider skip`, exit 0; M focused `91 passed` and full `1250 passed, 1 intentional live-provider skip`, exit 0. Parent's current-head owner+HTTP spotcheck on M passed `27` in `6.60s`, exit 0. These local checks do not substitute for hosted CI.

- F exact-head hosted CI: [36673827658](https://github.com/creep1ng/sre-agent/actions/runs/36673827658), all 8 required jobs SUCCESS, watch exit 0.
- M exact-head hosted CI: [36673681362](https://github.com/creep1ng/sre-agent/actions/runs/36673681362), all 8 required jobs SUCCESS, watch exit 0.

The captured PNGs are real local Chromium headless screenshots of HTML rendered from the saved probe JSON by `render-captures.py` (Python standard library). Capture used Chromium `153.0.8010.52`, fresh profiles, `--headless --disable-gpu --disable-crash-reporter --disable-breakpad --no-first-run --disable-background-networking --disable-component-update --disable-sync --no-default-browser-check --disable-extensions --host-resolver-rules='MAP * ~NOTFOUND'`, local `file:` inputs, and no external network. The three images were reopened and visually checked for readable complete cards and sensitive content. These are evidence viewers, not product UI captures.

Observed local versions/images: Python `3.12.14` in Docker, Docker client/server `29.8.1`, Compose `5.5.1`, pinned PostgreSQL `17.4-alpine` image `sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5`; F API/checks IDs `sha256:29e3ebaa79496c3ba35e8dfc3cc3951e6e522c99ff8460d394f28ce80ed5add8` / `sha256:07a801296c34c978d14caa5dbfd1488bfd27bcc181b7213cd91a6b23c30c4105`; M API/checks IDs `sha256:72ab869a14e2114842d616e5b6094c148cd61ac9ce3e15515f45d039e53fd4ae` / `sha256:9df31fdea359faa96c17362936d97943cc234596c925e19621ffd87de75c7bc0`.

The API foreground handles ended with intentional Ctrl-C exit 130 after successful probes; each scoped cleanup exited 0. Both project container lists and their named network lists were empty afterward. The Compose-created project-named `postgres_data` volume metadata was left untouched (`down` deliberately omitted `-v`); the test DB itself was tmpfs. No unrelated resource/global daemon change was made.

## Acceptance boundary

All reported data is synthetic. API keys exist only in probe memory and are checked absent from JSON. The probe's persisted audit metadata scan found no request query, fragments or credentials. SQL child drift checks are separate from API SQL-read instrumentation, which is tested by source TestClient SQL observer assertions. No provider/paid, Jev, cloud, OTel, SSH, production-load, concurrent-writer or privileged-DB-write-hardening claim is made. CI success and green producer evidence are not human approval or integration acceptance. PRs remain draft, the #382 bot review thread remains unresolved, and issue #332 stays open.
