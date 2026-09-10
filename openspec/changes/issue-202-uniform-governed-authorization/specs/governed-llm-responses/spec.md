# Delta for Governed LLM Responses

## MODIFIED Requirements

### Requirement: Ordered, correlated request handling

The operation MUST assign one server-controlled `request_id` and process validation, credential authentication, authorization, logical resource resolution, routing, upstream invocation, normalization, and terminal recording in that order. It MUST derive the Principal from the credential and keep action and resource type server-owned; client input MAY supply only the validated logical model identifier.
(Previously: logical lookup was listed before authorization and did not require credential-derived identity or explicit server-owned scope fields.)

#### Scenario: Invalid request is rejected before routing

- GIVEN a malformed or unsupported HT-01 request
- WHEN the request is submitted
- THEN the operation returns the contract validation status, commits terminal metadata, and performs no authentication, authorization, routing, or upstream call

#### Scenario: Authenticated allow reaches routing only after authorization

- GIVEN a valid request and a credential resolving to a Principal with an active exact `invoke` grant for `llm_model` and the validated `body.model`
- WHEN the operation handles the request
- THEN it resolves routing and invokes the provider only after allow, using one assigned `request_id`

### Requirement: Authorize before routing and invocation

The operation MUST read only authorization-safe logical resource state before the grant decision. A deny MUST return uniform non-enumerating 403 `resource_unavailable`, MUST NOT resolve an alias or provider, and MUST NOT call an upstream or business adapter.
(Previously: the requirement covered routing/provider denial but did not explicitly forbid business-adapter effects.)

#### Scenario: Restricted principal has no upstream traffic

- GIVEN `restricted-harness` has no applicable `invoke` grant
- WHEN it submits an otherwise valid request
- THEN it receives 403 `resource_unavailable`, provider and adapter call counts remain zero, and a deny attempt is recorded

#### Scenario: Missing or inactive resource is indistinguishable

- GIVEN the requested logical resource is missing or unavailable
- WHEN an authenticated Principal submits the request
- THEN the operation returns the same 403 `resource_unavailable` without routing, adapter, or upstream traffic

## ADDED Requirements

### Requirement: Bearer and governed-route contract

The runtime route MUST declare Bearer security with 401/403 outcomes and governed-scope metadata. A valid request MUST use the existing grant inventory; no grant provisioning, seeds, migrations, schema, or lifecycle changes are introduced.

#### Scenario: Runtime contract exposes security

- GIVEN the composed Responses route
- WHEN its runtime contract is inspected
- THEN Bearer security and 401/403 responses are declared

#### Scenario: Invalid credentials fail before effects

- GIVEN a valid request with a missing, malformed, unknown, inactive, or revoked Bearer credential
- WHEN the operation executes
- THEN it returns 401 `authentication_failed` and makes zero authorization, routing, adapter, or upstream effects
