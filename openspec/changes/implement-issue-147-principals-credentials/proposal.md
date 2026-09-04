# Proposal: Implement Administrative Principals + Credentials API (Issue #147)

## Intent

Implement the administrative HTTP API for Principals and credentials over the 1.3.0
contract, the existing persistence ports, and the reusable authorization engine from
issue #18, without letting the UI write persistence directly or exposing secrets.
This unblocks the admin-console user story #19, which explicitly excludes endpoints
and persistence.

## Scope

### In Scope

- `POST /v1/principals`, `GET /v1/principals`, `GET /v1/principals/{id}`,
  `PUT /v1/principals/{id}/status` over existing `Principal` DTO/rows.
- `POST /v1/principals/{id}/credentials` (issue), `GET .../credentials` (metadata list),
  `DELETE /v1/credentials/{id}` (revoke, convergent), `POST /v1/credentials/{id}/rotation`.
- Idempotency-Key scoped bindings with payload hash, 24h minimum, credential bindings
  for principal lifetime, replay without transition, 409 on payload conflict.
- Optimistic concurrency on `PUT status` via expected `updated_at` (stale write -> 409).
- Every terminal attempt audited metadata-only before release; 503 `audit_unavailable`
  fail-closed on store rejection.
- Typed 401/403/404/409/422 envelopes; hidden/absent resources indistinguishable.
- All access decisions delegated to `AuthorizationDecisionEngine`; no parallel rules.

### Out of Scope

- Admin UI experience (#19), Resources/grants administration, historical credential
  display, end-user management, SSO, cloud deployment.
- Bootstrap/offline seed changes; existing `seeds.py` behavior is preserved.
- New resource types, new grant semantics, roles/scopes/tenancy.

## Capabilities

### New Capabilities

- `control-plane-principals-credentials`: Administrative Principal + credential
  lifecycle over the 1.3.0 contract with idempotency, concurrency, rotation,
  revocation, metadata-only audit, and engine-delegated authorization.

### Modified Capabilities

- `runtime-audit-evidence`: Control-plane terminal attempts recorded with the
  existing 1.3.0 `AuditEvent` shape extended with control operations.
- `authorization-decision-engine`: Second consumer (Principal-scoped facts +
  exact control grant) reusing the sole precedence authority.

## Approach

Add `sre_agent/control/` use cases + FastAPI router; extend `AuditEvent`
operation vocabulary with control operations; add `idempotency_records`
persistence with scoped key digest + payload hash; enforce status replace via
`updated_at` compare; rotate atomically (revoke old + issue replacement) with
failure leaving the old credential active; replay returns stored outcome with
`secret_revealed=false` and no key. Publish additive contract 1.4.0 reusing all
unchanged 1.3.0 artifacts by reference.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/sre_agent/control/` | New | Use cases + HTTP router for Principals/credentials |
| `src/sre_agent/governance/` | Modified | Control audit operations + DTOs (issuance/rotation/idempotency/list) |
| `src/sre_agent/persistence/` | Modified | `IdempotencyRecord` row/repo, principal CRUD, rotation, control audit ops |
| `src/sre_agent/gateway/` | Modified | Control audit projection; application wiring |
| `schemas/releases/1.4.0/` | New | Additive control-plane contract (OpenAPI + schemas + fixtures) |
| `migrations/` | Modified | `idempotency_records` + control audit operation vocabulary |
| `tests/` | Modified | Unit/integration/contract/migration evidence |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Secret/hash leaks via response/audit/log | High | Metadata-only projections, replay omission, negative fixture + repr tests |
| Parallel authorization rules drift | Medium | Engine-only decisions; fact adapters; non-enumeration tests |
| Idempotency scope collision across principals | Medium | Scope = principal+method+canonical path/IDs+key digest; conflict tests |
| Stale-write lost update | Medium | `updated_at` compare; 409 conflict path; concurrency tests |
| Rotation partial failure mints orphan | Medium | Atomic revoke+issue; failure leaves old active; rotation-failure tests |

## Rollback Plan

Revert router/use-case wiring first, then repositories/migration/DTOs; keep
immutable 1.4.0 artifacts published. No policy rows rewritten; audit history
append-only and preserved.

## Dependencies

- Issue #18 engine + 1.3.0 audit base (merged into this branch as verified base).
- Existing persistence (#11), authentication (#13), governed responses (#14).
- Contract authority: `schemas/releases/1.3.0/openapi/control-plane.yaml`.

## Success Criteria

- [ ] Same Idempotency-Key + payload replays one logical result; differing payload -> 409.
- [ ] Stale concurrent status write -> 409 without overwrite.
- [ ] Rotation revokes old credential atomically; revocation blocks later use.
- [ ] No list/read/audit/log exposes secrets or usable hashes.
- [ ] Unauthorized control operator cannot enumerate or mutate (uniform 403/404).
- [ ] Every operation delegates to the #18 engine; no parallel rule exists.
