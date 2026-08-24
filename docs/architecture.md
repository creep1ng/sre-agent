# Runtime and persistence boundaries

Issue 10 establishes the deployable FastAPI runtime. Issue 11 adds a PostgreSQL adapter for the
HT-01 governance contracts without making ORM or DTO models authoritative.

## Composition

| Boundary | Python package | Current responsibility |
| --- | --- | --- |
| Control plane | `sre_agent.control` | Reserved boundary for governed configuration and administration |
| Incident-resolution plane | `sre_agent.incident` | Reserved boundary for incident analysis and remediation |
| Harness | `sre_agent.harness` | Contract and fixture execution boundary |
| Gateway | `sre_agent.gateway` | HTTP transport and health probes |

`sre_agent.application.create_application` is the only composition root. The current runtime exposes infrastructure health routes only:

- `GET /health/live` is dependency-free and proves the Python process can serve requests.
- `GET /health/ready` verifies that `alembic_version` contains revision `20260822_01`. Failures
  return a fixed `503` response that excludes driver messages, DSNs, and credentials.

The schema releases remain the contract authority. Runtime models must not replace or rewrite files under `schemas/releases/`.

## Persistence ownership

PostgreSQL contains exactly five domain tables: `principals`, `credentials`, `resources`,
`grants`, and append-only `audit_events`; `alembic_version` is migration metadata. Repositories
receive a caller-owned async session and flush or read only. The transaction owner decides when
seed changes and accepted audit events commit.

The application startup path only constructs the session provider. It does not create, migrate,
or seed schema. Operators own the lifecycle explicitly:

```bash
docker compose run --rm migrate
docker compose run --rm seed
npm --prefix schemas/tooling run conformance -- --consumer issue-11
```

Seed configuration comes only from the ignored `.env` file. Required names are
`ADMIN_HUMAN_API_KEY`, `DEMO_HUMAN_API_KEY`, `INCIDENT_HARNESS_API_KEY`,
`RESTRICTED_HARNESS_API_KEY`, `TRIAGE_AGENT_MODEL`, and `TRIAGE_AGENT_PROVIDER`; documentation
must never carry functional API-key values. Seed validation happens before SQL. Exact state is a
no-op, while partial or differing seed-owned state rolls back and reports only entity/field names.

## Rollback boundaries

| Reverse order | Boundary |
| --- | --- |
| 1. CI and operations docs | Revert `.github/workflows/ci.yml`, `README.md`, and this guide. |
| 2. Seed and runtime wiring | Revert seed, Compose/image, settings, application, and readiness wiring. |
| 3. Repository ports | Revert repository adapters and their projection adjustment; preserve the audit trigger. |
| 4. Schema | Before durable use, run `docker compose run --rm migrate alembic downgrade base`, then revert migration/models/database wiring. |
| 5. Contract projections | Revert governance DTOs and projections only after persistence consumers are gone. |

After durable rows or audits exist, the downgrade boundary closes: preserve and back up the
database, revert runtime behavior without deleting tables, then use an operator-reviewed forward
migration or restore plan. Audit history must not be rewritten to simplify rollback.

## Verification path

CI keeps the existing Python, contract, static-web, and Compose gates. The issue 11 job adds a
real PostgreSQL 17.4 service, repeated migrations and seeds, focused persistence suites,
`alembic check`, and the issue 11 conformance consumer. Locally, run the same focused suites plus
full `pytest`, Ruff check/format check, `uv lock --check`, and the Compose harness before delivery.
