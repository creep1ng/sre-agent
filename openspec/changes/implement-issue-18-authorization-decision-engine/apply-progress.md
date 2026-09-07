# Apply Progress: Reusable Authorization Decision Engine

## Completed
- [x] 1.1 Authorization engine RED tests
- [x] 2.1 Engine, facts, and deterministic precedence
- [x] 1.2 Audit/DTO/projection/migration RED tests
- [x] 2.3 Audit-only cause DTO, model, projection, gateway plumbing, and migration
- [x] 2.4 Immutable 1.3.0 audit contract, fixtures, compatibility, evidence, and manifest
- [x] 1.3 Responses integration RED tests
- [x] 2.2 Repository fact ports and decision-authority removal
- [x] 3.1 Responses engine integration and audit-only cause projection
- [x] 4.1 Final routing, append, release, and harness verification

## Deferred
- [x] 2.2 completed in PR 4 after `ResponsesService` migrated to the engine.

## TDD Cycle Evidence
| Task | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|
| 1.1/2.1 | N/A: prior PR 2 work | `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev pytest tests/test_authorization.py -q`: collection failed (`ModuleNotFoundError`) | Same command: 16 passed | Engine table covers all precedence branches | `uv run pytest tests/test_authorization.py -q`: 16 passed; Ruff exit 0 |
| 1.2 | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q`: 247 passed | Same command after test-first changes: 8 failed, 250 passed (missing DTO field, projector parameter, 1.3 fixture, and migration column/constraint) | Same command: 338 passed | Four closed causes, invalid value, non-deny/stage misuse, legacy null, valid constrained row, invalid row, and 1.3 fixture | Reformatted changed tests; focused suite remained 338 passed |
| 2.3 | Same 247-pass baseline | Migration triangulation test: 1 failed (`authorization_denial_cause` metadata absent) | Focused migration suite: 6 passed; focused complete suite: 338 passed | Valid authorization deny round-trip and invalid routing-stage row prove the database constraint | Rolled back the test-only insert transaction to preserve later append-only count tests |
| 2.4 | Contract release did not exist | Focused RED included missing `schemas/releases/1.3.0/...audit.responses.denied...` fixture | `node schemas/tooling/release.mjs evidence --release 1.3.0` and `validate --release 1.3.0`: 143 artifacts, 8 checks | Positive audit fixture has `grant_not_applicable`; negative fixture rejects an unclosed cause; 1.2 positive fixtures validate through additive compatibility | Restored existing compact JSON-schema layout after a formatting-only expansion; regenerated immutable evidence and manifest |
| 1.3/2.2/3.1 | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_responses.py tests/test_persistence_repositories.py -q`: 16 passed | Same command: 4 failed (missing exact audit causes, repository fact type, and `GrantRepository.decide()` removal) | Same command: 16 passed | Grant-not-applicable and resource-missing preserve uniform 403/API secrecy while retaining separate audit causes; assignment resolution spy raises on deny | Replaced the repository-specific view with the engine fact type and removed the duplicate decision authority; focused Responses/repository/engine suite: 33 passed |
| 4.1 | Focused GREEN: 33 passed | N/A: verification/refactor task | Full isolated suite: 426 passed, 1 skipped | Issue-14 harness covers 12 Responses cases, including denied provider/assignment isolation | Ruff check/format passed; no application-root change was needed because the engine is composed with per-request SQLAlchemy fact readers inside `ResponsesService` |

