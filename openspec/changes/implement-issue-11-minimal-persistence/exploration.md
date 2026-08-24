## Exploration: Issue #11 minimal persistence

### Current State

The repository has the required contracts and a local backend foundation, but they are not yet present in the same checked-out tree. The current worktree is detached at `617c660`; the local `feat/issue-10-local-runtime` branch at `fd79507` contains the FastAPI/Python 3.12 runtime, PostgreSQL 17 Compose service, `psycopg`, pytest/pytest-asyncio, Ruff, CI, and the single `sre_agent.application.create_application` composition root. No ORM entities, migration runner, database session abstraction, repository, seed implementation, or persistence integration tests exist.

HT-01 is the contract authority. Releases `schemas/releases/1.0.0/` and `1.1.0/` define closed Principal, CredentialReference, Resource, ModelAlias, Grant, PolicyDecision, and AuditEvent representations. ADR-002 through ADR-006 require single-workspace principals, one-way API-key storage, direct allow grants with default deny, and durable append-only audit events with fail-closed redaction. The consumer registry explicitly says framework DTOs, ORM models, and database models are not contract authority.

The existing `npm --prefix schemas/tooling run conformance -- --consumer issue-11` command validates the pinned HT-01 identity/model-resource/policy fixtures. It does not validate an actual PostgreSQL mapping. Python CI currently runs `ruff check .`, `ruff format --check .`, and `pytest`; Compose smoke verifies only health and contract transport. `openspec/config.yaml` still describes the pre-issue-10 repository, so downstream work must first use a base that contains `feat/issue-10-local-runtime` and then reconcile that stale project-context statement through the appropriate SDD phase rather than infer that the runtime is absent.

Key implementation constraints are:

- `Principal.kind` is only `human|agent`; organization, tenant, user, role, and scope authority are out of scope.
- Persistent credentials may contain only an internal one-way hash and safe prefix; raw keys and `Authorization` must never enter DTOs, rows, logs, audit events, fixtures, or errors.
- Grants are direct `allow` records over `(principal, action, resource)` and only active grants match. No row means `deny/no_matching_grant/policy_id=null`; there is no explicit deny grant.
- Routing data must not enter a Grant. The logical `triage-agent` LLM resource needs a separate ModelAlias projection to its concrete `<lab>/<model>` assignment.
- Audit events must be accepted durably before later gateway work can release an allow or deny outcome, and accepted rows must not be updated or deleted. Only closed, already-redacted HT-01 fields may be stored.
- The literal string `<lab>/<model>` does not satisfy the HT-01 concrete-model pattern. Proposal/spec must freeze it as configuration placeholders and persist resolved values such as `lab/model`, not the angle brackets.

### Affected Areas

- `pyproject.toml` — add pinned direct Pydantic, SQLAlchemy, and Alembic dependencies; keep PostgreSQL on the existing psycopg 3 driver.
- `src/sre_agent/settings.py` — expose the database URL to SQLAlchemy without breaking the raw psycopg readiness DSN; normalize `postgresql://` internally instead of changing the shared environment value to a driver-specific URL.
- `src/sre_agent/application.py` — compose a session/repository provider for future #13/#14 consumers without running migrations implicitly at API startup.
- `compose.yaml` — add an explicit one-shot migration/seed dependency before the API, while preserving the existing database volume and health ordering.
- `docker/api.Dockerfile` — copy the Alembic configuration and migrations into the runtime image; it currently copies only `pyproject.toml` and `src/`.
- `.github/workflows/ci.yml` — add PostgreSQL-backed migration, repository, and deterministic-seed checks; retain the current Python, contract, and Compose gates.
- `src/sre_agent/governance/dto.py` — new strict Pydantic DTOs aligned to HT-01 while remaining projections, not contract authority.
- `src/sre_agent/persistence/database.py` — new async SQLAlchemy engine/session factory and transaction boundary.
- `src/sre_agent/persistence/models.py` — new internal models for `principals`, `credentials`, `resources`, `grants`, and `audit_events`, with named foreign-key, uniqueness, and closed-vocabulary constraints.
- `src/sre_agent/persistence/repositories.py` — new narrow async interfaces/adapters for identity lookup, credential metadata/hash lookup, resource lookup, active-grant decision, and audit append/read. Avoid a generic CRUD repository.
- `src/sre_agent/persistence/seeds.py` — new transactional, deterministic, idempotent demo seed for `admin-human`, `incident-harness`, `restricted-harness`, `triage-agent`, credentials, and the incident-harness-only allow grant.
- `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/*_create_minimal_governance_store.py` — new repeatable schema migration surface.
- `tests/test_governance_dto.py` — prove positive/negative HT-01 fixture mapping and forbid extra/secret-bearing fields.
- `tests/test_persistence_repositories.py` — exercise PostgreSQL round trips, active-grant allow, absent-grant deny, and allow/deny audit persistence.
- `tests/test_migrations.py` — prove clean upgrade, repeated `upgrade head`, and required constraints/append-only behavior.
- `tests/test_demo_seeds.py` — run the seed twice and prove stable IDs/counts/hashes, no duplicate grant, no secret persistence, and no grant for the restricted harness.
- `docs/architecture.md` and `README.md` — document the explicit migration/seed path, persistence boundary, verification commands, and rollback only when implementation is delivered.

