# Tasks: Complete Administrative Principals + Credentials API (Issue #147)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 900-1,200 authored lines; full-snapshot copies are generated identity material |
| 400-line budget risk | High overall; each work unit targets <=400 |
| Chained PRs recommended | Yes |
| Suggested split | Local slices D -> E -> F -> G -> H, stacked to main |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

No size exception is approved: use five local slices. Auto-chain authorizes local
stacking only, not GitHub publication.

### Verified merged baseline

- [x] A: published immutable 1.4.0 control evidence/tooling.
- [x] B: control-audit validator and additive control-resource/grant seed convergence.
- [x] C: engine-delegated principal create/list/get router, service, and baseline tests.

### Suggested Work Units

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| D | 2.0.0 snapshot + RED cases | `npm --prefix schemas/tooling run validate:release -- --release 2.0.0` | contract validator | `schemas/releases/2.0.0/` |
| E | DB correctness | `uv run pytest tests/test_persistence_repositories.py -q` | isolated PostgreSQL | repository changes |
| F | Status + audit | `uv run pytest tests/test_control_plane.py -q` | FastAPI TestClient + PostgreSQL | status/audit service code |
| G | Issue/list/revoke | `uv run pytest tests/test_control_plane.py -q` | FastAPI TestClient + PostgreSQL | credential non-rotation routes |
| H | Rotation + final proof | `uv run pytest tests/test_control_plane.py tests/test_persistence_repositories.py -q` | isolated PostgreSQL | rotation path/tests |

## Phase 1: Contract and RED (D)

- [x] 1.1 Create full immutable `schemas/releases/2.0.0/`; preserve 1.4.0 bytes and add status-token, 409, rotation, retention, and audit-denial/hidden-404 fixtures.
- [x] 1.2 Add failing HTTP RED tests: malformed unauthenticated request -> 401 before validation; authenticated validation audit is anonymous; authenticated success retains authorization metadata; engine precedes target access.
- [x] 1.3 Add failing secrecy RED tests: first issuance alone reveals a key; replay/list/audit/log omit it; audit rejection returns 503.

## Phase 2: Persistence correctness (E)

- [x] 2.1 Add failing two-session PG RED test, then make `src/sre_agent/persistence/repositories.py` status replace atomic CAS/locked conditional update.
- [x] 2.2 Add failing idempotency-scope and timed/lifetime-expiry RED tests, then derive/store `expires_at` correctly.
- [x] 2.3 Add failing inactive-rotation/rollback RED tests, then lock active rows and prevent replacement minting from revoked credentials.
- [x] 2.4 Add a migration, matching model constraint, and readiness revision for administrative read 404 denial causes; preserve governed Responses constraints and append-only history, with PostgreSQL migration evidence.
- [x] 2.5 Hide SQL bound parameters in engine errors as defense in depth; prove credential issuance failures are caught and audited without logging keys or hashes.

## Phase 3: Principal status and audit (F)

- [x] 3.1 Implement closed 2.0 status route/service flow with engine evaluation before target access and deterministic 409 handling.
- [x] 3.2 Update `src/sre_agent/control/service.py` audit completion so authenticated success retains identity/resource/decision while validation and 401 remain anonymous.

## Phase 4: Credential routes (G/H)

- [x] 4.1 Implement issue/list/revoke with bounded metadata-only responses, secret-free replay/log/audit behavior, and exact control scopes.
- [x] 4.2 Implement rotate using active-only atomic repository behavior, replay/conflict semantics, and one-time-secret response behavior.

## Phase 5: Verification

- [x] 5.1 Run Ruff, release validation, Alembic, snapshot comparison, and all-eight-route acceptance (create/list/get/status/issue/credential-list/revoke/rotation); record actual results in `apply-progress.md`.
