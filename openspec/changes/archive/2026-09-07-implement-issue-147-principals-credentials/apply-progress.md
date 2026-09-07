# Apply Progress: Complete Administrative Principals + Credentials API (Issue #147)

## Status: COMPLETE — READY FOR INDEPENDENT SDD VERIFY

The owner approved an immutable 2.0.0 full snapshot while retaining 1.4.0. This
progress record distinguishes merged work from unimplemented work; it is not a
claim that the remaining acceptance suite has run.

## Verified Merged Baseline (A/B/C)

- [x] Slice A: immutable 1.4.0 control audit evidence, fixtures, and tooling release support.
- [x] Slice B: control `AuditEvent` validation and additive control resources/grants in `src/sre_agent/persistence/seeds.py`.
- [x] Slice C: engine-delegated principal create/list/get service/router and associated control-plane tests.
- [x] Current baseline evidence (not 2.0.0 acceptance): Python 670 passed, 1 skipped; Node 73 passed; Ruff 66 files clean; isolated PostgreSQL control/persistence/auth/seed baseline passed on port 55447.

## Pending 2.0.0 Work

- [ ] Create and validate full immutable `schemas/releases/2.0.0/`; do not alter 1.4.0.
- [ ] Add `expected_updated_at` to the status contract and implement an atomic concurrent-write guard with PG proof.
- [ ] Correct `at_least_24h` idempotency expiry and preserve `principal_lifetime` no-expiry records.
- [ ] Complete status, issue, list, revoke, and active-only atomic rotation routes/use cases.
- [ ] Authenticate before every validation path; preserve authorization metadata for successful authenticated audit events while validation/401 evidence remains anonymous.
- [ ] Run full contract, lint, migration, DB-independent, isolated-PG, and all-eight-route acceptance verification; record only observed results.

## Delivery Boundary

Apply uses local auto-chained slices D->E->F->G->H, each targeted at <=400
reviewed authored lines. No GitHub publication, merge, or size exception is
implied by this plan.

# Issue #147 persistence work-unit evidence

## Work Unit E — DB correctness (tasks 2.1–2.3 plus required idempotency convergence finalization)

### Completed tasks

- [x] **2.1** Atomic principal-status CAS: `PrincipalRepository.replace_status` performs a conditional PostgreSQL `UPDATE ... WHERE principal_id AND updated_at ... RETURNING`; an update miss returns `None` only for an absent principal and otherwise raises `StaleWriteError`.
- [x] **2.2** Idempotency safety: `at_least_24h` derives/stores a concrete expiry no earlier than `created_at + 24h`; `principal_lifetime` always stores `NULL`; expired timed bindings become a fresh transition; a PostgreSQL `INSERT ... ON CONFLICT DO NOTHING ... RETURNING` makes same-key concurrent requests converge to one initial result and one replay; different payload hashes conflict. `response_payload` is round-tripped and `set_response_payload()` reassigns/flushed JSONB metadata for a new-session replay without storing a secret.
- [x] **2.3** Rotation safety: `rotate()` locks the credential row with `FOR UPDATE`, accepts only active/unexpired rows, returns `None` with no mint for absent/revoked/expired rows, and lets issuance failures escape the transaction so the old credential remains active after rollback.

### RED → GREEN evidence

| Behavior | RED | GREEN |
|---|---|---|
| Two-session principal CAS | Coordinated legacy read/check/flush returned `['written', 'written']`. | One writer + one stale result; stored row is one winner. |
| Retention/lifetime/replay expiry | Timed record persisted `expires_at=None`. | Timed expiry is >=24h; lifetime is `NULL`; pre-expiry replays and post-expiry reclaims. |
| Inactive and failed rotation | Revoked rotation minted a replacement. | Revoked/expired produce no replacement; injected issuance failure rolls back revocation. |
| Concurrent idempotency first claim | Concurrent insert raised PostgreSQL unique violation. | One first claim + one replay, one transition row, no raw `IntegrityError`. |
| Finalized replay metadata | Missing `set_response_payload` port raised `AttributeError`. | Secret-free metadata persisted and replayed in a new transaction. |

### Work Unit Evidence

| Evidence | Actual result |
|---|---|
| Focused test | `TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres .venv/bin/pytest tests/test_control_persistence.py tests/test_persistence_repositories.py -q` → **10 passed in 0.47s**. |
| Runtime harness | The new suite resets only disposable PostgreSQL `:55447`, migrates it to head, uses independent async sessions for true CAS and idempotency first-claim competition, then verifies stored database state, retention/replay, row locking, and rollback. |
| Style | Ruff check passed; format check reports both persistence files already formatted. |
| Rollback boundary | Revert `src/sre_agent/persistence/repositories.py` and delete `tests/test_control_persistence.py`; no migration is part of E. |

