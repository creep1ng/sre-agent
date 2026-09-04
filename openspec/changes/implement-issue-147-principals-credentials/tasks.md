# Tasks: Implement Administrative Principals + Credentials API (Issue #147)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 1400-1800 authored lines (contract 1.4.0 + migration + runtime + tests) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 openspec contract/migration plan -> PR 2 persistence+DTO -> PR 3 use cases+router -> PR 4 tests/evidence |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision (owner, #147 2026-09-04): option 3 with SEC-006 naming. Scope triples are
`(admin.read|admin.write, administrative_control, principals|credentials)`:
reads use `admin.read`, creación/actualización/revocación/rotación use
`admin.write`. Binding for this change.

### Suggested Work Units

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| 1 | Control DTOs + idempotency model + migration | `uv run pytest tests/test_governance_dto.py tests/test_migrations.py -q` | N/A | Revert DTO/model/migration + 1.4.0 draft |
| 2 | Repositories: principal CRUD, list, credentials, rotation, idempotency | PG-backed `tests/test_persistence_repositories.py` subset | N/A | Revert repository adapters only |
| 3 | Use cases + FastAPI router + application wiring | `uv run pytest tests/test_control_plane.py -q` (new) | `TestClient` control-flow | Revert control service/router wiring |
| 4 | Contract 1.4.0 + fixtures + openspec evidence + full gates | `npm --prefix schemas/tooling run validate:release -- --release 1.4.0` | issue-14 harness still green | Keep immutable 1.4.0 published |

## Phase 1: RED — Contract and Threat Tests

- [ ] 1.1 Add failing DB-independent tests: idempotency-key validation (400),
  payload-conflict 409, replay returns stored outcome without transition, stale
  `updated_at` -> 409, rotation failure leaves old active, revoke blocks auth,
  replay omits key, 403/404 non-enumeration, audit metadata-only (no secret).
- [ ] 1.2 Add failing PG tests: principal CRUD round-trip, bounded list ordering,
  credential issue/list/revoke/rotate, idempotency binding lifetime + conflict,
  concurrent stale-write conflict, audit append/readback for control operations.
- [ ] 1.3 Add failing contract tests: 1.4.0 control OpenAPI shapes validate;
  issuance/rotation/idempotency/list fixtures validate; negative replay-secret,
  duplicate-transition, hidden-resource cases rejected or mapped.

## Phase 2: GREEN — Persistence and Contracts

- [ ] 2.1 Extend `AuditEvent` operation vocabulary with control operations
  (`principals.create/get/list/status.replace`, `credentials.issue/list/revoke/
  rotate`) + `stage=audit` metadata-only rules; keep 1.3.0 denial-cause logic.
  Widen `ResourceType` with `administrative_control` (SEC-006 name) in DTO,
  `ck_resources_type`, `resource.schema.json`, `ResourceEvidence`.
- [ ] 2.2 Add control DTOs (`PrincipalCreate`, `StatusReplace`, `CredentialIssue`,
  `CredentialIssuance`, `CredentialRotation`, `IdempotencyRecord`, list envelopes)
  mirroring `schemas/releases/1.3.0` shapes; extend projections.
- [ ] 2.3 Add migration `20260902_04`: `idempotency_records` table +
  `ck_resources_type` widening (`administrative_control`) + control audit
  operation/action vocabulary; update health readiness head; keep downgrade path.
  Also extend `schemas/tooling` release allow-list (`1.4.0`, `PREVIOUS_RELEASE`).
- [ ] 2.4 Implement `PrincipalRepository` create/get/list/status-replace (+stale
  detection), `CredentialRepository` list-by-principal + rotate, and
  `IdempotencyRepository` scoped claim/replay; existing `ResourceRepository` /
  `GrantRepository` serve engine facts unchanged (no new `decide()`).
- [ ] 2.5 Publish additive `schemas/releases/1.4.0/` (control-plane OpenAPI +
  new/changed schemas + fixtures + manifest/compatibility/evidence). 1.4.0 is a
  complete sibling snapshot (tooling requirement); unchanged 1.3.0 bytes are
  copied verbatim, only widened/new artifacts differ.
- [ ] 2.6 Extend `seeds.py` (offline bootstrap): first administrator +
  `administrative_control/principals|credentials` resources + `admin.read` /
  `admin.write` grants; preserve determinism + `SeedConflict` semantics.

## Phase 3: GREEN — Service and HTTP

- [ ] 3.1 Implement `sre_agent/control/service.py` use cases: authenticate ->
  validate -> idempotency-claim -> `evaluate(principal, admin.read|admin.write,
  "administrative_control", "principals"|"credentials")` BEFORE any target
  lookup/mutation -> mutate -> audit-append -> release; deny path skips target
  access, returns uniform 403/404, audits exact cause only; fail-closed 503 on
  audit rejection; never log secrets.
- [ ] 3.2 Implement `sre_agent/control/router.py` FastAPI routes per matrix with
  closed bodies, limit/forbidden-param validation, typed envelopes, 204 revoke.
- [ ] 3.3 Wire `application.py` (control router behind bearer auth + audit store),
  preserving `/v1/responses` behavior and health probes.

## Phase 4: REFACTOR — Verification and Boundaries

- [ ] 4.1 Run `uv run ruff check .`, `ruff format --check .`, DB-independent
  pytest, PG-backed suites, `alembic check`, contract validate + conformance;
  record openspec `apply-progress.md` + `verify-report.md`.
