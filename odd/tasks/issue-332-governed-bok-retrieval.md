# Issue #332: Governed BoK retrieval

## Objective

Provide two versioned demo BoK collections with deterministic lexical search and direct chunk reads, while enforcing exact collection-version authorization before content access. Keep Jev an optional, post-authorization experiment.

## Problem and why

The resource catalog defines `bok_collection` and `bok.search`/`bok.read`, but there is no BoK-owned corpus, readiness state, or retrieval surface. Catalog state alone is not proof that a collection version is indexed. The #34 consumer needs authorized results with provenance and no fixture fallback.

## Authorized scope and constraints

- The implementation phase was local-only. Subsequent explicit authorization permits the current authenticated `gh` session to inspect the issue's GitHub Project and publish branches/PRs in `creep1ng/sre-agent`; it does not authorize merge, issue closure, other destinations/credentials, or live TypeSafe calls.
- PostgreSQL 17 full-text search is the lexical baseline. The exact `collection_id@version` grant and authoritative BoK readiness must be checked before any content query.
- Topics/tags may classify or narrow already-authorized content, never grant access.
- No cross-identity content cache. Direct IDs cannot bypass collection authorization. Distinguish empty results, denial, unavailable index, and storage errors without enumerating restricted resources.
- Jev may evaluate/reorder only authorized candidates, opt-in and failure-isolated; use synthetic data for tests and document privacy/cost/latency limitations.
- Preserve existing interfaces and tests. Prefer real PostgreSQL-backed HTTP acceptance tests, not mocked-only or tautological tests. Technical artifacts are in English.
- Effective TDD: **enabled**, from session `strict-tdd-mode` and current `AGENTS.md` test-first rule. RED → GREEN → REFACTOR is required. Runner: `docker compose --profile checks run --build --rm python-checks pytest -q <focused-test-path>` using the disposable checks database and a safe local `.env` prepared from `.env.example`.
- Roughly 400 authored changed lines per task is advisory only; keep coherent behavior/tests together.

## Tasks

- [x] **BOK-1 — Owner corpus and version lifecycle.** Add BoK-owned collection-version, document, and section-chunk persistence with migration; immutable same-version replay, collision rejection, ready-only activation, and two deterministic demo collections. Prove with PostgreSQL-backed acceptance tests written before implementation. Check: focused BoK corpus test and migration test; record observed RED/GREEN.
- [x] **BOK-2 — Governed lexical retrieval.** Add bounded deterministic PostgreSQL FTS search and direct reads with complete collection/document/version/section provenance. Check exact grants and BoK readiness before content repository calls; no content read on denied requests; metadata-only audit and content-read counters. Prove authorized, denied, unready, no-match, direct-ID, revocation, and storage/index-failure distinctions through real DB + HTTP tests written first. Check: focused BoK HTTP tests and relevant existing governance tests; record observed RED/GREEN.
- [x] **BOK-3 — Optional Jev experiment.** Add a default-off, separately configured Jev shadow-evaluation boundary that receives only authorized synthetic chunks and never changes lexical results or authorization. Live HTTP is implemented against a pinned model but was tested only with `httpx.MockTransport`; no live Jev request was made. Check: tests prove no evaluator calls on denial, unready, no-match, direct-read, or non-synthetic retrieval and lexical fallback on evaluator failure.
- [x] **BOK-4 — Integration evidence.** Run focused checks, full applicable Python suite, migration replay, and static checks in containers; document actual results, limitations, reproducible commands, and issue #332 criterion mapping. Do not claim hosted CI or live Jev evidence. Parent spot-checks at least one command.

## Acceptance criteria

1. Re-ingesting an identical collection version is idempotent; conflicting bytes for that version fail; unready versions never search.
2. At least two demo collections can be searched only with exact version grants; restricted collections contribute no content, titles, or counts.
3. Search order is deterministic for a fixed corpus/query; results include provenance. Direct chunk reads enforce the same boundary.
4. No-match is distinguishable from denial and index/storage failure. A revoked/deactivated collection cannot be delivered by new requests after state commit.
5. Metadata-only audit and content-read instrumentation permit proving zero restricted content reads on denial; no query or chunk text is logged.
6. Jev is opt-in after authorization, uses only permitted candidates, and cannot become an access-control dependency.

