# Control-Plane Principals + Credentials Specification

## Purpose

Define the complete eight-route administrative lifecycle for issue #147 on immutable
contract 2.0.0. The 1.4.0 snapshot remains exactly published; `/v1` remains the API
path. 2.0.0 is a complete snapshot and does not promise the old status body.

## Requirements

### Requirement: Immutable major contract

The service MUST publish `schemas/releases/2.0.0/` as a full release snapshot.
Unchanged 1.4.0 artifacts MUST be byte-identical copies. The status-replace body
MUST require `status` and `expected_updated_at`; this breaking change MUST NOT
modify 1.4.0.

#### Scenario: Missing concurrency token
- GIVEN a 2.0.0 status request without `expected_updated_at`
- WHEN it is authenticated and validated
- THEN it is rejected with 422 and no status mutation

### Requirement: Principal lifecycle

The service MUST expose `POST /v1/principals` (201), `GET /v1/principals` (200,
bounded `(created_at,id)` ascending), `GET /v1/principals/{id}` (200/404), and
`PUT /v1/principals/{id}/status` (200/409) over closed bodies. Create REQUIRES a
16-128 ASCII `Idempotency-Key`. Status replace MUST use atomic database
compare-and-swap (or equivalently locked conditional update) on
`expected_updated_at`: exactly one simultaneous writer MAY transition and stale
writers MUST return 409 `status_conflict` without overwrite.

#### Scenario: Create then replay
- GIVEN a created principal and retained idempotency binding
- WHEN the same key and payload repeat
- THEN 201 returns the same principal with no second row or transition

#### Scenario: Simultaneous status writers
- GIVEN two writers holding the same original timestamp
- WHEN both replace status concurrently
- THEN one succeeds, one returns 409, and the stored winner remains intact

#### Scenario: Hidden principal is probed
- GIVEN an absent ID or a principal the operator may not see
- WHEN `GET /v1/principals/{id}` runs
- THEN identical 404 `resource_not_found` returns with no existence signal

### Requirement: Credential lifecycle and secrecy

The service MUST expose issue, list, revoke, and rotation at the four credential
routes. Issuance reveals one key exactly once (`secret_revealed=true`); replay,
list, readback, audit, and logs MUST omit keys/hashes (`secret_revealed=false` on
replay). Lists are bounded to 100 and reject continuation parameters. Revocation
converges (repeat DELETE -> 204, no transition) and blocks later authentication.
Rotation MUST lock and accept only an active credential, revoke it and create one
replacement in one transaction, and roll back to active on issuance failure.
Inactive rotation MUST not mint a replacement.

#### Scenario: Rotation replay
- GIVEN a completed rotation binding
- WHEN the same key and payload repeat
- THEN stored replacement IDs return without a key or second credential

#### Scenario: Rotation failure preserves service
- GIVEN replacement issuance fails
- WHEN rotation ends
- THEN the old credential is active with `result=failure`,
  `replacement_count=0`, and `transition_count=0`

#### Scenario: Revoked credential cannot authenticate
- GIVEN a revoked credential
- WHEN its key is presented
- THEN authentication fails uniformly with 401 and no reason distinction

### Requirement: Idempotency and bounded lists

Mutating POST bindings MUST scope by operator, method, canonical path/IDs, and key
digest, and bind canonical payload hash. `at_least_24h` bindings MUST store expiry
at least 24 hours after creation; `principal_lifetime` bindings MUST store no
expiry. Same hash replays stored outcome without transition; a different hash
returns 409 `idempotency_conflict` without mutation.

#### Scenario: Payload conflict
- GIVEN a retained binding for key K and hash H1
- WHEN K arrives with H2
- THEN 409 returns and nothing mutates

### Requirement: Authentication and engine-delegated authorization

Every control route MUST authenticate FIRST, including malformed body, query, path,
or idempotency key. Authentication failure MUST return uniform 401 before validation.
After successful authentication and validation, every operation MUST call
`AuthorizationDecisionEngine.evaluate()` with the owner-approved exact tuple
(`admin.read|admin.write`, `administrative_control`, `principals|credentials`)
BEFORE target principal/credential lookup or mutation. Denied reads MUST be 404 and
denied mutations 403 without public cause/existence leakage; no route or repository
may construct parallel allow/deny rules.

#### Scenario: Unauthorized operator is blind
- GIVEN an authenticated operator without an exact control grant
- WHEN any control operation runs
- THEN engine denial precedes target access and returns uniform 403/404

### Requirement: Administrative resources and bootstrap grants

`administrative_control/principals` and `administrative_control/credentials` MUST
be active persisted resources. Additive offline bootstrap convergence MUST retain
existing seed behavior while creating missing control resources and `admin.read` /
`admin.write` grants for `admin-human`; it MUST NOT become an HTTP bypass.

#### Scenario: Bootstrap grants gate administration
- GIVEN converged control resources and `admin-human` grants
- WHEN `admin-human` calls a matching control route
- THEN the engine allows via the exact persisted grant

### Requirement: Metadata-only terminal audit

Every terminal attempt MUST append metadata-only evidence before its public result;
audit rejection MUST suppress ordinary output and return retryable 503
audit_unavailable. Validation and 401 evidence MUST NOT require identity, resource,
or policy decision. Successful authenticated operations MUST record
`stage=authorization` with identity, `administrative_control` resource, and policy
decision metadata. Denied operations MUST retain the exact cause only in audit
(including hidden-read 404) and never in the public envelope; the 2.0.0 audit
schema/fixtures MUST validate that shape. Secrets/hashes remain forbidden.

#### Scenario: Audit store rejects
- GIVEN an otherwise terminal control operation
- WHEN audit append fails
- THEN the client receives 503 `audit_unavailable` and no ordinary payload