### Budget accounting — one honest split pass

The original E evidence file contains three independently reviewable deliverables. No source or test code was compressed or changed during this split.

| Deliverable | Scope and shared allocation | Actual authored-line impact | Rollback boundary |
|---|---|---:|---|
| **E1: principal status CAS** | `replace_status` plus the module imports, disposable-PG fixture, coordinated-session harness, and two-session CAS case. Per instruction, shared fixture/harness lines are allocated here only. | **132** (28 repository diff + 104 test/fixture lines) | CAS hunk in `repositories.py` and test lines 1–104. |
| **E2: idempotency** | Timed/lifetime expiry, expired replay, same/different hash behavior, concurrent first-claim convergence, and persisted secret-free response payload. | **230** (48 repository diff + 182 test lines) | Idempotency hunk in `repositories.py` and test lines 105–286. |
| **E3: rotation** | Locked active/unexpired transition, revoked/expired no-mint behavior, and issuance-failure rollback. | **74** (17 repository diff + 57 test lines) | Rotation hunk in `repositories.py` and test lines 287–343. |

Each autonomous deliverable is within the 400-line review target. The full test file remains a single cohesive PG fixture file, but its shared setup is allocated only to E1 and never counted again.

## Work Unit E.2.4 — audit 2.0 migration correctness

- [x] Added migration head `20260907_05` without changing earlier migrations. It permits authorization-denial 404 only when action is `admin.read` and the HMAC-only JSONB resource type is `administrative_control` (missing/null resource is explicitly rejected with `COALESCE`); response-path 403 remains valid, and `responses.create` 404 remains rejected.
- [x] Widened audit reason-code persistence exactly for 2.0 `resource_not_found` and `status_conflict` events.
- [x] Downgrade is fail-closed if any 05-only 404 denial evidence or 2.0-only reason code exists; it never rewrites append-only audit history.
- [x] Updated readiness prerequisite to revision `20260907_05`.

| Evidence | Actual result |
|---|---|
| Migration tests | `TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres .venv/bin/pytest tests/test_migrations.py -q` → **8 passed in 0.26s**. |
| Runtime harness | `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres .venv/bin/alembic current` → **20260907_05 (head)**. |
| Health test | `.venv/bin/pytest tests/test_health.py -q` → **3 passed in 0.22s**. |
| Style | Ruff check passed; format check reports all four files formatted. |
| Rollback boundary | Revert `src/sre_agent/persistence/models.py`, `src/sre_agent/gateway/health.py`, `migrations/versions/20260907_05_allow_control_read_audit_404.py`, and corresponding migration tests as one unit. |

Migration work-unit impact is 153 authored lines, within the 400-line target.

# Issue 147 — Work Unit D Contract Evidence

## Work Unit Evidence

| Evidence | Actual result |
|---|---|
| Focused test command | `npm --prefix schemas/tooling test` — 74 passed, 0 failed (executed outside sandbox because Node crashes natively inside it) |
| Runtime harness | `node schemas/tooling/release.mjs validate --release 2.0.0` — `Validated immutable release 2.0.0: 161 artifacts and 8 checks.` |
| Release identity | `schemas/releases/2.0.0/manifest.yaml`, `conformance/evidence.json`, and `conformance/compatibility.json` generated deterministically; compatibility is breaking from 1.4.0 with preserved API major 1 and `conformance/migration.md`. |
| Legacy immutability | `git diff --exit-code -- schemas/releases/1.4.0` — passed; no 1.4.0 byte changed. |
| Rollback boundary | Revert `schemas/releases/2.0.0/`, the 2.0 tooling allowlist/validation changes, `docs/contracts/2.0.0-migration.md`, and the contract tooling test. This does not touch prior releases or runtime behavior. |

## Completed Contract Tasks

- [x] 1.1 Full immutable 2.0.0 snapshot with status token, status conflict, inactive rotation, audit-boundary, and retention fixtures.
- [x] Contract portion of 1.2: schema/tooling RED→GREEN proof for the required status token and 2.0 package retaining `/v1`.

## Pending Integration

- Runtime/HTTP tests for stale timestamp, engine-before-target, and emitted audit DTOs remain owned by the runtime slice.
- Persistence and route tasks 2.x–5.1 remain pending.

## Interrupted integration checkpoint — 2026-09-07