### Approaches

1. **SQLAlchemy 2 + Alembic + separate Pydantic DTOs** — use async SQLAlchemy over psycopg, explicit repository adapters, and contract-aligned DTO projections.
   - Pros: matches the FastAPI async runtime, gives repeatable migrations and transaction boundaries, keeps ORM/DTO/contract authority separate, and creates clean ports for #13/#14.
   - Cons: adds dependencies and mapping code; PostgreSQL integration tests need a real database.
   - Effort: High

2. **Raw psycopg repositories + SQL migration files** — extend the existing driver directly and hand-map rows to Pydantic DTOs.
   - Pros: smallest runtime dependency increase and full SQL control.
   - Cons: requires a custom migration ledger or a second migration tool, duplicates row-mapping/transaction logic, and makes schema drift easier to miss.
   - Effort: Medium initially, High to maintain

3. **SQLModel/shared ORM-DTO classes** — combine persistence and Pydantic models.
   - Pros: fewer files and less mapping code.
   - Cons: conflicts with HT-01's explicit authority boundary, risks leaking `secret_hash` or database-only fields, and couples later API changes to storage layout.
   - Effort: Medium, but not recommended

### Recommendation

Use approach 1. Keep the external `DATABASE_URL=postgresql://...` valid for psycopg readiness and derive a SQLAlchemy driver URL inside `database.py`. Use `TEXT` plus named check constraints for contract vocabularies, `TIMESTAMPTZ` for lifecycle fields, a composite resource identity `(resource_type, resource_id)`, and database foreign keys from grants. Keep `secret_hash` strictly internal to the credential row and project only CredentialReference fields.

For minimal scope, let the `resources` row back both the two-field Resource DTO and the LLM-only ModelAlias projection through nullable assignment columns constrained to `resource_type=llm_model`; Grants reference only the base resource identity. This preserves the requested five-table boundary without putting router/provider/model data into grants. If product requirements soon need multiple assignments per resource, split that mapping into a sixth `model_aliases` table in a later migration rather than introduce a generic JSON metadata bag now.

Map required AuditEvent scalar fields to typed columns and closed nested evidence to JSONB columns only after Pydantic validation. Expose `append` and bounded query operations, never update/delete operations, and add a PostgreSQL trigger that rejects `UPDATE` and `DELETE` for accepted audit rows. Repository behavior must persist both the HT-01 allowed-response and denied-authorization fixtures.

Run migrations explicitly through a one-shot Compose/CI command; do not auto-migrate from FastAPI startup. Seed all demo records in one transaction using stable IDs and conflict checks. A repeat must converge without credential rotation or key reveal, and incompatible partial state must fail without mutation. Only `incident-harness` receives an active `invoke` grant to `triage-agent`; `restricted-harness` and `admin-human` prove default deny by absence.

The implementation is likely above the 400-line review budget. Plan it as reviewable work units: (1) DTO/contract mapping with fixture tests, (2) migration/models with PostgreSQL tests, (3) repositories/default-deny/audit append with tests, and (4) deterministic seed plus Compose/CI/docs. Each unit must keep its tests and rollback boundary with the behavior it introduces.

### Risks

- Downstream implementation on the current detached HEAD would miss the entire issue-10 foundation; it must use a base containing `fd79507` or its merged equivalent.
- Literal `<lab>/<model>` seed text is schema-invalid; unresolved placeholder semantics would block deterministic fixtures.
- Combining Resource and ModelAlias persistence is intentionally minimal but must enforce LLM-only assignment constraints to avoid routing leakage into other resource types.
- A DTO/ORM-only audit immutability rule can be bypassed by SQL; database enforcement is required.
- Contract conformance currently proves JSON fixtures, not Python/row parity; fixture-driven DTO and repository tests must close that gap.
- The repository has no verified transitive Python lock, so dependency updates require a network-enabled resolver and lock review rather than guessed versions.

### Ready for Proposal

Yes. The proposal should lock the five-table SQLAlchemy/Alembic boundary, resolved demo model-assignment inputs, exact deterministic credential IDs/secret source, append-only audit enforcement, and a base that includes the issue-10 runtime.
