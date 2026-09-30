# Issue #332 — R11 evidence reproduction

**Frozen candidates:** F `e2b83d45f285c46a5a83c0234846dbfd122934df` (tree `ec2cd216…`, base main `2779b0b9…`); M `7438b5a87dbf389fd1a936c899281520c1300295` (tree `572782bb…`, base F `e2b83d45`). Delivered main `2779b0b9af4476c1e1a0c0b99ab2379c8326a86e` (usage contract 2.5 plus grants-client seam). R11 script SHA-256 `6e2fc653d500e5dfc9d237cf1f6702b0d02d47c5d5c07c7df3ff704c2304f316`; renderer `893c784f8418420196a6ea6707293fef17040904d51e366c746cfff5b9931f7c`; overlay `ead2cca2bcc4785f113c5ba1faaad1964f26260af520a19fd577ef086d76dddc`, subnet `10.254.239.0/28`.

The bundle is portable beside each source checkout's `compose.yaml`; copy it as `./evidence-issue332` with writable `results/`. Prepare safe ignored `.env`/`.env.worktree` with synthetic non-production settings, blank provider keys, live-provider smoke disabled. Do not print/source/attach configs. Probe creates API keys in memory and never serializes them. Confirm overlay subnet unused; fail closed on overlap. Use only existing Compose services and checks-profile PostgreSQL tmpfs DB with no host port. Run F then M sequentially, never concurrently. Stop API with `docker stop`, then scoped `down` without `-v`. No global prune, providers, Jev, cloud, OTel, SSH, production, or foreign inspection.

## Foundation F (ran first, 18/18 passed)

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r11 --env-file .env --env-file .env.worktree --profile checks build api python-checks
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r11 --env-file .env --env-file .env.worktree --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && alembic upgrade head'
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r11 --env-file .env --env-file .env.worktree --profile checks run --rm --no-deps --service-ports --use-aliases --name issue332-foundation-r11-api -e DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e TEST_DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e OPENROUTER_API_KEY= api
```

With API attached, in a second terminal:

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-foundation-r11 --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence:ro" --volume "$PWD/evidence-issue332/results:/results" -e EVIDENCE_RESULTS_DIR=/results python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py foundation e2b83d45f285c46a5a83c0234846dbfd122934df'
```

Observed: `{"mode":"foundation","source_sha":"e2b83d45…","scenarios":18,"outcome":"all assertions passed"}`, exit 0. `docker stop issue332-foundation-r11-api`; scoped `down` (no `-v`); owned labels empty; network removed. Results copied to private `results/foundation-results.json` (5,443 bytes).

## Retrieval M (after verified F cleanup, 40/40 passed, 22 HTTP, 20 audit)

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-retrieval-r11 --env-file .env --env-file .env.worktree --profile checks build api python-checks
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-retrieval-r11 --env-file .env --env-file .env.worktree --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && alembic upgrade head'
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-retrieval-r11 --env-file .env --env-file .env.worktree --profile checks run --rm --no-deps --service-ports --use-aliases --name issue332-retrieval-r11-api -e DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e TEST_DATABASE_URL=postgresql://python_checks@python-checks-db:5432/python_checks -e OPENROUTER_API_KEY= api
```

```sh
docker compose -f compose.yaml -f ./evidence-issue332/compose-proof-network.yml --project-name issue332-retrieval-r11 --env-file .env --env-file .env.worktree --profile checks run --rm --user "$(id -u):$(id -g)" --volume "$PWD/evidence-issue332:/evidence:ro" --volume "$PWD/evidence-issue332/results:/results" -e EVIDENCE_RESULTS_DIR=/results python-checks sh -c 'python scripts/assert_test_database_isolated.py && python /evidence/producer-probe.py retrieval 7438b5a87dbf389fd1a936c899281520c1300295'
```

Observed: `{"mode":"retrieval","source_sha":"7438b5a…","scenarios":40,"outcome":"all assertions passed"}`, exit 0. `docker stop`; scoped `down` (no `-v`); owned labels empty.

## Non-TCP source-test proof

R8 locked cause: `pytest -q tests/test_bok_http.py tests/test_governed_authorization.py tests/test_bok_persistence.py` on exact M head via overlay project `issue332-r11-r8check` observed `44 passed in 16.47s`, exit 0; scoped down without `-v`. Summary bound in `r8-denial-cause.json` (`tests/test_bok_http.py` lines 627–727), distinct from TCP audit rows. Owner timestamp probes are SQL observations inside the producer JSON, not HTTP/audit counts.

## Captures

Rendered `foundation-capture.html`, `retrieval-capture.html`, `retrieval-audit-capture.html` via `render-captures.py` (renderer refuses pending R8). Screenshotted with real local Chromium 153.0.8010.52, fresh profiles, `--disable-background-networking`, `--host-resolver-rules="MAP * ~NOTFOUND"`, `--no-sandbox`: 1600×1500 `foundation.png` (217,709 bytes), 1600×1650 `retrieval.png` (275,713 bytes), 1600×1400 `retrieval-audit.png` (227,917 bytes). Visually inspected and privacy audited; synthetic corpus only.

Configured full/static, schema harness, exact-head hosted CI (F 36722870580, M 36722880991, both 8/8 SUCCESS), image/lock provenance, and review inventory are bound in reports/provenance/ledger/manifest. No R9/R10 output reused as R11 proof. Video deferred: `Deferred: media storage unavailable; screenshot evidence is mandatory.`
