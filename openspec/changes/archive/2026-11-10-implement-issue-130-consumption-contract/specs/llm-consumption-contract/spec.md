# LLM Consumption Contract Specification

## Purpose

Define the portable token and billed-cost projection published by release `2.1.0` for downstream consumption without exposing prompts, output, credentials, or provider bodies.

## ADDED Requirements

### Requirement: Immutable 2.1.0 contract

The service MUST publish a complete `/v1` release `2.1.0` based on `2.0.0` and MUST leave every `2.0.0` artifact byte-identical. The contract MUST define one closed `consumption` object with `availability` (`complete|partial|absent|unavailable`), `source`, non-negative nullable `input_tokens`, `output_tokens`, and `total_tokens`, nullable exact-decimal `billed_usd`, nullable `currency`, `precision`, and `pricing_context`. Unknown fields MUST be rejected.

#### Scenario: Additive release preserves baseline

- GIVEN the published `2.0.0` snapshot
- WHEN `2.1.0` is generated and validated
- THEN all `2.0.0` bytes remain unchanged and the new snapshot validates

#### Scenario: Closed projection rejects drift

- GIVEN a consumption object with an unknown field or negative token count
- WHEN the contract validator runs
- THEN validation fails without coercing the value

### Requirement: Authoritative provider evidence

The adapter MUST use validated OpenRouter response `usage` as the sole authority for token and billed-cost values. `billed_usd` MUST be the provider-reported exact USD decimal with provider observation time and price snapshot/version in `pricing_context`; estimated, rounded, inferred, or text-derived values MUST NOT be emitted.

#### Scenario: Complete usage and billing are normalized

- GIVEN a completed response with valid provider usage and billed USD evidence
- WHEN adaptation runs
- THEN the projection records the evidence source, exact decimal cost, pricing context, and token values

#### Scenario: Partial or malformed evidence is explicit

- GIVEN usage or cost evidence is partial, contradictory, or invalid
- WHEN adaptation runs
- THEN availability is `partial` when valid dimensions remain or `unavailable` when evidence is invalid, missing dimensions remain null, and no zero is inferred

### Requirement: Token and outcome semantics

When all three token values are present, `total_tokens` MUST equal `input_tokens + output_tokens`; missing values MUST remain missing. A completed response without evidence is `absent`. Timeout, upstream error, cache, or fallback without explicit provider evidence is `unavailable`; explicit evidence MAY produce `complete` or `partial`. Pre-routing denial has no provider consumption.

#### Scenario: Successful response has no usage

- GIVEN an authorized provider completion with no usage fields
- WHEN the projection is created
- THEN availability is `absent` and every unavailable value remains null

#### Scenario: Failure does not become zero

- GIVEN a timeout, error, cache result, or fallback result without provider evidence
- WHEN outcome metadata is normalized
- THEN availability is `unavailable` and no token or cost value is synthesized

### Requirement: Shared safe projection

Public response metadata and persisted audit metadata MUST use the same normalized projection. The projection MUST contain metadata only; raw provider bodies, prompts, output, URLs, and credentials MUST NOT be exposed or persisted. Persistence and reconstruction MUST preserve nulls, availability, exact decimal text, and pricing context.

#### Scenario: Response and audit agree

- GIVEN an authorized completion with valid evidence
- WHEN public and audit projections are produced
- THEN their consumption values are equal and neither contains provider body content

#### Scenario: Denial remains consumption-free

- GIVEN a request denied before routing
- WHEN its outcome is recorded
- THEN no upstream consumption is claimed and no zero-valued projection is added

### Requirement: Deterministic conformance coverage

The `2.1.0` release MUST include schemas, examples, positive/negative fixtures, and conformance checks for complete, partial, absent, unavailable, invalid-evidence, deny, timeout, error, cache, and fallback semantics. Checks MUST verify `2.0.0` immutability and MUST NOT use provider secrets or raw bodies.

#### Scenario: Contract fixtures cover every state

- GIVEN the versioned fixture suite
- WHEN release validation runs
- THEN every listed availability and outcome state has an explicit passing or rejecting fixture
