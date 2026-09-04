# Apply Progress: Reusable Authorization Decision Engine

## Completed
- [x] 1.1 Authorization engine RED tests
- [x] 2.1 Engine, facts, and deterministic precedence
- [x] 1.2 Audit/DTO/projection/migration RED tests
- [x] 2.3 Audit-only cause DTO, model, projection, gateway plumbing, and migration
- [x] 2.4 Immutable 1.3.0 audit contract, fixtures, compatibility, evidence, and manifest

## Deferred
- [ ] 2.2 is not implemented in PR 2 or PR 3. PR 4 will add persistence fact ports and remove/narrow `GrantRepository.decide()` after `ResponsesService` migrates.

## TDD Cycle Evidence
| Task | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|
| 1.1/2.1 | N/A: prior PR 2 work | `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev pytest tests/test_authorization.py -q`: collection failed (`ModuleNotFoundError`) | Same command: 16 passed | Engine table covers all precedence branches | `uv run pytest tests/test_authorization.py -q`: 16 passed; Ruff exit 0 |
| 1.2 | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q`: 247 passed | Same command after test-first changes: 8 failed, 250 passed (missing DTO field, projector parameter, 1.3 fixture, and migration column/constraint) | Same command: 338 passed | Four closed causes, invalid value, non-deny/stage misuse, legacy null, valid constrained row, invalid row, and 1.3 fixture | Reformatted changed tests; focused suite remained 338 passed |
| 2.3 | Same 247-pass baseline | Migration triangulation test: 1 failed (`authorization_denial_cause` metadata absent) | Focused migration suite: 6 passed; focused complete suite: 338 passed | Valid authorization deny round-trip and invalid routing-stage row prove the database constraint | Rolled back the test-only insert transaction to preserve later append-only count tests |
| 2.4 | Contract release did not exist | Focused RED included missing `schemas/releases/1.3.0/...audit.responses.denied...` fixture | `node schemas/tooling/release.mjs evidence --release 1.3.0` and `validate --release 1.3.0`: 143 artifacts, 8 checks | Positive audit fixture has `grant_not_applicable`; negative fixture rejects an unclosed cause; 1.2 positive fixtures validate through additive compatibility | Restored existing compact JSON-schema layout after a formatting-only expansion; regenerated immutable evidence and manifest |

## Work Unit Evidence
| Evidence | Result |
|---|---|
| Focused tests | `TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent uv run pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q` exit 0: 338 passed in 0.49s. |
| Relevant lint | `uv run ruff check src/sre_agent/governance/dto.py src/sre_agent/persistence/models.py src/sre_agent/gateway/audit.py migrations/versions/20260901_03_add_authorization_denial_cause.py tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py` exit 0. |
| Immutable release | `node schemas/tooling/release.mjs evidence --release 1.3.0` and `node schemas/tooling/release.mjs validate --release 1.3.0` exit 0: 143 artifacts and 8 checks; `npm --prefix schemas/tooling test` exit 0. |
| Runtime harness | `scripts/worktree-compose --profile checks run --build --rm python-checks sh -c 'shellcheck docker/harness-entrypoint.sh scripts/worktree-compose && ruff check --no-cache src/sre_agent/governance/dto.py src/sre_agent/persistence/models.py src/sre_agent/gateway/audit.py migrations/versions/20260901_03_add_authorization_denial_cause.py tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py && ruff format --check --no-cache src/sre_agent/governance/dto.py src/sre_agent/persistence/models.py src/sre_agent/gateway/audit.py migrations/versions/20260901_03_add_authorization_denial_cause.py tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py && uv lock --check --no-cache && pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q && alembic check'` exit 0: shellcheck, Ruff, formatting, and lock checks passed; 339 passed in 0.57s; `No new upgrade operations detected.` The unmodified default command remains known to fail 8 unrelated `test_security_catalogs.py` tests because `docker/api.Dockerfile` does not copy `docs/security/**`. |
| Rollback boundary | Revert audit DTO/model/projector changes, `20260901_03_add_authorization_denial_cause.py`, the complete immutable `schemas/releases/1.3.0/**` release, release-tooling version maps/tests, audit tests, `tasks.md`, and this progress file. Leave PR 2 engine code and deferred PR 4 Responses/repository work intact. |

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
