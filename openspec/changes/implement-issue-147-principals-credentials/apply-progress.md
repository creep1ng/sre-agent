# Apply Progress: Implement Administrative Principals + Credentials API (Issue #147)

## Status: IN PROGRESS (scope reconciled, partial GREEN)

Owner decision on #147 (2026-09-04): option 3 with SEC-006 naming. Scope triples
are `(admin.read|admin.write, administrative_control, principals|credentials)`.

## Completed

- [x] Branch `feat/issue-147-principals-credentials` from `origin/main`.
- [x] Merged verified #18 base (engine + audit + responses).
- [x] Openspec change `implement-issue-147-principals-credentials/`:
  `proposal.md`, `tasks.md`, `design.md`, `specs/control-plane-principals-credentials/spec.md`
  updated to `administrative_control` + `admin.read`/`admin.write` + 1.4.0.
- [x] RED `tests/test_control_plane.py` (ResourceType widening + CONTROL_SCOPES +
  hashing + secret-free projection) now GREEN.
- [x] Contract draft `schemas/releases/1.4.0/`: full 1.3.0 sibling retargeted;
  `resource.schema.json` + audit `resourceEvidence` widened;
  audit `operation` extended with 8 control operations, `action` with
  `admin.read`/`admin.write`. `manifest.yaml` / `compatibility.json` /
  `evidence.json` intentionally NOT staged: they carry stale 1.3.0 hashes and
  must be regenerated via node tooling (`release.mjs evidence --release 1.4.0`,
  allow-list currently caps at 1.3.0).
- [x] Runtime DTO `ResourceType` + `ControlAction` + control audit vocabulary.
- [x] `IdempotencyRecordRow` model + migration `20260902_04` (idempotency table +
  `ck_resources_type` widening + audit vocabulary) + readiness head.
- [x] Seeds: `administrative_control/principals|credentials` resources +
  4 `admin.read`/`admin.write` grants for `admin-human`.
- [x] Repositories: `PrincipalRepository` create/list/replace_status (stale guard),
  `CredentialRepository.list_for_principal` + atomic `rotate`,
  `IdempotencyRepository.claim_or_replay` (same-hash replay, other-hash 409).
- [x] `AuditProjector.control_event()` metadata-only control audit projection.
- [x] `ControlService` (create/list/get principals; authorize-before-target via
  `evaluate()`) + `control_router` + `application.py` wiring.
- [x] `test_governance_dto.py` exclusion extended for 1.4.0 nullable-cause
  negatives (mirrors 1.3.0 gating).
- [x] DB-independent suite: 495 passed. `ruff check` + `format --check`: clean.

## Remaining (tracked, not in this commit)

- Status replace / credential issue-list-revoke-rotate HTTP routes + service
  methods (scopes already reserved in `CONTROL_SCOPES`).
- PG-backed tests: seeds convergence (3 resources / 5 grants), CRUD round-trips,
  rotation atomicity, idempotency lifetime/conflict, stale-write 409, audit
  append/readback for control operations, migration upgrade/downgrade.
- Contract tooling: `schemas/tooling` allow-list (`1.4.0`, `PREVIOUS_RELEASE`),
  `control-plane.yaml` + `GrantCreate`/`GrantList` `administrative_control`
  coverage, new control fixtures, `manifest.yaml`/`compatibility.json`/
  `evidence.json` regeneration via node tooling.
- `verify-report.md` + full gates (`alembic check`, PG suites, contract validate).