## Work Unit Evidence
| Evidence | Result |
|---|---|
| Focused tests | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q` exit 0: 338 passed in 0.49s. |
| Relevant lint | `uv run ruff check src/sre_agent/governance/dto.py src/sre_agent/persistence/models.py src/sre_agent/gateway/audit.py migrations/versions/20260901_03_add_authorization_denial_cause.py tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py` exit 0. |
| Immutable release | `node schemas/tooling/release.mjs evidence --release 1.3.0` and `node schemas/tooling/release.mjs validate --release 1.3.0` exit 0: 143 artifacts and 8 checks; `npm --prefix schemas/tooling test` exit 0. |
| Runtime harness | `scripts/worktree-compose --profile checks run --build --rm python-checks sh -c 'shellcheck docker/harness-entrypoint.sh scripts/worktree-compose && ruff check --no-cache src/sre_agent/governance/dto.py src/sre_agent/persistence/models.py src/sre_agent/gateway/audit.py migrations/versions/20260901_03_add_authorization_denial_cause.py tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py && ruff format --check --no-cache src/sre_agent/governance/dto.py src/sre_agent/persistence/models.py src/sre_agent/gateway/audit.py migrations/versions/20260901_03_add_authorization_denial_cause.py tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py && uv lock --check --no-cache && pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q && alembic check'` exit 0: shellcheck, Ruff, formatting, and lock checks passed; 339 passed in 0.57s; `No new upgrade operations detected.` The unmodified default command remains known to fail 8 unrelated `test_security_catalogs.py` tests because `docker/api.Dockerfile` does not copy `docs/security/**`. |
| Rollback boundary | Revert audit DTO/model/projector changes, `20260901_03_add_authorization_denial_cause.py`, the complete immutable `schemas/releases/1.3.0/**` release, release-tooling version maps/tests, audit tests, `tasks.md`, and this progress file. Leave PR 2 engine code and deferred PR 4 Responses/repository work intact. |
| PR4 focused tests | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_responses.py tests/test_persistence_repositories.py tests/test_authorization.py -q` exit 0: 33 passed in 1.15s. |
| PR4 runtime harness | `scripts/worktree-compose --profile issue-14 run --rm issue-14-harness` exit 0: 12 passed, 1 warning; deny assignment spy and provider recording prove zero routing/provider access. |
| PR4 release and suite | `node schemas/tooling/release.mjs validate --release 1.3.0` exit 0: 145 artifacts, 8 checks; `npm --prefix schemas/tooling test` exit 0: 71 passed; `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest -q` exit 0: 426 passed, 1 skipped. |
| PR4 rollback boundary | Revert engine use in `gateway/responses.py`, fact-only `persistence/repositories.py`, and PR4 tests/docs; restore the former repository decision only with the old Responses composition. |

## Scope and Size Exception

The maintainer explicitly approved `size:exception` for work unit `pr3-audit-size-exception`. The immutable release snapshot is complete and deliberately not compressed or partially omitted. PR 3 does not modify Responses composition or remove/narrow repository decisions.

## Phase-Contract Correction Evidence

| Field | Evidence |
|---|---|
| Native attempt | `sha256:b243930ce853d13dc28c32b2ae354a683e003f71b83b4593fa32bbf1f5612567`; work unit `pr3-phase-contract-correction`; bounded to the missing-cause contract and exact runtime-harness receipt. |
| Safety net | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q` exit 0: 338 passed in 0.51s. |
| RED | `node --test schemas/tooling/test/schema-validation.test.mjs` exit 1: `release 1.3.0 requires an audit cause for every authorization deny` failed with `true !== false` after removing the cause. The compatibility test then correctly rejected the historical 1.2 authorization-deny fixture, and the Python DTO suite correctly exposed the schema-only negative fixture as readable historical data. |
| GREEN | The 1.3 audit schema requires `authorization_denial_cause` for `authorization` + `denied` + 403, with a required-rule negative fixture. `node --test schemas/tooling/test/schema-validation.test.mjs` exit 0: 32 passed; `node --test schemas/tooling/test/release-validation.test.mjs` exit 0: 11 passed; focused PostgreSQL suite exit 0: 339 passed in 0.57s. |
| Historical readback | The DTO retains nullable causes for persisted 1.2 rows; the release compatibility receipt deliberately excludes only the historical 1.2 audit deny fixture and example from new-writer validation, reporting 80 compatible fixtures and 9 examples. |
| Immutable release | `node schemas/tooling/release.mjs projection --release 1.3.0 && node schemas/tooling/release.mjs evidence --release 1.3.0 && node schemas/tooling/release.mjs validate --release 1.3.0` exit 0: 144 artifacts, 8 checks. `npm --prefix schemas/tooling test` exit 0: 71 passed. |

## Exact-Cause-Null Correction Evidence

| Field | Evidence |
|---|---|
| Native attempt | `sha256:309d52daebd672425899a9e24bbfdd8d676f039cfa613168998da8d39a7dac38`; work unit `pr3-exact-cause-null-correction`; bounded to reject a null cause on new 1.3 authorization-deny 403 events. |
| RED | `node --test schemas/tooling/test/schema-validation.test.mjs` exit 1: `release 1.3.0 requires a non-null audit cause for every authorization deny` failed with `true !== false` after setting the cause to `null`. |
| GREEN | The 1.3 conditional now requires the field and constrains it to the four closed non-null values; `audit.authorization-denial-cause-null.negative.v1.3.0.fixture.json` verifies the null rejection. `node --test schemas/tooling/test/schema-validation.test.mjs` exit 0: 32 passed. |
| Release/tooling | `node schemas/tooling/release.mjs projection --release 1.3.0 && node schemas/tooling/release.mjs evidence --release 1.3.0 && node schemas/tooling/release.mjs validate --release 1.3.0` exit 0: 145 artifacts, 8 checks. `npm --prefix schemas/tooling test` exit 0: 71 passed. |
| Focused PostgreSQL | `scripts/bootstrap-worktree.py && scripts/worktree-compose up -d --wait db && TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q` exit 0: 339 passed in 0.52s. |
| Historical readback | DTO readback remains nullable for persisted historical rows. The new negative fixtures are schema-only 1.3 writer-contract evidence and are explicitly excluded from the version-agnostic DTO negative-fixture matrix. |

## Verify Remediation: Inactive Principal and Resource Short-Circuiting

| Field | Evidence |
|---|---|
| Native attempt | `sha256:1919c43a4f00436b5233df4e1402573f5c74072e3d0f2bbf3a8a64208e2c6c68`; work unit `verify-remediation-inactive-principal`; remediates failed evidence `sha256:e821a8657106e7e3f5444cd521339ed781345826d5ec0664ffda0f92f4f70118`. |
| Safety net | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_responses.py tests/test_authentication.py tests/test_persistence_repositories.py -q` exit 0: 27 passed in 1.44s. |
| RED | After adding Responses and credential-boundary tests, `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_responses.py tests/test_authentication.py -q` exit 1: 2 failed, 23 passed. The inactive Principal returned 401 before the engine and `CredentialRepository.resolve_authorization_context` did not exist. |
| GREEN | `CredentialRepository.resolve_authorization_context()` reuses the existing credential prefix, active-status, expiry, and hash checks while retaining Principal status. `authenticate()` delegates and still rejects inactive Principals. Responses calls the explicit authorization-context boundary. The same focused command exit 0: 25 passed in 1.89s. |
| Triangulation | Revoked, expired, and same-prefix wrong-hash credentials remain rejected by the new boundary; inactive Principal and inactive resource each return the uniform 403, persist their exact audit-only causes, and prove zero later reads. Focused Responses/authentication command exit 0: 28 passed in 1.53s. |
| Refactor | Ruff formatted the new credential-boundary test; `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_responses.py tests/test_authentication.py tests/test_persistence_repositories.py tests/test_authorization.py -q` exit 0: 49 passed in 1.65s. |
| Full suite | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` exit 0: 432 passed, 1 skipped in 2.58s. |
| Lint | `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/sre_agent/gateway/responses.py src/sre_agent/persistence/repositories.py tests/test_responses.py tests/test_authentication.py` and `ruff format --check` exit 0; `git diff --check` exit 0. |
| Release and runtime harness | `node schemas/tooling/release.mjs validate --release 1.3.0` exit 0: 145 artifacts, 8 checks; `npm --prefix schemas/tooling test` exit 0: 71 passed; `scripts/worktree-compose --profile issue-14 run --rm issue-14-harness` exit 0. The immutable release tool correctly rejects regeneration via `projection` after publication. |
| Rollback boundary | Revert the Responses credential-boundary call, the delegated repository resolver, the inactive-principal/resource tests, and this remediation record. Keep generic `authenticate()` and all existing 401 authentication behavior unchanged. `verify-report.md` remains excluded prior evidence. |
