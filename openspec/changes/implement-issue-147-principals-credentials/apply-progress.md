# Apply Progress: Implement Administrative Principals + Credentials API (Issue #147)

## Status: IN PROGRESS (review fixes applied per owner decisions 2026-09-04)

Owner decisions (issue #147 + review threads #160/#161/#162):
1. Authorization-without-alias: control audit uses `stage=authorization` with
   identity + `administrative_control` resource + decision, exempting
   `model_alias_ref`/`routing` only for control evidence.
2. Explicit seed conflict: pre-control-plane seeds fail with
   `pre_control_plane_seed_requires_reseed`; no additive upgrade (no test data).
3. Slices adicionales: this stack ships 3 principals routes; status replace +
   credentials ship in follow-up slices with #147 open.

## Completed (stacked slices A/B/C)

- [x] Slice A: 1.4.0 audit-event control evidence + 4 control fixtures +
  tooling allow-list + regenerated `manifest.yaml`/`compatibility.json`/
  `evidence.json` (`validate --release 1.4.0`: 149 artifacts, 8 checks).
- [x] Slice B: control `AuditEvent` validator (identity+resource required,
  alias/routing forbidden) + explicit seed conflict + PG fixture coverage.
- [x] Slice C: `control_event()` emits DTO-valid evidence (allow requires
  grant `policy_id`; deny cause only on 403 deny); typed FastAPI router
  (3 principals routes; status/credentials reserved); extended
  `test_control_plane.py` (scopes, operations, projector, router).
- [x] DB-independent suite: 506 passed. `ruff check` + `format --check`: clean.

## Remaining (follow-up slices, #147 stays open)

- Slice D: status replace route + service + stale-write tests.
- Slice E: credentials issue/list/revoke/rotate routes + service + secrecy tests.
- PG-backed tests: seeds convergence (3 resources / 5 grants), CRUD round-trips,
  rotation atomicity, idempotency lifetime/conflict, audit append/readback,
  migration upgrade/downgrade.
- `verify-report.md` + full gates (`alembic check`, PG suites, contract validate).
