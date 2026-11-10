# Delta for Runtime Audit Evidence

## MODIFIED Requirements

### Requirement: Project metadata safely

Audit evidence MUST be metadata-only. It MUST NOT persist or log prompts, model output, provider bodies, bearer credentials, or provider secrets. Source identifiers for principal, resource, grant/policy, alias, model, and provider MUST be represented by the approved HMAC projections; raw identifiers MUST NOT be exposed in the audit projection. A consumption projection MUST use the LLM Consumption Contract's normalized values and MUST NOT add provider content.
(Previously: metadata-only audit projected identity and routing references but had no consumption projection.)

#### Scenario: Redaction and HMAC projection

- GIVEN an event containing source identifiers, sensitive request/provider data, and normalized consumption
- WHEN the audit projection is created
- THEN only approved HMAC references and non-sensitive consumption metadata are persisted, and readback contains none of the sensitive values

## ADDED Requirements

### Requirement: Persist optional consumption evidence without weakening gates

The system MUST persist and reconstruct the optional normalized consumption projection for authorized provider outcomes, preserving availability, nulls, exact decimal `billed_usd`, and pricing context. Denial MUST remain consumption-free; append-only storage, audit-before-release, and existing terminal-event cardinality MUST remain unchanged.

#### Scenario: Consumption round-trips safely

- GIVEN an authorized completion with complete or partial provider evidence
- WHEN its terminal audit event is persisted and read back
- THEN the consumption projection is identical, metadata-only, and protected by existing audit controls

#### Scenario: Unavailable evidence stays explicit

- GIVEN timeout, error, cache, fallback, or invalid evidence without a valid provider projection
- WHEN the terminal event is recorded
- THEN it stores `unavailable` without zero inference or raw body content

#### Scenario: Audit failure still suppresses release

- GIVEN an otherwise successful response carrying consumption metadata
- WHEN terminal audit commit fails
- THEN the client receives retryable 503 `audit_unavailable` and no response is released
