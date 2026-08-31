# Runtime Audit Evidence Specification

## Purpose

Define durable, metadata-only evidence for every governed response attempt and the release gate that prevents an outcome from escaping before its terminal audit state is accepted.

## Requirements

### Requirement: Record every terminal attempt

The system MUST persist one terminal audit event for every governed endpoint attempt, including allow, deny, authentication/validation outcomes covered by the operation, and normalized upstream failures. Each event MUST include the request correlation, principal/resource references, decision, outcome status, applicable routing references when known, and integer non-null `latency_ms`.

#### Scenario: Allow is durably represented

- GIVEN an allowed request whose provider result normalizes successfully
- WHEN the operation reaches its terminal decision
- THEN one committed event contains allow, status 200, correlation, protected identity/routing references, and non-negative latency

#### Scenario: Deny is durably represented without routing

- GIVEN a denied request
- WHEN the operation returns 403
- THEN one committed event contains deny and status 403, while routing references remain absent or not applicable

### Requirement: Project metadata safely

Audit evidence MUST be metadata-only. It MUST NOT persist or log prompts, model output, provider bodies, bearer credentials, or provider secrets. Source identifiers for principal, resource, grant/policy, alias, model, and provider MUST be represented by the approved HMAC projections; raw identifiers MUST NOT be exposed in the audit projection.

#### Scenario: Redaction and HMAC projection

- GIVEN an event containing source identifiers and sensitive request/provider data
- WHEN the audit projection is created
- THEN only approved HMAC references and non-sensitive metadata are persisted, and a readback contains none of the sensitive values

### Requirement: Audit acceptance gates release

The operation MUST commit the terminal audit event before releasing a 200, 403, or normalized provider error. If the audit store cannot accept the event, the operation MUST suppress the intended result and return safe retryable 503 `audit_unavailable`; it MUST NOT claim success or silently continue.

#### Scenario: Audit failure suppresses success

- GIVEN an otherwise successful allowed provider result
- WHEN terminal audit commit fails
- THEN the client receives 503 `audit_unavailable` and no 200 response is released

#### Scenario: Audit failure suppresses denial

- GIVEN a denied request
- WHEN its deny event cannot be committed
- THEN the client receives 503 `audit_unavailable` rather than 403

### Requirement: Preserve request and transaction boundaries

The system MUST measure latency from request entry through terminal decision/normalization, MUST close governance reads before upstream I/O, and MUST perform terminal audit persistence in a short transaction. It MUST NOT hold a database transaction open across the network call.

#### Scenario: Latency and ordering are durable

- GIVEN a request with a bounded provider delay
- WHEN the terminal event is committed
- THEN `latency_ms` is a non-negative integer covering the operation and the event is committed before the response is released

#### Scenario: Provider call does not hold governance transaction

- GIVEN an allowed request requiring one upstream call
- WHEN the provider is in flight
- THEN no governance read transaction remains open, and the terminal audit transaction begins only after normalization

### Requirement: Verify durability and redaction deterministically

PostgreSQL-backed deterministic tests MUST assert event counts, fields, redaction/HMAC projections, release gating, and latency for allow, deny, and failure paths. A live smoke, when enabled, MUST assert only protected audit dimensions and MUST NOT require raw audit inspection.

#### Scenario: Deterministic audit readback

- GIVEN a recording provider and a real test database
- WHEN allow, deny, and provider-failure cases execute
- THEN each has exactly one terminal event with the required status, latency, and protected fields
