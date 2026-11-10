# Delta for Governed LLM Responses

## MODIFIED Requirements

### Requirement: Authorize before routing and invocation

The operation MUST obtain authorization-safe Principal, logical-resource, and grant facts through the reusable authorization decision engine before resolving any alias, provider, or routing assignment. A deny MUST return the uniform 403 `resource_unavailable`, MUST NOT resolve an alias or provider, and MUST NOT make an upstream call.
(Previously: The gateway checked authorization-safe resource state and grant applicability before routing, but did not require the reusable engine as the sole decision authority.)

#### Scenario: Restricted principal has no upstream traffic

- GIVEN `restricted-harness` has no applicable `invoke` grant
- WHEN it submits an otherwise valid request
- THEN the engine returns deny, the operation returns 403 `resource_unavailable`, the upstream call count remains zero, and a deny attempt is recorded

#### Scenario: Missing or inactive resource is indistinguishable

- GIVEN the requested logical resource is missing or unavailable
- WHEN an authenticated principal submits the request
- THEN the engine returns deny, the operation returns the same 403 `resource_unavailable` without routing or upstream traffic

#### Scenario: Inactive Principal is denied before routing

- GIVEN an authenticated context whose Principal is inactive
- WHEN it submits an otherwise valid request
- THEN the engine denies before routing, the operation returns 403 `resource_unavailable`, and no provider or routing data is accessed

## ADDED Requirements

### Requirement: Preserve one authorization authority for Responses

The Responses consumer MUST pass its authorization facts to the reusable engine and MUST use its `PolicyDecision` unchanged for allow/deny behavior. It MUST NOT infer roles, scopes, or policy from request fields, routing assignments, YAML catalogs, or provider state.

#### Scenario: Allowed request routes only after engine allow

- GIVEN an active Principal, active logical resource, and exact active `invoke` grant
- WHEN the engine returns allow
- THEN routing resolves one assignment and only then may one upstream call occur

#### Scenario: Denied request cannot reveal topology

- GIVEN an inactive resource or inapplicable grant
- WHEN the engine returns deny
- THEN the response remains uniform 403 and neither alias/provider identity nor upstream data is exposed
