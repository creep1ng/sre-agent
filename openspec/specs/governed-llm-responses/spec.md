# Governed LLM Responses Specification

## Purpose

Define the HT-01 non-streaming text-only response operation for governed principals. The operation must decide access before revealing routing information or contacting an upstream provider, and must expose only normalized contract outcomes.

## Requirements

### Requirement: Ordered, correlated request handling

The operation MUST assign one server-controlled `request_id` and process validation, authentication, logical resource lookup, authorization, routing, upstream invocation, normalization, and terminal recording in that order. It MUST NOT accept client-supplied routing or provider identity.

#### Scenario: Invalid request is rejected before routing

- GIVEN a malformed or unsupported HT-01 request
- WHEN the request is submitted
- THEN the operation returns the contract validation status, commits its terminal metadata event, and performs no routing or upstream call

#### Scenario: Authenticated allow reaches routing only after authorization

- GIVEN a valid request and an authenticated principal with an active `invoke` grant
- WHEN the operation handles the request
- THEN it resolves routing only after the grant decision is allow and uses the assigned `request_id` throughout

### Requirement: Authorize before routing and invocation

The operation MUST read only authorization-safe logical resource state before the grant decision. A deny MUST return the uniform 403 `resource_unavailable`, MUST NOT resolve an alias or provider, and MUST NOT make an upstream call.

#### Scenario: Restricted principal has no upstream traffic

- GIVEN `restricted-harness` has no applicable `invoke` grant
- WHEN it submits an otherwise valid request
- THEN it receives 403 `resource_unavailable`, the upstream call count remains zero, and a deny attempt is recorded

#### Scenario: Missing or inactive resource is indistinguishable

- GIVEN the requested logical resource is missing or unavailable
- WHEN an authenticated principal submits the request
- THEN the operation returns the same 403 `resource_unavailable` without routing or upstream traffic

### Requirement: Resolve bounded routing evidence after allow

After allow, the operation MUST resolve the active alias to one concrete model and configured provider, request that provider without fallback, and accept success only when evidence identifies exactly that selected provider. Missing, malformed, contradictory, or extra-provider evidence MUST be rejected.

#### Scenario: Alias resolves and evidence agrees

- GIVEN an allowed principal and an active alias mapped to one model/provider
- WHEN the provider returns valid text and exactly matching selected-provider evidence
- THEN the operation returns a normalized HT-01 non-streaming response

#### Scenario: Provider evidence is invalid

- GIVEN an allowed principal and a provider response with absent or contradictory routing evidence
- WHEN the response is normalized
- THEN the operation returns non-retryable 502 `provider_evidence_invalid` and performs no fallback call

### Requirement: Normalize provider outcomes without hidden retries

The operation MUST make at most one upstream request. It MUST map timeout to 504, temporary transport/availability failure to 503, and unadaptable provider success or error bodies to 502, using only bounded validated retry metadata when exposed.

#### Scenario: Upstream failure taxonomy is stable

- GIVEN an allowed request and one of the defined provider failure classes
- WHEN the provider attempt completes
- THEN the gateway returns the corresponding HT-01 status/error shape and makes no second attempt

### Requirement: Verification is deterministic with optional live smoke

The conformance suite MUST prove allow, ordering, normalized failures, and deny zero-call behavior with a recording provider. A separately named live smoke MAY run one bounded request only when an operator-supplied provider secret is present; it MUST be skipped otherwise and MUST NOT be required for ordinary CI.

#### Scenario: Recording adapter proves deny behavior

- GIVEN a deterministic provider double and a restricted principal
- WHEN the contract test submits the request
- THEN the test observes zero provider calls and the committed 403 outcome

#### Scenario: Secret-gated live smoke

- GIVEN the live-smoke secret is present
- WHEN one non-streaming request is sent through the complete gateway
- THEN the test asserts only normalized response and protected metadata, never provider bodies or secrets
