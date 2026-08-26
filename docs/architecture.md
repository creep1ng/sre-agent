# Runtime and persistence boundaries

Issue 10 establishes the deployable FastAPI runtime. Issues 11–14 add PostgreSQL governance,
bearer authentication, and one governed HT-01 response path without making ORM, DTO, or provider
models authoritative.

## Composition

| Boundary | Python package | Current responsibility |
| --- | --- | --- |
| Control plane | `sre_agent.control` | Reserved boundary for governed configuration and administration |
| Incident-resolution plane | `sre_agent.incident` | Reserved boundary for incident analysis and remediation |
| Harness | `sre_agent.harness` | Contract and fixture execution boundary |
| Gateway | `sre_agent.gateway` | Health, authentication, governed responses, provider and audit adapters |

`sre_agent.application.create_application` is the only composition root:

- `GET /health/live` is dependency-free and proves the Python process can serve requests.
- `GET /health/ready` verifies that `alembic_version` contains revision `20260825_02`. Failures
  return a fixed `503` response that excludes driver messages, DSNs, and credentials.
- `POST /v1/responses` validates and authenticates before logical-resource authorization, resolves
  routing only after allow, makes at most one OpenRouter request, commits a protected terminal
  audit event, then releases the normalized result.

The provider secret and timeout are API-only Compose settings. Seed services receive an explicit
allow-list of bootstrap variables instead of the whole `.env`; contract and deterministic harness
containers receive no provider credential. The optional live-smoke client receives only a safe
presence flag and calls the API boundary, so the OpenRouter key never crosses into a client image.

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
docker compose --profile issue-14 run --build --rm issue-14-harness
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-14
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

CI keeps the Python, contract, static-web, and Compose gates. The PostgreSQL job owns migrations,
seeds, persistence, authentication, governed-response and audit suites; the contract job owns the
immutable 1.2.0 release and issue-14 conformance. Compose smoke additionally runs the isolated
recording-provider harness. Ordinary CI explicitly excludes the secret-gated live smoke.

The deterministic harness is authoritative for allow, 403 deny with zero provider calls,
normalized failures, protected audit readback, and release gating. The separately named live smoke
makes one bounded provider request only with operator enablement and API-owned secrets; it asserts
the normalized response envelope and protected routing metadata, never provider bodies or raw
audit rows.