**Status: incomplete; do not publish, merge, close #147, or treat earlier passing
acceptance evidence as final.** All apply workers were interrupted by the Codex
usage limit while integrating the last credential-failure changes. No final SDD
verification or archive ran. Review mode remains disabled/unmanaged.

Current parent-observed checks:

- Full isolated-PG suite: **682 passed, 1 failed, 1 skipped**. Failure:
  `tests/test_control_acceptance.py::test_rotation_issuance_failure_rolls_back_and_audits`
  receives 503 instead of its contracted 409. The interrupted change maps
  `rotation_failed` to a new audit reason not accepted by the SQL constraint.
- Ruff check and format check pass (70 files); `git diff --check` passes.
- The 1.4.0 snapshot has no diff.
- The latest 2.0.0 validation fails Redocly: an unquoted comma in the inline
  `InternalFailure.description` creates an unexpected YAML property named
  `without exception or secret details`. Regenerate release evidence/manifest
  only after resolving the final contract/runtime differences.
- Earlier all-eight-route isolated acceptance was **5 passed** before the last
  interrupted edits; this is superseded by the failing full-suite checkpoint.

### Resume in this order

1. Reconcile only the interrupted failure handling. Intended final direction:
   controlled rotation failure remains a 409 `CredentialRotation` failure result
   with zero counts and rollback; standalone credential issuance dependency errors
   use a sanitized 500 `ErrorEnvelope` with `credential_issuance_failed`. Reuse
   the existing `upstream_failed` audit reason rather than introducing an
   unmatched `rotation_failed` reason in only some layers. The current code still
   contains an incorrect `credential_rotation_failed` issuance error.
2. Fix the 2.0.0 OpenAPI YAML description and align issuance/rotation error
   responses, runtime DTOs, and actual response bodies; preserve 1.4.0 bytes.
3. Complete the synthetic SQL-error secrecy test. The engine now uses
   `hide_parameters=True` and its focused configuration test exists, but driver
   detail still requires safe exception handling without traceback logging.
4. Merge final runtime/acceptance evidence and honest per-behavior work-unit
   boundaries into this record; pending tasks must remain pending until proven.
5. Run all Python tests, Ruff, all release validators, Alembic check, and
   independent SDD verification; only then consider archive/publication.

Diagnostic outputs are in `/tmp/issue147-evidence/final-interrupted-pytest.txt`
and `/tmp/issue147-evidence/final-interrupted-contract.txt`. Worker progress and
result files are `/tmp/issue147-*-progress.md` and `/tmp/issue147-*-result.*`.
The disposable PostgreSQL container `sre-issue147-pg-20260907` is removed at this
checkpoint; recreate it on 127.0.0.1:55447 before database checks. User services
on ports 5432/8000/8080 were not changed. Work remains uncommitted and unpushed.


# Final closure evidence — 2026-09-07

The interrupted integration checkpoint is resolved. No release was published,
no commit, push, merge, or GitHub mutation occurred, and 1.4.0 remains unchanged.
This apply phase is complete and awaits an **independent SDD verify** phase.

## Reconciled failure behavior

- A controlled rotation issuance failure now returns the documented `409`
  `CredentialRotation` failure wrapper with `rotation_failed`, zero replacement
  and transition counts, and rollback preserving the old active credential.
  Its audit reason is the already-persisted `upstream_failed`; no unsupported
  `rotation_failed` SQL reason was introduced.
- A standalone credential issuance dependency failure returns the sanitized,
  retryable `500 credential_issuance_failed` `ErrorEnvelope`. It is audited as
  `upstream_failed`; driver details, statement parameters, key hashes, and keys
  are absent from the response and captured logs.
- The 2.0.0 OpenAPI `InternalFailure` description is quoted and valid. Credential
  issue documents `500`; rotation documents its `201` wrapper and `409` typed
  failure/error-envelope union without a runtime `500` branch.

## Final completed tasks

- [x] **1.2** Runtime RED→GREEN evidence now proves authenticate-first behavior,
  anonymous validation/401 audit boundaries, authorization metadata on success,
  and engine-before-target ordering for all eight control routes.
- [x] **1.3** Acceptance tests prove one-time secret disclosure, replay/list/audit
  secrecy, audit rejection suppression, and sanitized SQL-driver issuance failure.
- [x] **2.5** Database engines use `hide_parameters=True`; focused coverage proves
  SQLAlchemy error rendering hides bound hashes and controlled runtime handling
  never exposes a driver detail.
