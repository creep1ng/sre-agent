# Apply Progress: Implement Issue #11 Minimal Persistence

Mode: Standard. Delivery: auto-chain, stacked-to-main. Completed slices: PR 1 DTOs; PR 2 schema; PR 3 repositories/audits; PR 4 seed/runtime; PR 5 CI/docs/conformance.

## Completed Tasks
- [x] 1.1 Strict HT-01 DTOs and safe row projections.
- [x] 1.2 Fixture-driven 1.0.0/1.1.0 parity tests.
- [x] 2.1 Async database boundary and five constrained ORM tables.
- [x] 2.2 Transactional Alembic migration and PostgreSQL evidence.
- [x] 3.1 Narrow async lookup, active direct-grant decision, and append/read repositories.
- [x] 3.2 PostgreSQL evidence for default deny, durable audits, bounds, and mutation rejection.
- [x] 4.1 Deterministic transactional seeds, strict local settings, and secret-safe scrypt storage.
- [x] 4.2 Explicit migrate/seed lifecycle, session provider, readiness, and image wiring.
- [x] 4.3 PostgreSQL seed, health, lifecycle, convergence, and conflict evidence.
- [x] 5.1 PostgreSQL-backed CI, explicit operations guidance, conformance, and reverse-order rollback boundaries.
- [x] 5.2 Full static, PostgreSQL, Alembic, Compose, and issue 11 conformance evidence.

## Work Unit Evidence
| Evidence | Result |
|---|---|
| Focused tests | `.venv/bin/pytest -q tests/test_governance_dto.py` — 156 passed |
| Runtime harness | Fixture round-trip and secret/routing rejection through every DTO/projector — 156 passed |
| Proportional lint | `.venv/bin/ruff check src/sre_agent/governance src/sre_agent/persistence tests/test_governance_dto.py` — passed |
| Rollback boundary | Revert `src/sre_agent/governance/`, `src/sre_agent/persistence/projections.py`, and `tests/test_governance_dto.py` |
| PR 2 focused tests | `.venv/bin/pytest -q tests/test_migrations.py` — 4 passed |
| PR 2 runtime harness | PostgreSQL 17.4 async UoW, repeated head, constraints, and append-only trigger — 4 passed |
| PR 2 proportional lint | `.venv/bin/ruff check src/sre_agent/persistence/{database,models}.py migrations tests/test_migrations.py` — passed |
| PR 2 rollback boundary | Revert `alembic.ini`, `migrations/`, `database.py`, `models.py`, `test_migrations.py`, and dependency pins/lock |
| PR 3 focused tests | `.venv/bin/pytest -q tests/test_persistence_repositories.py` — 3 passed |
| PR 3 regression tests | `.venv/bin/pytest -q tests/test_governance_dto.py tests/test_persistence_repositories.py` — 159 passed |
| PR 3 runtime harness | Real PostgreSQL allow/deny decisions, committed audit reread, bounded reads, and trigger-rejected raw `UPDATE`/`DELETE` — passed |
| PR 3 proportional lint | `.venv/bin/ruff check src/sre_agent/persistence/repositories.py src/sre_agent/persistence/projections.py tests/test_persistence_repositories.py` — passed |
| PR 3 rollback boundary | Revert `repositories.py`, the audit row projection adjustment in `projections.py`, and `test_persistence_repositories.py`; the database trigger remains owned by PR 2 |
| PR 4 focused tests | `.venv/bin/pytest -q tests/test_demo_seeds.py tests/test_health.py` — 7 passed |
| PR 4 regression tests | DTO, repository, seed, and health suites — 166 passed |
| PR 4 runtime harness | Compose built the image, ran migrate → seed → healthy API, then repeated migrate and reported `seed converged` |
| PR 4 proportional lint | Ruff check and format check for persistence, composition, health, and focused tests — passed |
| PR 4 rollback boundary | Revert `seeds.py`, `test_demo_seeds.py`, `.env.example`, Compose/Docker wiring, and the session/readiness changes |
| PR 5 structural check | Parsed `.github/workflows/ci.yml`; jobs include the existing gates plus `issue-11-postgresql` |
| PR 5 format normalization | `.venv/bin/ruff format` on the seven maintainer-authorized files — 7 reformatted; 104 additions + 52 deletions = 156 changed lines; semantics unchanged |
| PR 5 lint and format checks | `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .` — passed; 27 files formatted |
| PR 5 lock check | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv lock --check` — resolved 37 packages; lock current |
| PR 5 focused PostgreSQL tests | Four persistence/health suites on PostgreSQL 17.4 — 14 passed |
| PR 5 full regression | Full pytest on PostgreSQL 17.4 — 178 passed |
| PR 5 migration check | `.venv/bin/alembic upgrade head` then `.venv/bin/alembic check` — no new upgrade operations detected |
| PR 5 Compose harness | Isolated image build, migrate, seed, healthy API/web, repeated migrate, `seed converged`, and issue 10 harness — passed; project volume/network removed |
| PR 5 issue 11 conformance | `npm --prefix schemas/tooling run conformance -- --consumer issue-11` — validated via `schema-persistence` |
| PR 5 diff hygiene | `git diff --check HEAD` — passed, exit 0 |
| PR 5 authored review budget | CI/docs 172 + format normalization 156 = 328 changed lines |
| PR 5 rollback boundary | Revert workflow/docs plus formatter-only deltas in the seven authorized Python/test files; no semantics belong to this slice |

## Remaining Tasks
None. All tasks are complete and ready for independent SDD verification.

## Focused Remediation: CI-01 and DOC-01

Bound failed evidence revision: `sha256:f18dcd0e1c9d5c3d2fab4942d12305cc29edc45cc289fec4371622da3ad7853e`.

| Evidence | Result |
|---|---|
| CI-01 correction | The general Python job excludes the three PostgreSQL-backed modules; `issue-11-postgresql` owns and collects them with its PostgreSQL 17.4 service and database URLs. |
| DOC-01 correction | Architecture guidance now states that readiness verifies `alembic_version` contains revision `20260822_01`, matching `postgres_readiness_probe`. |
| CI ownership inspection | Parsed `.github/workflows/ci.yml` and asserted exclusion/ownership, PostgreSQL service, database URL, and module collection — passed. |
| Focused test | `.venv/bin/pytest -q --ignore=tests/test_migrations.py --ignore=tests/test_persistence_repositories.py --ignore=tests/test_demo_seeds.py` — 167 passed. |
| Exact regression | PostgreSQL 17.4 plus `.venv/bin/pytest -q` with host `DATABASE_URL`/`TEST_DATABASE_URL` — 178 passed. |
| Proportional validation | Ruff check and format-check, readiness documentation assertion, and `git diff --check HEAD` — passed. |
| Runtime harness | Isolated `sre-agent-issue11-remediation` PostgreSQL service supported the full regression; container, network, and volume were removed. |
| Correction budget | Workflow/docs: 15 additions + 3 deletions; evidence artifact: 16 additions; 34 total changed lines, below the 200-line remediation limit. |
| Rollback boundary | Revert only the test-ownership edits in `.github/workflows/ci.yml` and readiness wording in `docs/architecture.md`; no product behavior changed. |