## Progress and evidence

- BOK-1 completed with a real PostgreSQL owner schema, immutable version replay/collision handling, ready-gated activation, a `--seed-bok` bootstrap for two synthetic collections, and migration table/FK coverage. Catalog rows use `collection_id@version`; owner readiness remains independently authoritative.
- TDD evidence: RED — `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_bok_persistence.py` failed during collection with `ModuleNotFoundError: No module named 'sre_agent.bok'` before owner implementation. GREEN/REFACTOR — `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_bok_persistence.py tests/test_migrations.py` → `17 passed`; focused `ruff check --no-cache` across BOK-1 source, migration, and tests → `All checks passed!`.
- The test database was the disposable `python-checks-db`; `.env` was created locally from `.env.example` with dummy-only values and is ignored by Git. No live TypeSafe calls, GitHub operations, or schema release artifacts were touched.
- BOK-2 TDD evidence: RED — the new real-PostgreSQL HTTP acceptance suite initially had `5 failed` because both BoK endpoints were absent. GREEN/REFACTOR — `docker compose --profile checks run --build --rm python-checks .venv/bin/pytest -q tests/test_bok_http.py tests/test_migrations.py tests/test_governed_authorization.py` → `27 passed in 22.75s`; focused `.venv/bin/ruff check --no-cache` over changed BoK, audit, migration, and governance files → `All checks passed!`.
- BOK-2 covers deterministic English PostgreSQL FTS with ID tie-break, complete provenance, direct reads, exact `collection_id@version` grants, owner readiness, grant/status revocation, no content query after denial/unready checks, storage-failure distinction, and metadata-only audit. Tests assert request/query/chunk text is absent from audit; no-match returns an empty result distinct from 403/503.
- The test database was the disposable `python-checks-db`; `.env` was created locally from `.env.example` with dummy-only values and is ignored by Git. No live TypeSafe calls, GitHub operations, or schema release artifacts were touched.
- BOK-3 TDD evidence: RED — `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_bok_http.py -k 'jev or typesafe_key'` → `1 failed, 3 errors` because `Settings.bok_jev_enabled` and the application evaluator injection were not yet implemented. GREEN/REFACTOR — the same command after implementation → `4 passed, 5 deselected`; then `docker compose --profile checks run --build --rm python-checks .venv/bin/pytest -q tests/test_bok_http.py tests/test_bok_persistence.py tests/test_migrations.py tests/test_governed_authorization.py` → `35 passed in 43.54s`.
- BOK-3 has a synthetic evaluator seam and a dependency-free `httpx` adapter pinned to `jev-1.13.0`. It runs only when `BOK_JEV_ENABLED=true` and the request explicitly uses `evaluation_mode=shadow`; providing a key alone does not enable it. It is shadow-only: lexical order and content are returned unchanged even on success, and all errors degrade to content-free metadata. Adapter tests use a mock transport; no live TypeSafe call was made. The provider request contains query/passage text, so deployment must account for TypeSafe's stated data handling; the docs note that zero-data-retention is Enterprise-only, plus cost, latency, and model limitations.
- A focused Ruff invocation initially found an import-block formatting issue in `src/sre_agent/bok/retrieval.py`; an automated fix attempt encountered container `E902 Permission denied`, so the missing blank line was corrected manually. Final focused Ruff command over the BOK, application/settings, migration, and relevant tests → `All checks passed!`.
- The test database was the disposable `python-checks-db`; `.env` was created locally from `.env.example` with dummy-only values and is ignored by Git. No live TypeSafe calls, GitHub operations, or schema release artifacts were touched.
- BOK-4 correction evidence: an independent full-suite run initially had `1161 passed, 1 skipped, 2 failed` from stale Alembic-head assertions. Ruff requested formatting in eight files; `alembic check` found ORM/migration drift in FK names/cascade, chunk `TEXT`, and the English GIN FTS index. These concrete issues were corrected before final verification.
- Regression RED observed before the Jev usage fix: `docker compose --profile checks run --build --rm python-checks .venv/bin/pytest -q tests/test_bok_http.py::test_typesafe_adapter_rejects_boolean_token_usage` failed because `True` was accepted as an integer token count. The adapter now requires exact `int` types for usage counters. ORM metadata now mirrors the migration's FK names and `CASCADE`, `TEXT`, and English GIN FTS index; readiness now requires revision `20260924_15`, and migration-version expectations were updated. These changes await post-normalization verification.
- The writer's copied-file formatter and subsequent Docker socket attempt were unavailable in its runtime. The parent normalized the eight files with a UID-matched bind-mounted Ruff container; `git diff --check` passed. This was completed before the final checks.
- Final migration replay and model-drift check in a separate disposable Compose project: `docker compose --project-name issue332-schema --profile checks run --build --rm python-checks sh -c '.venv/bin/alembic upgrade head && .venv/bin/alembic check'` exited 0 with `No new upgrade operations detected.` The project was removed and recreated for the suite.
- Final CI-style Python static checks on that resulting checks image exited 0: isolated-database assertion, ShellCheck, `ruff check --no-cache .`, `ruff format --check --no-cache .` (`158 files already formatted`), lock check, import-linter (`5 kept, 0 broken`), configured mypy (`11 source files`), and the five repository validators.
- Final full Python suite on the isolated checks project: `docker compose --project-name issue332-schema --profile checks run --rm python-checks .venv/bin/pytest -q` exited 0 with `1164 passed, 1 skipped in 225.94s`. The ordinary live-provider smoke is skipped without explicit external configuration. No hosted CI, live Jev request, or network-level API-process result is claimed; the HTTP acceptance tests use FastAPI TestClient against real PostgreSQL.
- Delivery progress: the first stacked-to-main slice is draft PR [#382](https://github.com/creep1ng/sre-agent/pull/382), commit `ed394a6185517c6ea0310fec214adeac07ddc676`, with BOK-1 only. Its 532 changed lines have an explicit maintainer-approved PR1 size exception. Independent local spot check: `17 passed`; writer's isolated branch suite: `1151 passed, 1 skipped`, plus Alembic and Ruff checks. The PR is draft because a real HTTPS screenshot remains missing; `pr-governance` fails pending evidence, and hosted functional CI was still running at the last check. The full BOK-2/BOK-3 candidate remains uncommitted in this worktree.

## Criterion-to-evidence map

1. Immutable replay, collision, and readiness: `tests/test_bok_persistence.py` and the migration replay/check.
2. Exact-version access and restricted-content isolation: `tests/test_bok_http.py::test_denied_search_and_direct_id_read_do_not_read_or_enumerate`, including the ungranted version-2 request.
3. Stable lexical order and provenance, including direct read: `test_authorized_search_has_versioned_provenance_and_stable_order` and `test_no_match_unready_and_authorized_chunk_read_are_distinct` in `tests/test_bok_http.py`.
4. Distinct no-match, denial, unavailable index/storage, and revocation: `test_no_match_unready_and_authorized_chunk_read_are_distinct`, `test_revoked_owner_version_is_not_delivered_and_audit_has_no_content`, and `test_postgresql_content_storage_failure_is_not_a_no_match`.
5. Metadata-only audit and zero restricted content reads: `test_denied_search_and_direct_id_read_do_not_read_or_enumerate` and `test_revoked_owner_version_is_not_delivered_and_audit_has_no_content`.
6. Optional authorized Jev shadow/fallback: the Jev cases in `tests/test_bok_http.py`, including mock HTTP contract, no evaluator on denied/unready/no-match/direct-read paths, synthetic-source gate, and failure fallback. No live model-quality claim is made.

## Delivery boundary

The full implementation remains local and uncommitted in this worktree. PR #382 publishes only the BOK-1 owner-corpus slice; it must gain a genuine sanitized screenshot and independent human review before acceptance. After PR1 merges to `main`, prepare the governed retrieval PR as a clean stacked-to-main diff; Jev remains a later optional slice. Each later PR requires its own tested SHA, containerized reproduction, screenshot, human review, and cohesive size boundary or separate explicit maintainer exception. No live synthetic-data Jev experiment has been authorized.