- [x] **3.1–3.2** Status CAS, deterministic `409 status_conflict`, authenticated
  audit metadata, and anonymous validation/401 events are implemented and proven.
- [x] **4.1–4.2** Issue/list/revoke/rotation support metadata-only replay, bounded
  lists, convergent revoke, active-only atomic rotation, and rollback-safe failure.
- [x] **5.1** Final Python, lint, contract, immutable-snapshot, and migration
  evidence below all passed.

## Work-unit evidence and honest review allocation

The full service delta is intentionally not represented as one review unit. The
following is the single honest allocation pass: shared acceptance harness lines
are allocated once across the route units; source and test code was not compressed
or restyled to reach a limit. Every behavior unit remains within the 400-line
review budget.

| Unit | Scope and exact allocated evidence | Authored-line impact | Focused proof | Runtime boundary and rollback |
|---|---|---:|---|---|
| **F1 auth/audit** | Authenticate-before-validation reordering, authorization-stage audit context, and `tests/test_control_authorization_order.py` eight-case repository-constructor trap. | **390** | `.venv/bin/pytest tests/test_control_authorization_order.py -q` → **8 passed** | DB-independent service harness denies every exact scope before a target repository can construct. Revert authorization/audit hunks and this test. |
| **F2 status** | Closed status body, expected timestamp CAS result mapping, status router binding, and status portions of HTTP acceptance. | **230** | `TEST_DATABASE_URL=...:55447 .venv/bin/pytest tests/test_control_acceptance.py -q` → **6 passed** | Isolated PostgreSQL proves missing token 422 and stale write 409 without overwrite. Revert status model/service/router hunks and associated acceptance assertions. |
| **G1 issue** | Credential issue/replay metadata behavior, sanitized dependency 500, issue router `500`, and SQL secrecy acceptance case. | **290** | `TEST_DATABASE_URL=...:55447 .venv/bin/pytest tests/test_control_acceptance.py -q` → **6 passed** | Real FastAPI + PostgreSQL proves one-time secret and `upstream_failed` audit with no driver detail. Revert issue path, InternalFailure contract entries, and related test assertions. |
| **G2 list/revoke** | Bounded metadata-only credential list, reject pagination, convergent revocation, and route bindings. | **275** | `TEST_DATABASE_URL=...:55447 .venv/bin/pytest tests/test_control_acceptance.py -q` → **6 passed** | Real FastAPI + PostgreSQL proves list secrecy and repeated DELETE 204. Revert list/revoke service/router hunks and their acceptance assertions. |
| **H rotation** | Active-only rotate, typed 201/409 response behavior, idempotency replay, rollback failure wrapper, and rotation contract fixture/OpenAPI union. | **395** | `TEST_DATABASE_URL=...:55447 .venv/bin/pytest tests/test_control_acceptance.py -q` → **6 passed** | Real FastAPI + PostgreSQL proves concurrent 201/409, replay secrecy, inactive no-mint, and rollback preserving the old credential. Revert rotation service/router/repository hunks and rotation fixtures/assertions. |

The database repository units E1–E3 and migration E2.4 remain as recorded above;
their earlier focused proofs are preserved rather than replaced.

## Final verification

| Check | Observed result |
|---|---|
| Complete Python suite | `TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres CONTROL_ACCEPTANCE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres uv run pytest -q` → **692 passed, 1 skipped in 5.21s** |
| Focused acceptance | Same isolated PostgreSQL settings with `.venv/bin/pytest tests/test_control_acceptance.py -q` → **6 passed in 1.60s** |
| Authorization ordering | `.venv/bin/pytest tests/test_control_authorization_order.py -q` → **8 passed in 0.18s** |
| Ruff and diff hygiene | `uv run ruff check . && uv run ruff format --check . && git diff --check` → **all checks passed; 71 files formatted** |
| Contract unit tests | `npm --prefix schemas/tooling test` → **74 passed, 0 failed** |
| 2.0.0 generation/validation | `node schemas/tooling/release.mjs projection --release 2.0.0 && node schemas/tooling/release.mjs evidence --release 2.0.0 && node schemas/tooling/release.mjs validate --release 2.0.0` → **161 artifacts, 8 checks** |
| Published releases | `node schemas/tooling/release.mjs validate-all` → **exit 0** |
| Immutable 1.4.0 | `git diff --exit-code -- schemas/releases/1.4.0` → **passed** |
| Alembic | `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres .venv/bin/alembic current --verbose` → **20260907_05 (head)** |

## Remaining apply tasks

None. Independent SDD verification is required before archive or publication.
