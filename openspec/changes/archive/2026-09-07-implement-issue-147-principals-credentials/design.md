# Design: Complete Administrative Principals + Credentials API

## Technical Approach

Retain merged slices A/B/C and implement the unfinished operations as local
stacked slices. 2.0.0 is a new complete immutable snapshot because its mandatory
status concurrency token breaks 1.4.0 clients; this package-major change retains
the `/v1` API path rather than introducing `/v2`.

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Contract | Copy every 1.4.0 artifact into `schemas/releases/2.0.0/`; regenerate only 2.0.0 release metadata after intentional changes. | A reference-only or partial release is not an immutable snapshot; editing 1.4.0 is forbidden. |
| Status write | Conditional database update on `(principal_id, expected_updated_at)` (or row lock with equivalent predicate). | ORM read-then-flush permits two concurrent writers to pass the same timestamp. |
| Authorization | Authenticate first, validate second, evaluate the engine, then access a target. | Invalid unauthenticated requests must be uniform 401; engine order blocks existence probing. |
| Audit | `_finish` carries context/resource/decision for successful authenticated results and denials; validation and 401 deliberately omit them. | The current audit projection must remain DTO-valid without inventing identity before authentication. |
| Idempotency | Repository derives/stores `expires_at=created_at+24h` for timed bindings and `NULL` only for lifetime bindings. | Current optional expiry allows the timed contract to persist indefinitely. |
| Rotation | Lock credential; require `active`; revoke and issue in one transaction. | Current code can issue from an already revoked row. |
| Seeds | Preserve additive convergence of two control resources and four admin grants. | Existing seeded databases must gain control nodes without destructive reseeding. |

## Data Flow

```text
request -> authenticate -> anonymous audit + 401 on failure
        -> syntax validation -> anonymous audit + 4xx on failure
        -> engine evaluate(control tuple) -> target access/mutation
        -> authorization audit(identity + control resource + decision) -> response
```

For POST operations, the engine runs before target access; only then does the
idempotency repository claim/replay. A same-hash replay does not transition state;
a hash conflict returns 409. Rotation holds one transaction boundary around active
state check, revoke, and replacement issuance.

## File Changes

| File(s) | Action | Description |
|---|---|---|
| `schemas/releases/2.0.0/**` | Create | Full snapshot, required status token, credential/error/audit fixtures and regenerated release metadata. |
| `src/sre_agent/control/service.py` | Modify | Complete routes/use cases and preserve authenticated authorization audit metadata. |
| `src/sre_agent/persistence/repositories.py` | Modify | Atomic status CAS, retention expiry, and active-only rotation. |
| `tests/test_control_plane.py`, `tests/test_persistence_repositories.py` | Modify | Contract, HTTP, concurrency, retention, rotation, and secrecy proof. |
| `tests/test_persistence_seeds.py` | Modify only if needed | Preserve and prove additive seed convergence. |

## Interfaces / Contracts

```json
{ "status": "active", "expected_updated_at": "2026-09-07T00:00:00Z" }
```

2.0.0 defines 409 `status_conflict` for a conditional-write miss and an explicit
non-success error for inactive rotation; neither outcome may create a credential.

## Testing Strategy

| Layer | Evidence |
|---|---|
| Contract | Full 2.0.0 validation, immutable 1.4.0 comparison, missing-token and inactive-rotation fixtures. |
| Unit/HTTP | Engine-before-target, audit identity boundary, secret-free responses, replay/conflict. |
| PG | True simultaneous status writers, TTL/lifetime persistence, locked rotation rollback and no mint from revoked. |

## Threat Matrix

| Boundary | Applicability | Safe/failure behavior and planned RED test |
|---|---|---|
| Secret handling | Applicable | First issuance alone returns key; replay/list/audit/logs omit it; negative replay-secret test. |
| Authorization/routing | Applicable | Authentication precedes validation; engine precedes targets; malformed unauthenticated request is 401; target-spy RED test. |
| Idempotency scope | Applicable | Operator/path/hash scope and timed-vs-lifetime expiry; cross-hash and expiry RED tests. |
| Concurrency | Applicable | One winner for simultaneous status writes; two-session PG RED test. |
| Audit durability | Applicable | Authenticated success has authorization metadata; validation/401 omit identity; append failure becomes 503; RED tests. |

## Migration / Rollout

The existing idempotency migration remains compatible; deploy implementation slices
in order after 2.0.0 validation. Roll back service/router slices first while
retaining published snapshots and append-only evidence.

## Open Questions

None.
