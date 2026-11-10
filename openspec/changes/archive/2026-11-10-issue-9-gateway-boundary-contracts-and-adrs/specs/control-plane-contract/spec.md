## Purpose

Defines bounded `/v1` governance for identity, aliases, grants, audit, and bootstrap.

## ADDED Requirements

### Requirement: Control-plane matrix
The control plane SHALL expose:

| Resource | Operations |
|---|---|
| Principal | `POST /v1/principals` 201; `GET /v1/principals/{id}` 200; `GET /v1/principals` 200; `PUT /v1/principals/{id}/status` 200 |
| Credential | `POST /v1/principals/{id}/credentials` 201; `GET /v1/principals/{id}/credentials` 200; `DELETE /v1/credentials/{id}` 204; `POST /v1/credentials/{id}/rotation` 201 |
| ModelAlias | `POST /v1/model-aliases` 201; `GET /v1/model-aliases/{id}` 200; `GET /v1/model-aliases` 200; `PUT /v1/model-aliases/{id}/assignment` 200; `PUT /v1/model-aliases/{id}/status` 200 |
| Grant | `POST /v1/grants` 201; `GET /v1/grants` 200; `DELETE /v1/grants/{id}` 204 |
| Audit | `GET /v1/audit-events/{id}` 200; `GET /v1/audit-events` 200 |

Principal and ModelAlias status SHALL be `active|inactive`; Credential and Grant status SHALL be `active|revoked`. Only active Grants SHALL participate in allow; DELETE of a Credential or Grant SHALL converge on `revoked`. Assignment SHALL separate alias/model/router/provider. Grants SHALL be direct `allow`.

#### Scenario: Matrix operation succeeds
- **GIVEN** valid authorized input
- **WHEN** a listed operation runs
- **THEN** listed status/semantics return

### Requirement: Bounded non-paginated lists
Lists SHALL reject `cursor|page|offset|continuation_token|next`. `limit` SHALL default/max at 100. Principal/ModelAlias SHALL sort `(created_at,id)` ascending; Credential/Grant descending. Grant queries SHALL require `principal_id|resource_id`. Audit queries SHALL require Principal, decision, alias, request/domain/trace ID, or bounded time; sort SHALL be `(occurred_at,event_id)` descending. Truncation SHALL have no continuation.

#### Scenario: Unsafe collection query
- **GIVEN** unfiltered Grant/audit or `limit=101`
- **WHEN** validated
- **THEN** 422 returns

#### Scenario: Result exceeds limit
- **GIVEN** excess matches
- **WHEN** listed
- **THEN** bounded deterministic results have no continuation

### Requirement: POST idempotency
Mutating POST SHALL require a 16–128 ASCII `Idempotency-Key`. Scope SHALL combine Principal, method, canonical path/IDs, and key, bound to canonical payload hash for at least 24 hours; credential bindings SHALL last for Principal lifetime. Same hash SHALL replay status/resource without transition; another SHALL return 409 `idempotency_conflict`. Expired non-credential reuse SHALL be new work.

#### Scenario: POST replay matches
- **GIVEN** a retained binding
- **WHEN** scope/hash match
- **THEN** outcome returns without duplication

#### Scenario: Replay payload differs
- **GIVEN** a retained binding
- **WHEN** payload hash differs
- **THEN** 409 returns without mutation

#### Scenario: Key is missing
- **GIVEN** POST without valid key
- **WHEN** validated
- **THEN** normalized 400 returns unchanged

### Requirement: HTTP idempotency
GET SHALL be read-only; PUT SHALL replace state deterministically; DELETE SHALL converge on revocation. Repeats SHALL NOT create transitions and SHALL remain auditable.

#### Scenario: Revocation repeats
- **GIVEN** revoked credential/Grant
- **WHEN** DELETE repeats
- **THEN** 204 returns without secret/transition

### Requirement: Credential secrecy and rotation
First issuance SHALL use a dedicated `CredentialIssuance` response that reveals one key exactly once and persists only ID/hash/prefix/`active|revoked` status/lifecycle; CredentialReference and lists SHALL omit hash/key. Rotation SHALL atomically set the old credential to `revoked`, create one active replacement, and reveal only the replacement key once. Replay SHALL return the same IDs/status with `secret_revealed=false`, no key, and no transition. Failure SHALL leave the old credential active.

#### Scenario: First issuance succeeds
- **GIVEN** authorized issuance
- **WHEN** first successful
- **THEN** one key shows; later views are metadata-only

#### Scenario: Rotation replay occurs
- **GIVEN** completed rotation
- **WHEN** replayed
- **THEN** no key or second credential appears

### Requirement: Safe errors and audit reads
Failures SHALL use `ErrorEnvelope`; authentication SHALL precede lookup. Hidden/absent resources SHALL return identical 404 `resource_not_found`; validation SHALL return 422. Audit reads SHALL return metadata and redaction state only. Any parameter or field requesting raw or redacted content SHALL be unsupported and return uniform 422 without revealing whether content exists. Retention and content access remain undefined and out of scope.

#### Scenario: Hidden resource is probed
- **GIVEN** absent/unauthorized IDs
- **WHEN** requested
- **THEN** identical safe 404 returns

#### Scenario: Audit content retrieval is requested
- **GIVEN** any parameter or field requesting raw or redacted audit content
- **WHEN** the audit read is validated
- **THEN** uniform 422 returns without revealing whether content exists

### Requirement: Offline bootstrap
Offline seed/CLI bootstrap SHALL deterministically create first Principal, active credential, and active direct Grants from stable identity. A dedicated first-success response SHALL reveal one key exactly once and retain hash/prefix only. Duplicate seed SHALL converge without reveal/rotation, return `secret_revealed=false`, and omit the key. Incompatible partial state SHALL return `bootstrap_conflict`, mutate nothing, and serialize no secret.

#### Scenario: Bootstrap repeats
- **GIVEN** an applied seed
- **WHEN** repeated
- **THEN** identities converge without credential reveal

#### Scenario: Bootstrap conflicts
- **GIVEN** incompatible partial state
- **WHEN** bootstrap runs
- **THEN** it fails unchanged and secret-free
