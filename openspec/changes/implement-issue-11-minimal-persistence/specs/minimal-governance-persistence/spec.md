# Minimal Governance Persistence Specification

## Purpose

Provide repeatable PostgreSQL storage for HT-01 projections while keeping `/schemas` authoritative.

## Requirements

### Requirement: Constrained five-table schema and repeatable migrations

The schema MUST contain exactly five application/domain tables: `principals`, `credentials`, `resources`, `grants`, and `audit_events`. It MUST enforce HT-01 vocabularies, foreign keys, uniqueness, and lifecycle constraints. Migrations MUST be explicit, repeatable, and transactional; the migration tool's version ledger MAY exist as metadata.

#### Scenario: Clean and repeated upgrade
- GIVEN an empty PostgreSQL database
- WHEN the migration command runs twice to head
- THEN both succeed, with no extra application/domain table

### Requirement: Strict HT-01 projections

DTOs and rows MUST match HT-01 field, type, vocabulary, nullability, and identifier parity for Principal, CredentialReference, Resource, ModelAlias, Grant, PolicyDecision, and AuditEvent. ORM/DTOs are adapters, not authority; credential rows MUST NOT project raw keys/hashes, and Resource/Grant projections MUST reject routing/provider fields.

#### Scenario: Fixture parity
- GIVEN valid and invalid HT-01 fixtures
- WHEN they are mapped through DTO and row projections
- THEN valid fixtures round-trip; extra/secret fields are rejected

### Requirement: Single-workspace principals and local credential safety

The system MUST support multiple `human|agent` principals in one workspace and MUST NOT add organizations, roles, users, scopes, tenants, or multi-tenancy. Each of four seeded principals MUST have a raw key from local `.env`; `.env` MUST be Git-ignored and keys MUST never be logged or committed. The database stores only a one-way hash and safe prefix.

#### Scenario: Seeded identities are separated
- GIVEN the four named principals
- WHEN identity metadata and credentials are read
- THEN kinds are `human|agent`, credentials are active, and `triage-agent` has none

### Requirement: Resolved triage assignment

The logical `triage-agent` resource MUST resolve model and provider from required environment settings. The model MUST match `<lab>/<model>` and provider MUST be HT-01-valid; missing, literal placeholders, or malformed values MUST fail before persistence.

#### Scenario: Valid assignment persists
- GIVEN model `openai/gpt-4o-mini` and provider `openai` in the environment
- WHEN the seed runs
- THEN both values persist on the active LLM resource, separate from grants

### Requirement: Deterministic transactional seed

The seed MUST create four principals, four credentials, the `triage-agent` resource, the initial grant, and stable IDs transactionally. Reruns MUST converge without credential rotation or duplicates. Incompatible state MUST roll back all changes and return a secret-free conflict.

#### Scenario: Exact rerun converges
- GIVEN a successful seed
- WHEN the identical seed runs again
- THEN IDs, counts, hashes, assignments, and grants are unchanged

#### Scenario: Incompatible seed is atomic
- GIVEN existing seed state differs from expected state
- WHEN the seed runs
- THEN nothing mutates and the conflict contains no raw key, hash, or secret

### Requirement: Default-deny direct grant

Only `incident-harness` MAY receive the initial active `invoke` allow on `triage-agent`. Grants MUST be direct `allow` records with no routing/provider data; explicit deny effects are invalid. An absent active grant MUST produce `deny`, `no_matching_grant`, and `policy_id: null`.

#### Scenario: Restricted principal is denied
- GIVEN `restricted-harness` has no active grant
- WHEN it requests `invoke` on `triage-agent`
- THEN it returns HT-01 default deny: `deny/no_matching_grant/null`

### Requirement: Durable append-only audits

Allow and deny decisions MUST be persisted as closed HT-01 AuditEvent rows before release. Database operations MUST reject `UPDATE` and `DELETE`; repositories expose append/read only.

#### Scenario: Audit mutation is rejected
- GIVEN persisted allow and deny audit rows
- WHEN an update or delete is attempted through SQL or a repository
- THEN it fails and original rows remain unchanged

### Requirement: Explicit lifecycle orchestration

Migration and seed execution MUST be explicit commands or one-shot steps. Startup MUST NOT implicitly create, alter, migrate, or seed the database.

#### Scenario: Startup leaves schema unchanged
- GIVEN an application pointed at an unmigrated database
- WHEN the application starts without the migration step
- THEN it does not mutate schema or seed data and reports the prerequisite safely
