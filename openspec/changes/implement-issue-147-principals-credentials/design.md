# Design: Administrative Principals + Credentials API

## Technical Approach

Add a control-plane service in `sre_agent/control/` that reuses the verified #18
`AuthorizationDecisionEngine` as the sole authority. Persistence exposes facts
(principal status, control-scoped resource view, exact grant) and owns scoped
idempotency bindings. Every terminal attempt commits one metadata-only audit event
before releasing its ordinary result; audit rejection suppresses the result with
503 `audit_unavailable`.

## Architecture Decisions

| Decision | Choice and rationale | Rejected alternative |
|---|---|---|
| Authority | Control use cases call `AuthorizationDecisionEngine.evaluate()` with `resource_type=administrative_control` (SEC-006 name), `resource_id=principals|credentials`, per owner decision on #147. Actions are `admin.read` (lecturas) and `admin.write` (creación, actualización, revocación, rotación). No caller composes decisions. | Per-route `if` checks or repository `decide()` duplicates create parallel rules and drift. |
| Resource scope | Persist two active resources `administrative_control/principals` and `administrative_control/credentials` in the existing `resources` table (widened `ck_resources_type`, non-`llm_model` branch keeps routing NULL); seed bootstrap grants `admin.read`/`admin.write` to `admin-human`. `ResourceRepository.authorization_view()` returns them as ordinary facts. | Synthesizing control views without rows would bypass FK-backed grant integrity and diverge from the owner decision. |
| Idempotency scope | Binding key = (operator principal_id, method, canonical path incl. IDs, key digest). Payload = RFC-8785/canonical JSON SHA-256 of the closed body. Credential bindings live for principal lifetime; principal-create bindings live >= 24h. Same key+hash replays stored outcome; same key+different hash -> 409 `idempotency_conflict` without mutation. | Global (operator-agnostic) keys let one operator replay another's issuance; time-only expiry lets revoked-credential replay mint. |
| Concurrency | `PUT /v1/principals/{id}/status` requires `expected_updated_at`; mismatch -> 409 `status_conflict` without mutation. Replays of the same status value are deterministic and return 200. | ETag headers or silent last-write-wins lose determinism and break the acceptance criterion. |
| Rotation atomicity | Rotation runs in one transaction: revoke old (active->revoked) + issue exactly one replacement. Any failure rolls back, leaving old active (`result=failure`, `error_code=rotation_failed`, zero transitions). Replay returns stored issuance with `secret_revealed=false`, no key. | Two-step revoke-then-issue can orphan the principal with zero active credentials. |
| Audit shape | Control events use `stage=audit`, metadata-only identity/resource refs, `content_state=absent`, no routing/policy leakage beyond the uniform deny. New operations extend the closed vocabulary; 1.3.0 denial-cause rules unchanged. | Reusing `stage=authorization` for admin reads confuses governed-LLM evidence; raw IDs in audit break ADR-005 domain separation. |
| Contract release | Additive `schemas/releases/1.4.0/` reuses unchanged 1.3.0 files by reference (manifest entries point at 1.3.0 paths where bytes are identical); only new/changed control schemas, OpenAPI, fixtures, and evidence are new files. | Copying the whole tree duplicates ~150 files and risks hash drift; editing 1.3.0 in place breaks immutability. |

## Data and Transaction Flow

```text
Bearer -> authenticate (401 uniform)
  -> validate closed body + idempotency key + limit/params (400/422)
  -> idempotency lookup (scope+hash)
       -> hit, same hash: replay stored outcome, audit replay, release
       -> hit, other hash: 409 idempotency_conflict, audit, no mutation
  -> engine.evaluate(operator principal, admin.read|admin.write, administrative_control, principals|credentials)
       -> deny: no target lookup/mutation; uniform 403/404 public; exact cause only in audit (#154)
       -> allow: mutate in one transaction (principal/credential/idempotency)
  -> audit append (metadata-only); on reject: 503 audit_unavailable, suppress
  -> release ordinary result (201/200/204 + envelopes)
```

