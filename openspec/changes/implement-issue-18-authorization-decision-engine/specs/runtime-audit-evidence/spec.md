# Delta for Runtime Audit Evidence

## MODIFIED Requirements

### Requirement: Record every terminal attempt

The system MUST persist one terminal audit event for every governed endpoint attempt, including allow, deny, authentication/validation outcomes covered by the operation, and normalized upstream failures. Each event MUST include the request correlation, principal/resource references, decision, outcome status, applicable routing references when known, and integer non-null `latency_ms`. For an authorization denial, governed audit evidence MUST also retain the exact internal denial cause in a dedicated audit-only attribute, separately from the public `PolicyDecision`.
(Previously: Terminal events persisted the closed policy decision and status but had no separate exact authorization-denial cause.)

#### Scenario: Allow is durably represented

- GIVEN an allowed request whose provider result normalizes successfully
- WHEN the operation reaches its terminal decision
- THEN one committed event contains allow, status 200, correlation, protected identity/routing references, and non-negative latency

#### Scenario: Deny is durably represented without routing

- GIVEN a denied request
- WHEN the operation returns 403
- THEN one committed event contains deny and status 403, the exact internal cause, and no routing references

## ADDED Requirements

### Requirement: Isolate exact denial causes to governed audit

The audit contract and persistence MUST store the bounded causes `principal_inactive`, `resource_missing`, `resource_inactive`, and `grant_not_applicable` only in the dedicated audit denial-cause attribute. They MUST NOT overload, widen, or reinterpret public `PolicyDecision.reason_code`; API responses and ordinary operational logs MUST remain `deny/no_matching_grant/null`.

#### Scenario: Audit readback preserves the exact cause

- GIVEN a denied request with a known precedence winner
- WHEN governed audit evidence is read back
- THEN it contains that one cause and the public decision remains `deny/no_matching_grant/null`

#### Scenario: Non-audit projections omit the cause

- GIVEN a denied request with any internal cause
- WHEN an API response or ordinary operational log is produced
- THEN it contains no internal cause, grant enumeration, or resource-state distinction
