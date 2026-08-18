# ADR-003: API-key authentication boundary

- **Status:** Accepted
- **Contract version:** 1.0.0

## Context

The gateway needs a technology-independent credential boundary that authenticates one Principal without making a raw secret part of shared or persistent representations.

## Decision

Bearer API keys authenticate into `PrincipalContext`, which binds the resolved Principal to a safe credential identifier. `CredentialReference` exposes only credential ID, Principal ID, non-secret prefix, `active|revoked` status, and lifecycle timestamps.

Raw keys and `Authorization` MUST NOT appear in Principal, CredentialReference, PrincipalContext, lists, replay, storage projections, audit, or errors. Storage may retain only a one-way hash. A dedicated successful issuance or bootstrap response may reveal one raw key exactly once; replay omits the key and reports `secret_revealed=false`.

## Consequences

Shared contracts remain safe to serialize and inspect. Rotation and first-issuance response behavior require dedicated HTTP schemas in the control-plane slice. Accepted text is superseded by a new ADR rather than silently rewritten.

## Alternatives

Persisting recoverable keys, embedding Authorization, JWT, OAuth, and framework security models were rejected for the initial contract.

## Deferred

Hash algorithm selection, secret-store implementation, rotation transactions, and authentication runtime are deferred to owning consumers.

## Supersedes

None.

## Links

- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/shared-governance-schemas/spec.md`
- `schemas/releases/1.0.0/json-schema/domain/credential-reference.schema.json`
- `schemas/releases/1.0.0/json-schema/domain/principal-context.schema.json`
