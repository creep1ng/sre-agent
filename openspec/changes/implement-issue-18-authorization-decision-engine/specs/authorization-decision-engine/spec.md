# Authorization Decision Engine Specification

## Purpose

Define one reusable, framework- and persistence-independent authority for direct Principal–action–resource authorization. The engine preserves the closed public decision contract while making exact denial causes available only to governed audit projection.

## Requirements

### Requirement: Authorize generic governed resources

The engine MUST accept an authenticated `Principal`, an action, and an exact `resource_type/resource_id` identity for every existing governed artifact. Credentials, display names, model aliases, routing data, and evidence catalogs MUST NOT be policy inputs.

#### Scenario: Same rule applies across resource types

- GIVEN an active Principal and an exact active direct grant for a governed resource
- WHEN the engine evaluates `invoke` for any supported resource type
- THEN it returns `allow/grant_matched/<grant_id>` using the same rules

### Requirement: Apply deterministic denial precedence

The engine MUST short-circuit to one internal denial cause in this order: `principal_inactive`, `resource_missing`, `resource_inactive`, `grant_not_applicable`. A later fact MUST NOT replace an earlier cause.

#### Scenario: Inactive Principal takes precedence

- GIVEN an inactive Principal, a missing resource, and a matching grant record
- WHEN authorization is evaluated
- THEN the internal cause is `principal_inactive` and no grant decision is considered

#### Scenario: Resource state precedes grant applicability

- GIVEN an active Principal and a missing or inactive resource with a matching grant
- WHEN authorization is evaluated
- THEN the internal cause is `resource_missing` or `resource_inactive` respectively

### Requirement: Allow only an exact active direct grant

The engine MUST allow only when the Principal and resource are active and one active `allow` grant exactly matches principal, action, resource type, and resource ID. Every absent, revoked, mismatched, or otherwise inapplicable grant MUST deny as `deny/no_matching_grant/null`.

#### Scenario: Exact active grant allows

- GIVEN active Principal and resource facts and one exact active allow grant
- WHEN authorization is evaluated
- THEN the decision is `allow/grant_matched` and `policy_id` is that grant ID

#### Scenario: Revoked or mismatched grant denies

- GIVEN active Principal and resource facts but no exact active allow grant
- WHEN authorization is evaluated
- THEN the decision is `deny/no_matching_grant/null` with cause `grant_not_applicable`

### Requirement: Keep diagnostics and authority bounded

Public decisions, API responses, and ordinary operational logs MUST expose only the closed deny result. Exact internal denial causes MAY appear only in governed audit evidence. Persistence MUST return Principal, resource, and grant facts; this engine MUST be the sole constructor of runtime `PolicyDecision` and MUST NOT add roles, scopes, explicit denies, conditions, groups, tenancy, YAML runtime policy, or external policy engines.

#### Scenario: Denial details do not leak

- GIVEN any denied authorization evaluation
- WHEN its result is returned or logged outside governed audit projection
- THEN observers see only `deny/no_matching_grant/null` and no internal cause

#### Scenario: No second decision authority

- GIVEN persistence has returned authorization facts
- WHEN a consumer requests a runtime decision
- THEN it invokes this engine and no persistence method independently constructs policy decisions
