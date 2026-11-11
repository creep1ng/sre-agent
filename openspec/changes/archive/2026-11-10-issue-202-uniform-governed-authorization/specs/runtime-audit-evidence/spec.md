# Delta for Runtime Audit Evidence

## MODIFIED Requirements

### Requirement: Record every terminal attempt

The system MUST persist one terminal audit event for every governed endpoint attempt, including allow, deny, authentication/validation outcomes covered by the operation, and normalized upstream failures. Each event MUST include request correlation, principal/resource references, decision, outcome status, applicable routing references when known, and integer non-null `latency_ms`. An allowed governed operation MUST also retain protected evidence of exactly one matched active grant/policy.
(Previously: terminal events required the decision but not matched-grant evidence on allowed operations.)

#### Scenario: Allow is durably represented

- GIVEN an allowed request whose provider result normalizes successfully
- WHEN the operation reaches its terminal decision
- THEN one committed event contains allow, status 200, correlation, protected identity/routing references, the matched grant evidence, and non-negative latency

#### Scenario: Deny is durably represented without routing

- GIVEN a denied request
- WHEN the operation returns 403
- THEN one committed event contains deny and status 403, while routing and matched-grant references remain absent or not applicable

## ADDED Requirements

### Requirement: Audit evidence covers every governed operation

The four current operations (`POST /v1/responses`, `POST /v1/principals`, `GET /v1/principals`, and `GET /v1/principals/{principal_id}`) MUST use the same validation → authentication → authorization → resolution/execution → audit/release ordering. A permitted operation MUST execute once against its matched grant; a denied or invalid operation MUST make zero adapter/business/provider calls. Audit persistence MUST remain the release gate.

#### Scenario: Allowed control operation retains its grant

- GIVEN an authorized principal create, list, or get request
- WHEN the terminal audit event is committed
- THEN its protected decision evidence identifies exactly the grant that allowed execution

#### Scenario: Audit failure suppresses release

- GIVEN an otherwise allowed governed operation and an audit persistence failure
- WHEN terminal recording is attempted
- THEN no business result is released and the client receives 503 `audit_unavailable`
