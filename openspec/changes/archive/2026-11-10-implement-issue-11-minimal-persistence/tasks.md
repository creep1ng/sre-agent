# Tasks: Implement Issue #11 Minimal Persistence

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 900–1,200 authored lines |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 DTOs → PR 2 schema/models → PR 3 repositories/audits → PR 4 seed/runtime → PR 5 CI/docs/conformance |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Strict HT-01 DTO/projections | PR 1 (≤400) | `pytest -q tests/test_governance_dto.py` | Fixture round-trip and secret rejection | Revert `src/sre_agent/governance/dto.py`, `src/sre_agent/persistence/projections.py` |
| 2 | Five-table migration and ORM constraints | PR 2 (≤400) | `pytest -q tests/test_migrations.py` | Clean/repeated `alembic upgrade head` on PostgreSQL | Downgrade/revert `migrations/`, `src/sre_agent/persistence/models.py` |
| 3 | Repositories, default deny, append-only audits | PR 3 (≤400) | `pytest -q tests/test_persistence_repositories.py` | Allow/deny plus SQL UPDATE/DELETE rejection | Revert `src/sre_agent/persistence/repositories.py`, trigger |
| 4 | Deterministic seed and runtime wiring | PR 4 (≤400) | `pytest -q tests/test_demo_seeds.py tests/test_health.py` | `docker compose run --rm migrate`, `seed`, readiness | Revert `src/sre_agent/persistence/seeds.py`, runtime wiring |
| 5 | CI/docs/conformance evidence | PR 5 (≤400) | `npm --prefix schemas/tooling run conformance -- --consumer issue-11` | Full Compose harness and CI PostgreSQL job | Revert workflow/docs only |

## Phase 1: Contract Projections (PR 1)

- [x] 1.1 Add strict DTOs in `src/sre_agent/governance/dto.py` and row projections in `src/sre_agent/persistence/projections.py`; reject extras, hashes, raw keys, and routing fields.
- [x] 1.2 Add fixture-driven positive/negative parity tests, including 1.0.0/1.1.0 vocabulary, nullability, and identifier cases.

## Phase 2: Schema Foundation (PR 2)

- [x] 2.1 Add `src/sre_agent/persistence/database.py` session boundary and `models.py` five-table models with vocabulary, FK, uniqueness, lifecycle, and LLM-only constraints.
- [x] 2.2 Add transactional `migrations/versions/*_create_minimal_governance_store.py` and tests for clean/repeated upgrade, exact table count, constraints, and audit trigger.

## Phase 3: Persistence Ports (PR 3)

- [x] 3.1 Add narrow async repositories in `src/sre_agent/persistence/repositories.py`; project rows without secrets and match only active direct grants.
- [x] 3.2 Test incident-harness allow, restricted/admin default deny (`deny/no_matching_grant/null`), committed allow/deny audits, bounded reads, and mutation rejection.

## Phase 4: Seed and Composition (PR 4)

- [x] 4.1 Add `src/sre_agent/persistence/seeds.py`, strict settings, ignored `.env` placeholders, scrypt hashes, stable IDs, resolved model/provider validation, exact reruns, and atomic conflicts.
- [x] 4.2 Wire explicit migrate/seed one-shots, application session provider, sanitized unmigrated readiness, and Docker image contents.
- [x] 4.3 Add seed/health/integration tests proving four principals, four credentials, one triage resource, one grant, no secret leakage, and startup never migrates/seeds.

## Phase 5: Evidence and Operations (PR 5)

- [x] 5.1 Add the PostgreSQL job to `.github/workflows/ci.yml`; update README and architecture guidance with migration/seed commands, conformance, and rollback boundaries.
- [x] 5.2 Run focused suites, full pytest/Ruff, Compose harness, CI PostgreSQL job, and `issue-11` conformance before delivery.
