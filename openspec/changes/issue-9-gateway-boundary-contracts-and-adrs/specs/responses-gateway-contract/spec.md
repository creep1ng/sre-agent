## Purpose

Non-streaming Responses authorization, routing, tracing, errors, and audit.

## ADDED Requirements

### Requirement: Textual Responses subset
`POST /v1/responses` SHALL accept required string `model` (ModelAlias), `input` of 1–65,536 UTF-8 bytes, and optional `incident_id`, `run_id`, `task_id`. Server SHALL generate `request_id`. Client `request_id`, `stream`, routing selectors, tools, unknown fields, invalid/oversized input, and malformed IDs SHALL return 422 before authorization/upstream activity.

#### Scenario: Minimal request validates
- **GIVEN** valid `model` and `input`
- **WHEN** authenticated submission occurs
- **THEN** validation accepts and server assigns `request_id`

#### Scenario: Unsupported field is supplied
- **GIVEN** unsupported field or invalid/oversized input
- **WHEN** validation runs
- **THEN** 422 returns without upstream activity

### Requirement: Non-streaming success
Success SHALL be one 200 JSON Response, never SSE/chunks, with server response ID, `status=completed`, textual assistant output only, concrete effective `model`, server `request_id`, and flat string `metadata` containing `requested_model_alias`, `router`, `inference_provider`; nested metadata SHALL NOT emit.

#### Scenario: Routed response succeeds
- **GIVEN** authorized alias and valid upstream text
- **WHEN** normalization completes
- **THEN** concrete model and three routing strings return

### Requirement: Authentication is separate
`Authorization: Bearer` SHALL authenticate into `PrincipalContext` before authorization. Missing, malformed, unknown, revoked, expired, or otherwise inactive-by-lifecycle credentials SHALL return identical 401 `authentication_failed` plus `WWW-Authenticate: Bearer`; persisted Credential status remains `active|revoked`. Authentication SHALL grant no alias permission.

#### Scenario: Credential cannot authenticate
- **GIVEN** any invalid credential condition
- **WHEN** endpoint is called
- **THEN** uniform 401 returns without alias evaluation

### Requirement: Authorize before routing without enumeration
Gateway SHALL authorize `(Principal,invoke,ModelAlias,context)` before lookup/upstream. Missing, inactive, and unauthorized aliases SHALL return identical 403 `resource_unavailable`; protected audit SHALL retain cause. Denial SHALL not route. Domain IDs SHALL be bound to Principal/context and grant no permission.

#### Scenario: Missing versus unauthorized alias
- **GIVEN** absent and unauthorized aliases
- **WHEN** equivalent requests run
- **THEN** public 403 envelopes are indistinguishable except server correlation

#### Scenario: Correlation is spoofed
- **GIVEN** domain ID not bound to Principal/context
- **WHEN** authorization runs
- **THEN** safe 403 returns before routing and audit retains cause

### Requirement: OpenRouter alias boundary
After allow, gateway SHALL resolve alias to concrete model, router, and provider policy, replacing alias before OpenRouter Responses invocation. Upstream `model` SHALL be concrete `<laboratory>/<model>`. Audit/response SHALL keep `router=openrouter` separate from effective provider. SDK objects, credentials, and upstream errors SHALL NOT cross the public boundary.

#### Scenario: Allowed alias routes
- **GIVEN** allowed active assignment
- **WHEN** upstream request forms
- **THEN** concrete model replaces logical alias

#### Scenario: Provider executes through router
- **GIVEN** OpenRouter selects a provider
- **WHEN** result normalizes
- **THEN** router and effective provider remain separate

### Requirement: Untrusted Trace Context
Gateway SHALL accept valid W3C `traceparent`, create a span, and propagate updated context under local trust/sampling limits. Missing/invalid context SHALL start a new trace, not 422. Trace/domain/request IDs SHALL remain separate and grant no authority; sensitive `tracestate` SHALL NOT propagate.

#### Scenario: Valid traceparent arrives
- **GIVEN** valid incoming `traceparent`
- **WHEN** gateway processes it
- **THEN** bounded child context propagates

#### Scenario: Invalid traceparent arrives
- **GIVEN** invalid incoming `traceparent`
- **WHEN** gateway processes it
- **THEN** a new trace starts without 422

### Requirement: Error taxonomy and audit
Every outcome SHALL emit protected AuditEvent after safe normalization/redaction. `ErrorEnvelope` SHALL map 401 authentication, 403 unavailable resource, 422 contract error, 502 malformed/unadaptable upstream, 503 unavailable/no healthy route, and 504 timeout. 401/403/422/502 SHALL be non-retryable; 503/504 retryable. `Retry-After` SHALL appear only with reliable retryable estimates. Errors SHALL omit upstream bodies/URLs, stacks, secrets, internal IDs, and denial causes.

#### Scenario: Upstream is malformed
- **GIVEN** invalid/unadaptable upstream output
- **WHEN** normalization fails
- **THEN** safe non-retryable 502 returns

#### Scenario: Upstream is unavailable
- **GIVEN** temporary outage or no healthy route
- **WHEN** invocation runs
- **THEN** retryable 503 returns with trustworthy `Retry-After` only

#### Scenario: Upstream times out
- **GIVEN** upstream deadline elapses
- **WHEN** no valid result completed
- **THEN** retryable 504 returns and timeout is audited
