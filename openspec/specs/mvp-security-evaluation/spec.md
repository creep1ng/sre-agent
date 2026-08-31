# MVP Security Evaluation Specification

## Purpose

Define a bounded MVP threat model and versioned security-evaluation catalogs. Artifacts MUST describe current evidence without implying deferred runtime protections exist.

## Requirements

### Requirement: Bounded threat model

The threat model MUST identify MVP assets, trust boundaries, current threats, mitigations, residual risks, and explicit exclusions. It MUST distinguish implemented behavior from contracted or future behavior and link authoritative ADRs/evidence rather than restating policy.

#### Scenario: Current and future maturity are explicit

- GIVEN the threat model lists authentication, authorization, resource hiding, audit, redaction, MCP, and administration concerns
- WHEN a reviewer reads each concern
- THEN each is labeled current, contracted/future, or future/non-executable with evidence or absent runtime support

### Requirement: Complete versioned demo grant matrix

`demo-grants.v1.yaml` MUST contain every seeded principal (`admin-human`, `demo-human`, `incident-harness`, `restricted-harness`), the single `llm_model/triage-agent` resource, and exactly one active `incident-harness`/`invoke` grant. Principal names MUST NOT confer roles; all other combinations MUST be denied by grant absence.

#### Scenario: Matrix represents seeded authorization

- GIVEN deterministic seeds are loaded
- WHEN the matrix is validated
- THEN all four principals and the resource are present, exactly one active grant allows incident-harness invocation, and others have no implicit allow

### Requirement: Stable scenario catalog and traceability

`scenarios.v1.yaml` MUST use stable IDs and record maturity, threat, preconditions, credential state, principal/action/resource, request shape, expected HTTP status/code, policy decision, upstream/tool call count, audit expectation, automation status, and an evidence locator. Current executable scenarios MUST have passing test locators; future scenarios MUST be non-executable.

#### Scenario: Current entries are testable

- GIVEN current Responses allow and deny paths
- WHEN catalog validation runs
- THEN each current entry has a stable ID and resolvable passing test locator with HTTP, policy, upstream, and audit expectations

#### Scenario: Deferred controls do not claim implementation

- GIVEN redaction, MCP/tool, and administrative scenarios are cataloged
- WHEN runtime capability is absent
- THEN entries remain future/non-executable and identify evidence required for later implementation

### Requirement: Non-enumerating resource denial

The resource-denial contract MUST return HTTP 403 with code `resource_unavailable` for both missing/inactive resources and existing resources without an authorized grant. Authorization MUST precede routing/provider calls, and both cases MUST expect zero upstream calls.

#### Scenario: Missing and unauthorized resources are indistinguishable

- GIVEN one request names a missing resource and another names an existing resource without a grant
- WHEN both requests execute
- THEN each returns 403 `resource_unavailable`, makes zero upstream calls, and exposes no existence distinction

### Requirement: Metadata-only audit boundary

Current audit expectations MUST specify HMAC-protected metadata, no persisted prompt/response content, append-only behavior, and suppression of result release on audit persistence failure. The threat model MUST state that no runtime redactor is implemented; redaction requirements and bounded sanitized content remain future/contractual.

#### Scenario: Audit failure fails closed

- GIVEN an otherwise allowed request and an audit persistence failure
- WHEN the response path completes
- THEN content is not released and only safe metadata expectations remain

### Requirement: Future-only MCP and administrative controls

MCP/tool authorization and administrative control-plane scenarios MUST be future-only until those runtimes exist. They MUST require exact action/resource grants, deny before execution, and forbid role inference from principal names.

#### Scenario: Future unauthorized operation

- GIVEN a future MCP/tool or administrative request without an exact grant
- WHEN its runtime is implemented and the scenario executes
- THEN it returns a non-success authorization response, performs zero tool/control-plane executions, and records safe audit evidence

### Requirement: Structural validation and drift prevention

Validation MUST parse both catalogs, enforce required fields and stable IDs, verify seed/matrix relationships and exact active-grant count, resolve evidence locators, and reject contradictory maturity or HTTP/policy expectations. It MUST run without implementing future runtimes.

#### Scenario: Catalog drift is rejected

- GIVEN a seed, catalog field, locator, or maturity label changes inconsistently
- WHEN structural validation runs
- THEN validation fails with an actionable drift error and accepts no coverage claim
