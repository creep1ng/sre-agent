# Control-Plane Principals + Credentials Specification

## Purpose

Define the administrative HTTP lifecycle for Principals and credentials over the
immutable 1.4.0 control-plane contract. Every operation is authenticated,
idempotent where mutating via POST, concurrency-safe on status replace, audited
metadata-only, secret-safe, and authorized solely by the reusable decision engine.

## Requirements

### Requirement: Principal lifecycle

The service MUST expose `POST /v1/principals` (201), `GET /v1/principals` (200,
bounded, `(created_at,id)` ascending), `GET /v1/principals/{id}` (200/404), and
`PUT /v1/principals/{id}/status` (200) over closed bodies. `POST` REQUIRES a
16-128 ASCII `Idempotency-Key`. Status replace REQUIRES `expected_updated_at`
and MUST return 409 `status_conflict` on mismatch without mutation.

#### Scenario: Create then replay

- GIVEN a created principal and its retained idempotency binding
- WHEN the same key + payload repeats
- THEN 201 returns the same principal with no second row or transition

#### Scenario: Stale concurrent write

- GIVEN a principal with `updated_at=T2` after a concurrent update
- WHEN a writer sends `expected_updated_at=T1`
- THEN 409 `status_conflict` returns and stored status remains at the newer value

#### Scenario: Hidden principal is probed

- GIVEN an absent ID or one the operator is not permitted to see
- WHEN `GET /v1/principals/{id}` runs
- THEN identical 404 `resource_not_found` returns with no existence signal

### Requirement: Credential lifecycle and secrecy

Issuance MUST reveal one key exactly once (`secret_revealed=true`); replay, list,
readback, audit, and logs MUST omit keys/hashes (`secret_revealed=false` on
replay). Rotation MUST atomically revoke the old credential and create exactly
one replacement; failure MUST leave the old credential active with
`result=failure`, `replacement_count=0`, `transition_count=0`. Revocation MUST
converge (`DELETE` repeats -> 204, no transition) and block later authentication.

#### Scenario: Rotation replay

- GIVEN a completed rotation binding
- WHEN the same key + payload repeats
- THEN the stored replacement IDs return with no key and no second credential

#### Scenario: Rotation failure preserves service

- GIVEN a rotation whose replacement issue fails
- WHEN the operation ends
- THEN the old credential remains active and no replacement exists

#### Scenario: Revoked credential cannot authenticate

- GIVEN a revoked credential
- WHEN its key is presented
- THEN authentication fails uniformly (401) with no reason distinction

### Requirement: Idempotency and bounded lists

Mutating POST MUST scope bindings by (operator, method, canonical path + IDs,
key digest) bound to the canonical payload hash for >= 24h (credential bindings
for principal lifetime). Same hash replays; different hash -> 409
`idempotency_conflict` without mutation. Lists MUST reject
`cursor|page|offset|continuation_token|next`, default/max `limit=100`, and carry
`truncated` with no continuation.

#### Scenario: Payload conflict

- GIVEN a retained binding for key K + hash H1
- WHEN key K arrives with hash H2
- THEN 409 returns and nothing mutates

### Requirement: Engine-delegated authorization

Every control operation MUST authenticate first (401 uniform), then call
`AuthorizationDecisionEngine.evaluate()` with the operator principal BEFORE any
target principal/credential lookup or mutation, using
(`admin.read` for reads, `admin.write` for creation/update/revocation/rotation,
`administrative_control`, `principals|credentials`) per owner decision on #147.
Deny MUST skip target access, return uniform 403 `resource_unavailable` for
mutations (404 `resource_not_found` for hidden reads) with no existence or cause
leakage, and record the exact cause only in governed audit evidence per #154.
No route or repository may construct its own allow/deny.

#### Scenario: Unauthorized operator is blind

- GIVEN an authenticated operator with no exact control grant
- WHEN any control operation runs
- THEN no principal/credential data returns and the response is uniform 403/404

### Requirement: Administrative resources and bootstrap grants

`administrative_control/principals` and `administrative_control/credentials`
MUST exist as active persisted resources. The offline bootstrap (`seeds.py`)
MUST create the first administrator, both resources, and `admin.read` /
`admin.write` grants. Seeds MUST NOT serve as an HTTP bypass.

#### Scenario: Bootstrap grants gate administration

- GIVEN seeded `administrative_control/*` resources and `admin-human` grants
- WHEN `admin-human` calls a control route with the matching action
- THEN the engine allows via the exact persisted grant

### Requirement: Metadata-only terminal audit

Every terminal attempt MUST append one metadata-only audit event (stage `audit`,
`content_state=absent`, HMAC refs only) before releasing its ordinary result.
Audit rejection MUST suppress the result and return 503 `audit_unavailable`
with `retryable=true`. Audit reads MUST remain metadata-only; content params ->
422.

#### Scenario: Audit store rejects

- GIVEN an otherwise successful control operation
- WHEN the audit append fails
- THEN the client receives 503 `audit_unavailable` and no ordinary payload