Hidden vs absent: `GET` of a principal the operator may not see returns 404
`resource_not_found` identical to absent. Unauthorized mutation returns 403
`resource_unavailable` without confirming existence.

## Interfaces and Persistence

- `PrincipalRepository.create/get/list/replace_status` with `updated_at` compare.
- `CredentialRepository.issue/list_for_principal/revoke/rotate` (rotate = revoke +
  issue in one transaction; failure path preserves old active).
- `IdempotencyRepository.claim_or_replay(scope, payload_sha256, outcome)` with
  unique scope+key digest and `transition_count=1` guard.
- `ControlAuthorizationFacts`: `ResourceFactReader` synthesizing control views;
  `GrantFactReader` = existing `GrantRepository.find_active`.
- Migration `20260902_04`: `idempotency_records` table + `ck_resources_type` widening
  (`administrative_control`) + control audit vocabulary (`ck_audit_events_operation`,
  `ck_audit_events_action` extension); readiness head becomes `20260902_04`. Also
  extends `schemas/tooling` release allow-list (`1.4.0`, `PREVIOUS_RELEASE`) since the
  #153 contract is otherwise unpublishable by tooling.
- Seeds (`seeds.py`, bootstrap offline): first administrator + the two
  `administrative_control/*` resources + `admin.read`/`admin.write` grants. Seeds are
  NOT an HTTP bypass.

## File Changes

| Paths | Action |
|---|---|
| `src/sre_agent/control/service.py`, `router.py` | Create use cases + FastAPI control-plane router. |
| `src/sre_agent/governance/dto.py`, `persistence/models.py`, `persistence/projections.py` | Control operations + issuance/rotation/idempotency/list DTOs, rows, projections. |
| `src/sre_agent/persistence/repositories.py` | Principal CRUD, credential list/rotate, idempotency repo, fact adapters. |
| `src/sre_agent/gateway/audit.py`, `application.py`, `gateway/health.py` | Control audit projection, router wiring, readiness head. |
| `migrations/versions/20260902_04_*.py` | New migration + downgrade. |
| `schemas/releases/1.4.0/**` | Additive control contract + fixtures + manifest/evidence. |
| `tests/test_control_plane.py`, `test_governance_dto.py`, `test_migrations.py`, `test_persistence_*.py` | RED->GREEN evidence. |

## Testing Strategy and Planned RED Evidence

- Unit (DB-independent): idempotency-key shape, payload-hash stability, replay vs
  conflict, stale-write 409, rotation-failure preservation, revoke-blocks-auth,
  secret absence in repr/JSON/logs, 403/404 uniformity, audit metadata-only.
- PG: CRUD round-trips, ordering, rotation atomicity, idempotency lifetime,
  concurrency conflict, audit append/readback, migration upgrade/downgrade.
- Contract: 1.4.0 OpenAPI lint + fixture validation + negative cases.

## Threat Matrix

| Boundary | Applicability | Safe/failure behavior and planned RED test |
|---|---|---|
| Secret handling | Applicable | Keys appear once; replay/list/audit/logs omit; negative replay-secret fixture. |
| Authorization | Applicable | Engine-only; deny short-circuits before mutation; no enumeration. |
| Idempotency scope | Applicable | Operator-scoped bindings; cross-operator replay impossible. |
| Concurrency | Applicable | Stale write -> 409, no overwrite. |
| Audit durability | Applicable | Append-before-release; reject -> 503, suppress result. |

## Migration / Rollback

Deploy 1.4.0 contract + migration before writers; deploy DTO/model/projection,
repositories, service/router together. Roll back writers first, then migration;
keep 1.4.0 artifacts published. No policy/audit rewrites.

## Open Questions

None. Owner decision on #147 (2026-09-04): option 3 with SEC-006 naming
(`administrative_control`), release 1.4.0 widening the #153 contract, persisted
resources `administrative_control/principals|credentials`, bootstrap grants
`admin.read`/`admin.write` via `seeds.py`, `evaluate()` before any target access,
uniform public response + exact audit-only cause per #154.
