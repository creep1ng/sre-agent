# Runtime and persistence boundaries

Issue 10 establishes the deployable FastAPI runtime. Later vertical slices add PostgreSQL
governance, bearer authentication, administrative control, incident execution, and governed
capabilities without making ORM, DTO, or provider models authoritative.

## Composition

| Boundary | Python package | Current responsibility |
| --- | --- | --- |
| Control plane | `sre_agent.control` | Authenticated and authorized administration of Principals and credentials; later catalog/grant surfaces remain separately owned |
| Incident-resolution plane | `sre_agent.incident` | Workflow transitions, decisions, replay ports, and authoritative incident/run persistence |
| Harness | `sre_agent.harness` | Incident conversation and capability-orchestration boundary; it is not part of the gateway |
| Gateway | `sre_agent.gateway` | Health, authentication, capability authorization, governed responses, provider, and audit adapters |
| Deploy executor | `sre_agent.executor` | A separate process of the same image: named `deployment.rollback`/`deployment.restart` operations over docker-socket-proxy, idempotent by key and by state; it imports no other plane ([design](deploy-executor.md)) |

`sre_agent.application.create_application` is the only composition root:

- `GET /health/live` is dependency-free and proves the Python process can serve requests.
- `GET /health/ready` verifies the exact Alembic revision required by the running build, the
  code-owned `REQUIRED_SCHEMA_VERSION` in `src/sre_agent/gateway/health.py`; every later schema
  migration must advance that prerequisite in the same work unit (see the
  [change checklist](#change-checklist)). Failures return a fixed `503` response that excludes
  driver messages, DSNs, and credentials.
- The `/v1/principals` and `/v1/credentials` routes expose the real governed administrative API.
- `POST /v1/responses` validates and authenticates before logical-resource authorization, resolves
  routing only after allow, makes at most one OpenRouter request, commits a protected terminal
  audit event, then releases the normalized result.

The provider secret and timeout are API-only Compose settings. Seed services receive an explicit
allow-list of bootstrap variables instead of the whole `.env`; contract and deterministic harness
containers receive no provider credential. The optional live-smoke client receives only a safe
presence flag and calls the API boundary, so the OpenRouter key never crosses into a client image.

The schema releases remain the contract authority. Runtime models must not replace or rewrite files under `schemas/releases/`.

## Governed extension rule

Future LLM, MCP, skill, and knowledge consumers MUST enter through a declared governed operation:

1. Declare Bearer security and the server-owned `(action, resource_type, resource_id)` scope.
2. Call `authorize_governed_access` after operation validation and before lookup, routing, or adapter execution.
3. Use an exact existing grant; do not infer roles from principal names or client input.
4. Record the terminal audit event before releasing an allowed result, and keep denied effects at zero.

MCP and knowledge execution runtimes remain future-only until their runtime boundaries exist. The
administrative read path returns a persisted exact Skill version under the catalog grant, but does
not execute it. Administrators can activate or deactivate one exact version with an optimistic
`expected_updated_at` check. The separate content GET is `/v1/skills/{skill_id}/{version}/resolve`.
It requires direct active `invoke` grants for the exact root and every pinned dependency before
reading each version. Success returns the root and all direct dependencies atomically; an unavailable
dependency or any nested dependency produces the same non-disclosing 404. Status and grants are
rechecked on every request, and the exact URL keeps resume pinned to its original versions. The
request-correlated audit records metadata only; no implicit latest-version selection or content cache
is used.

Catalog `owner_id` is a functional subsystem label (for example `bok-platform`), not a reference
to a Principal: it is a plain identifier column with no foreign key to `principals`, and it grants
nothing. The administrator supplies `owner_id` and the discoverability metadata (display name,
tags) in the control-plane request that registers a catalog resource; the catalog does not read
them from the registered server.

## LLM consumption admission

`ConsumptionAdmissionService` (`src/sre_agent/gateway/consumption_admission.py`) reserves capacity
before any provider contact:

- When neither an incident token limit nor a monthly USD limit is active, admission allows without
  a reservation.
- An active limit needs guaranteed bounds, never estimates (#334, CA7), plus a dynamically capped
  `max_output_tokens`. A missing, expired, or unusable catalog fails closed with
  `consumption_bounds_unavailable`.
- Input bound: the UTF-8 byte count of the request's text plus 64 tokens per message
  (`text_input_bound`). Byte-level tokenizers emit at most one token per byte, so the prompt
  cannot exceed it. It is capped by the endpoint's prompt capacity (`max_prompt_tokens`, or
  `context_length` when OpenRouter reports null). A request with non-text parts would use that
  capacity instead; `/v1/responses` input is a single text message today.
- Output cap: the smallest of the endpoint's completion cap (or `context_length`), the context
  window minus the input bound, the incident balance minus the input bound, and the output the
  monthly balance can pay after the input and request fee.
- The catalog is queried for the routed model (`/api/v1/models/{author}/{slug}/endpoints`),
  never the alias. A null or absent `pricing.request` means no per-request fee; missing prompt or
  completion prices still fail closed. A configured provider slug matches every endpoint of that
  provider (by name or tag prefix) and uses the most conservative values across them: highest
  prices, highest prompt capacity, lowest completion cap and context window. An endpoint tag with
  a `/` (`fireworks/us`) matches that endpoint only. The catalog needs
  `OPENROUTER_MANAGEMENT_API_KEY`; without it every call under an active limit answers 429.
- A reservation needs an existing incident: an unknown `incident_id` under an active limit
  answers 422 `incident_not_found`, audited as `resource_not_found`.
- Each admitted request keeps the policy version it was admitted under, and its reservation stays
  booked until exact usage settles; an uncertain settlement keeps the reservation.
- Monthly limits use half-open UTC calendar months (`[first day 00:00, next first day 00:00)`),
  serialized per month with a PostgreSQL advisory lock.

## Release metadata

`/openapi.json` and Swagger identify a running API with three deliberately separate values:

| Metadata | OpenAPI location | Default | Meaning |
| --- | --- | --- |
| Application version | `info.version` | installed `sre-agent` package version | The runtime code version. |
| Contract version | `info.x-sre-agent-contract-version` | `2.0.0` | The immutable schema release implemented by the runtime. |
| Build revision | `info.x-sre-agent-build-revision` | `source-archive` | The source revision used to build this artifact. |

The Compose variables `SRE_AGENT_APPLICATION_VERSION`, `SRE_AGENT_CONTRACT_VERSION`, and
`SRE_AGENT_BUILD_REVISION` are optional build arguments and API runtime variables. A release
pipeline should set all three from its release manifest and checked-out revision; the runtime image
does not run Git or require a `.git` directory. Empty values keep the explicit source-archive
defaults, so source archives and local development remain buildable.

## Persistence ownership

PostgreSQL owns governance tables (`principals`, `credentials`, `resources`, `grants`,
`audit_events`, and control-plane idempotency records) plus the isolated `incident` schema for
incidents, runs, decisions, events, snapshots, correlated text context, and transition commits.
`alembic_version` is migration metadata, not a domain table. Governance repositories receive a
caller-owned async session; incident repositories run behind their own unit-of-work boundary. The
transaction owner decides when state and protected audit evidence commit.

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
plus `REMEDIATION_AGENT_MODEL` and `REMEDIATION_AGENT_PROVIDER`; documentation must never carry
functional API-key values. These values persist the `triage-agent` and `remediation-agent`
assignments; both aliases use the same `/v1/responses` contract and each authorized invocation
makes one provider attempt with fallback disabled. Seed validation happens before SQL. Exact state
is a no-op, while partial or differing seed-owned state rolls back and reports only entity/field
names. Routing drift is read safely with `--check-routing` and changed only through the explicit
`--reconcile-routing` seed action under the seed transaction lock.

## Change checklist

Several invariants are repeated across code, schema, and tests. Extend them together in the same
work unit:

- **New Alembic revision.** Set `REQUIRED_SCHEMA_VERSION` in `src/sre_agent/gateway/health.py`
  to the new head, otherwise `/health/ready` returns `503`. Update the tests that pin the exact
  head (for example `tests/test_health.py`, `tests/test_migrations.py`,
  `tests/test_skill_migration_compatibility.py`).
- **New table.** Add it to the manual `DROP TABLE` reset lists of the PostgreSQL-backed tests
  (for example `tests/issue454_support.py`), children before parents, or later tests fail with
  `DuplicateTable`.
- **New governed control route.** Register it in both `CONTROL_SCOPES`
  (`src/sre_agent/control/scopes.py`) and `CONTROL_OPERATIONS`
  (`src/sre_agent/control/service.py`), and update the tests that compare the two registries and
  enumerate every `/v1/` route.
- **New resource type or audit operation.** These are closed vocabularies repeated in the
  `governance/dto.py` Literals, the `ck_resources_type` and `ck_audit_events_operation` database
  checks, and the release schema enums. Extend every copy, or `AuditEvent` validation rejects the
  value and the request fails.
- **Backfilling `audit_events`.** The `audit_events_append_only` trigger rejects every `UPDATE`
  and `DELETE`, including a migration's own backfill. A backfilling migration drops the trigger,
  updates the rows, and recreates it in the same transaction, as
  `20260825_02_add_audit_latency.py` does.

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

CI keeps the Python, contract, static-web, browser, and Compose gates. The PostgreSQL job owns
migrations, seeds, persistence, authentication, administrative consumer, governed-response, and
audit suites; the contract job owns every published immutable release and its conformance tests.
Compose smoke additionally runs the isolated recording-provider harness. Ordinary CI explicitly
excludes the secret-gated live smoke.

The deterministic harness is authoritative for allow, 403 deny with zero provider calls,
normalized failures, protected audit readback, and release gating. The separately named live smoke
makes one bounded provider request only with operator enablement and API-owned secrets; it asserts
the normalized response envelope and protected routing metadata, never provider bodies or raw
audit rows.
