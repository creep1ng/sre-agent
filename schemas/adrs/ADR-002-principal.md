# ADR-002: Single-workspace Principal

- **Status:** Accepted
- **Contract version:** 1.0.0

## Context

Governance consumers need one portable identity type before runtime or persistence models exist. The MVP operates in one workspace and distinguishes people from autonomous agents.

## Decision

`Principal` is the sole identity authority and permits only `kind=human|agent`. It carries its own identifier, display name, and `active|inactive` lifecycle. Organization, tenant, user, role, and scope fields are outside the contract and MUST be rejected.

Correlation and domain identifiers never establish identity or permission. Framework DTOs, database records, and provider types may project this schema but never replace it.

## Consequences

Consumers share a small identity vocabulary and cannot infer multitenancy or role-based authorization. A future workspace or role model is a breaking governance decision and requires a new contract major. Accepted text is superseded by a new ADR rather than silently rewritten.

## Alternatives

Organization membership, user accounts, and role-bearing principals were rejected because they introduce unapproved authority and migration semantics.

## Deferred

Workspace tenancy, memberships, roles, federation, OAuth, and JWT identity are deferred.

## Supersedes

None.

## Links

- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/shared-governance-schemas/spec.md`
- `schemas/releases/1.0.0/json-schema/domain/principal.schema.json`
