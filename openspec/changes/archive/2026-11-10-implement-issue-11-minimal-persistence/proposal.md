# Proposal: Implement Issue #11 Minimal Persistence

## Intent

Implement HT-01 PostgreSQL persistence on issue #10, providing identity, authorization, assignment, and audit ports for #13/#14 while contracts remain authoritative.

## Scope

### In Scope
- Strict Pydantic projections of HT-01 governance types.
- SQLAlchemy 2/Alembic with exactly `principals`, `credentials`, `resources`, `grants`, and `audit_events`.
- Narrow async repositories, explicit migrations/tests, and composition without startup migration.
- Transactional deterministic seeds for `admin-human`, `demo-human`, `incident-harness`, `restricted-harness`, and resource `triage-agent`.
- Per-principal development keys from Git-ignored `.env`; `.env.example` documents placeholders. Store only one-way hashes and safe prefixes.

### Out of Scope
- Organizations, workspace IDs, roles, groups, multi-tenancy, explicit denies, or a sixth alias table.
- Endpoints, bearer authentication, gateway/provider calls, credential APIs, or audit retention/content access.

## Capabilities

### New Capabilities
- `minimal-governance-persistence`: Repeatable HT-01 storage, deterministic bootstrap, default deny, and append-only audits.

### Modified Capabilities
None. This implements without changing issue #9's `shared-governance-schemas`, `control-plane-contract`, `audit-redaction-contract`, and `contract-governance-conformance`.

## Approach

Use async SQLAlchemy over psycopg and Alembic. Store ModelAlias fields in LLM-only `resources` columns; grants reference resource identity. Require both `TRIAGE_AGENT_MODEL` and `TRIAGE_AGENT_PROVIDER` environment inputs; reject angle-bracket values. Exact seeds converge; conflicts roll back atomically with secret-free diagnostics. Only `incident-harness` gets active `invoke` access to `triage-agent`; absent grants deny. The database rejects audit updates/deletes. Deliver stacked-to-main work units targeting 400 lines or fewer.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/sre_agent/{governance,persistence}/` | New | DTOs, database boundary, repositories, seeds |
| `migrations/`, `alembic.ini` | New | Repeatable schema and append-only enforcement |
| `compose.yaml`, CI, tests, docs | Modified | Explicit migration/seed flow and PostgreSQL evidence |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Contract/storage drift | Med | Fixture-driven DTO and row parity tests |
| Dependency-resolution drift | Med | Resolve and review pinned lock changes; never guess versions |
| Oversized review | High | Auto-chain behavior-complete stacked slices |

## Rollback Plan

Revert stacked slices in reverse. Before durable data, downgrade; afterward, restore runtime while preserving tables and audit backup.

## Dependencies

- Issue #9/HT-01 releases and ADR-002 through ADR-006.
- Base `fd79507` (or merged equivalent) containing issue #10 runtime and PostgreSQL Compose service.

## Success Criteria

- [ ] Clean and repeated upgrades pass with five constrained tables.
- [ ] Seed reruns preserve IDs/counts/hashes, never reveal secrets, and conflicts mutate nothing.
- [ ] Every seeded principal has an active credential; only `incident-harness` has the initial grant, and absence yields `deny/no_matching_grant/policy_id=null`.
- [ ] Resolved `triage-agent` assignment validates; literal angle-bracket placeholders fail.
- [ ] Allow and deny audits persist durably; SQL update/delete attempts fail.
- [ ] Issue #11 HT-01 conformance and PostgreSQL-backed CI pass.
