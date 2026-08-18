# ADR-004: Direct grants and default deny

- **Status:** Accepted
- **Contract version:** 1.0.0

## Context

Consumers require one authorization decision model without selecting a policy engine or coupling permission to model routing.

## Decision

`Grant` represents one direct `allow` from a Principal and action to a Resource. Grant lifecycle is `active|revoked`; only an active matching Grant participates in allow. Grant data MUST NOT contain model assignment, router, provider, organization, tenant, role, or scope authority.

`PolicyDecision` is engine-independent. A matched active Grant returns `allow`, `grant_matched`, and that Grant identifier as `policy_id`. No match returns `deny`, `no_matching_grant`, and `policy_id=null`. Authorization completes before model routing.

## Consequences

Absence is an explicit default deny, persisted identifiers identify only the Grant that caused allow, and routing remains independently replaceable. Accepted text is superseded by a new ADR rather than silently rewritten.

## Alternatives

Embedded routing policy, role-based grants, deny rules, OPA, Casbin, and provider-specific policy objects were rejected for this contract version.

## Deferred

Policy engine selection, condition languages, delegation, hierarchical resources, and explicit deny rules are deferred.

## Supersedes

None.

## Links

- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/shared-governance-schemas/spec.md`
- `schemas/releases/1.0.0/json-schema/domain/grant.schema.json`
- `schemas/releases/1.0.0/json-schema/domain/policy-decision.schema.json`
