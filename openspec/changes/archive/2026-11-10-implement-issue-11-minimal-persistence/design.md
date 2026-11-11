# Design: Implement Issue #11 Minimal Persistence

## Technical Approach

Add a persistence adapter beneath the existing FastAPI composition root: strict Pydantic v2 projections mirror HT-01 release 1.1.0, while async SQLAlchemy 2/Alembic own PostgreSQL mapping. `/schemas` remains authoritative. Migrations and seed execution are one-shot operations, never application startup work.

## Architecture Decisions

| Topic | Choice and rationale | Rejected / tradeoff |
|---|---|---|
| Transactions | `database.py` converts the shared `postgresql://` DSN to `postgresql+psycopg://`, builds `create_async_engine` and `async_sessionmaker(expire_on_commit=False)`, and exposes an `async with session.begin()` unit-of-work. Services/seeding own commit/rollback; repositories receive a session and only flush/read. | Repository commits obscure atomicity; startup-owned sessions leak lifecycle. |
| Authority | `governance/dto.py` uses `ConfigDict(strict=True, extra="forbid")`; `projections.py` explicitly maps rows to Principal, CredentialReference, Resource, ModelAlias, Grant, PolicyDecision, and AuditEvent. | Shared ORM/DTO models could expose hashes and redefine HT-01. |
| Five tables | `models.py` defines only `principals`, `credentials`, `resources`, `grants`, `audit_events`; `alembic_version` is permitted metadata. Resource rows hold nullable ModelAlias columns, constrained non-null only for `llm_model`; Grant contains no routing fields. Audit scalar fields are typed and validated nested evidence is JSONB. | A sixth alias table or generic metadata JSON violates scope. |
| Credentials | Four raw development keys come only from ignored `.env`; built-in scrypt encoded hashes and 8-character safe prefixes persist. Reruns verify against the existing salted hash rather than rehashing. Errors/logs/audits contain neither raw keys nor hashes. | Fast hashes, recoverable encryption, and key logging weaken ADR-003. |
| Audit | A PostgreSQL `BEFORE UPDATE OR DELETE` trigger rejects mutation. `AuditRepository` exposes append and bounded read only; append becomes accepted only after its caller-owned transaction commits. | ORM-only immutability is bypassable. |

## Data and Seed Flow

```text
environment -> strict settings/DTO validation -> one SERIALIZABLE seed transaction
            -> repositories -> five tables -> explicit DTO projections
```

Stable principals are `admin-human`/`demo-human` (`human`) and `incident-harness`/`restricted-harness` (`agent`), with credential IDs `credential-<principal>`. `SeedSettings` requires `ADMIN_HUMAN_API_KEY`, `DEMO_HUMAN_API_KEY`, `INCIDENT_HARNESS_API_KEY`, `RESTRICTED_HARNESS_API_KEY`, `TRIAGE_AGENT_MODEL`, and `TRIAGE_AGENT_PROVIDER`; keys must have a safe prefix and at least 32 characters. `.env.example` contains only names/nonfunctional placeholders, and only the seed process receives these variables. Credential-less resource `(llm_model, triage-agent)` projects ModelAlias ID/alias `triage-agent`, router `openrouter`, and the configured model/provider; model must match HT-01 `<lab>/<model>`, provider must be non-empty and bounded. Only stable grant `grant-incident-harness-invoke-triage-agent` is active `allow/invoke`.

`seeds.py` validates all inputs before SQL, takes a transaction advisory lock, and compares seed-owned rows. Empty state inserts the complete graph; an exact graph is a no-op; partial or differing state raises `seed_state_conflict` with entity/field names only and rolls back. Unrelated principals remain valid. Grant lookup returns `allow/grant_matched/<id>` only for an active exact match; otherwise `deny/no_matching_grant/null`.

## File Changes

| Paths | Action |
|---|---|
| `src/sre_agent/governance/{__init__,dto}.py`; `src/sre_agent/persistence/{__init__,database,models,projections,repositories,seeds}.py` | Create DTO, unit-of-work, mapping, repository, and seed adapters. |
| `alembic.ini`; `migrations/{env.py,script.py.mako,versions/*_create_minimal_governance_store.py}` | Create transactional schema, constraints, indexes, and audit trigger. |
| `pyproject.toml`; `src/sre_agent/{settings,application}.py`; `src/sre_agent/gateway/health.py` | Pin direct Pydantic/SQLAlchemy/Alembic dependencies, compose the session provider, and report missing schema as sanitized readiness failure without mutation. |
| `.env.example`; `compose.yaml`; `docker/api.Dockerfile`; `.github/workflows/ci.yml` | Add seed variables, migration/seed one-shots, image artifacts, PostgreSQL CI, and issue-11 conformance. |
| `tests/{conftest,test_governance_dto,test_migrations,test_persistence_repositories,test_demo_seeds}.py`; `tests/test_health.py`; `README.md`; `docs/architecture.md` | Add PostgreSQL evidence and operating guidance. |

## Testing Strategy

Fixture-driven tests cover strict positive/negative 1.0.0 and 1.1.0 parity. PostgreSQL tests run clean/repeated `alembic upgrade head`, assert five domain tables plus metadata, constraints, default deny, committed allow/deny audits, SQL mutation rejection, exact seed reruns, atomic conflicts, and secret absence. CI adds a PostgreSQL service, ephemeral seed keys, and `conformance -- --consumer issue-11`; Compose runs fixed `migrate` (`alembic upgrade head`) then `seed` (`python -m sre_agent.persistence.seeds`) before API. Direct API startup never migrates/seeds.

## Threat Matrix

| Boundary | Applicability |
|---|---|
| Documentation-like paths | N/A: no executable-file classification. |
| Git repository selection | N/A: no Git invocation. |
| Commit state | N/A: no index operation. |
| Push state | N/A: no push operation. |
| PR commands | N/A: no PR automation. |

## Delivery / Rollback

Stacked-to-main units are: core DTOs; audit DTOs; migration/models; repositories/default deny/audit; seed plus Compose/CI/docs. Each carries focused tests, targets at most 400 authored changed lines, and splits again if forecast exceeds it. Revert in reverse order; before durable use downgrade, afterward preserve tables/audit backup.

## Open Questions

None.
