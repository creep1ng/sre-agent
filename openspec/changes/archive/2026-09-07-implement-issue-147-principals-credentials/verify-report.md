```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:44924d461f23c201b5fe04bc60cbf5a96dd4f36866be2a60b6ad309e3e8dd618
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/7
scenarios: 11/11
test_command: TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres CONTROL_ACCEPTANCE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres uv run pytest -q -rs
test_exit_code: 0
test_output_hash: sha256:3543034f9c0fb867c53fd87bbf48f1e90908d08849091dbc9a9631bc95392922
build_command: uv run ruff check . && uv run ruff format --check . && git diff --check
build_exit_code: 0
build_output_hash: sha256:34801750828c02301a99e494c1b8ec195797e379bddb9586e45e182d1038bce6
```

## Verification Report

**Change**: implement-issue-147-principals-credentials
**Version**: 2.0.0 (with 1.4.0 retained)
**Mode**: Standard independent SDD verification

### Completeness
| Metric | Value |
|---|---:|
| Tasks total | 16 |
| Tasks complete | 16 |
| Tasks incomplete | 0 |

### Build & Tests Execution

**Tests**: PASS — 692 passed, 1 skipped; exit 0. The exact skip is `tests/test_openrouter_live.py:14`, which requires `RUN_OPENROUTER_LIVE_SMOKE=1` for a live provider request. This non-control-plane integration test is deliberately opt-in.

**Build/style**: PASS — Ruff check, Ruff format check, and `git diff --check`; exit 0.

**Contract/release**: PASS — `npm --prefix schemas/tooling test` (74/74); `node schemas/tooling/release.mjs validate --release 2.0.0` (161 artifacts, 8 checks); `validate-all` (1.0.0 through 2.0.0); and `git diff --exit-code HEAD -- schemas/releases/1.4.0` (exit 0).

**Migration**: PASS — `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55447/postgres .venv/bin/alembic current --verbose` reported `20260907_05 (head)`; `alembic check` reported `No new upgrade operations detected.`

**Current-candidate stability**: PASS — candidate snapshot manifest before/after the final read-only Python/lint/Node/Alembic run was identical: `sha256:44924d461f23c201b5fe04bc60cbf5a96dd4f36866be2a60b6ad309e3e8dd618`.

### Spec Compliance Matrix
| Requirement | Scenario | Runtime covering test | Result |
|---|---|---|---|
| Immutable major contract | Missing concurrency token | `test_control_acceptance.py::test_all_eight_routes_with_replays_expiry_and_revocation` | COMPLIANT |
| Principal lifecycle | Create then replay | `test_control_acceptance.py::test_all_eight_routes_with_replays_expiry_and_revocation` | COMPLIANT |
| Principal lifecycle | Simultaneous status writers | `test_control_persistence.py::test_status_replace_allows_exactly_one_concurrent_writer` | COMPLIANT |
| Principal lifecycle | Hidden principal is probed | `test_control_acceptance.py::test_conflict_inactive_auth_and_hidden_denial_audit` | COMPLIANT |
| Credential lifecycle and secrecy | Rotation replay | `test_control_acceptance.py::test_all_eight_routes_with_replays_expiry_and_revocation` | COMPLIANT |
| Credential lifecycle and secrecy | Rotation failure preserves service | `test_control_acceptance.py::test_rotation_issuance_failure_rolls_back_and_audits` | COMPLIANT |
| Credential lifecycle and secrecy | Revoked credential cannot authenticate | `test_control_acceptance.py::test_all_eight_routes_with_replays_expiry_and_revocation` | COMPLIANT |
| Idempotency and bounded lists | Payload conflict | `test_control_acceptance.py::test_conflict_inactive_auth_and_hidden_denial_audit` | COMPLIANT |
| Authentication and engine-delegated authorization | Unauthorized operator is blind | `test_control_authorization_order.py::test_engine_denial_precedes_target_access_for_every_control_operation` | COMPLIANT |
| Administrative resources and bootstrap grants | Bootstrap grants gate administration | `test_demo_seeds.py::test_seed_upgrades_pre_control_plane_graph_additively` plus HTTP acceptance | COMPLIANT |
| Metadata-only terminal audit | Audit store rejects | `test_control_acceptance.py::test_audit_append_failure_suppresses_ordinary_secret` | COMPLIANT |

**Compliance summary**: 11/11 scenarios compliant. The full HTTP acceptance suite validates canonical 2.0.0 schemas for principal, issuance, rotation, list, and error responses; it exercises all eight routes, replay/conflict, revocation, concurrent rotation, audit metadata, and secret-free failure paths.

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|---|---|---|
| Immutable major contract | Implemented | 2.0.0 validates; 1.4.0 has no diff from HEAD. |
| Principal lifecycle | Implemented | Atomic PostgreSQL CAS gives one concurrent winner and stale 409. |
| Credential lifecycle and secrecy | Implemented | Real HTTP/PG evidence covers one-time secrets, replay, revoke, rotation, and rollback. |
| Idempotency and bounded lists | Implemented | PG evidence covers retention, replay, conflict, and concurrent claim convergence. |
| Authentication and engine-delegated authorization | Implemented | Eight-route target-repository trap proves engine evaluation before target access. |
| Administrative resources and bootstrap grants | Implemented | Additive seed upgrade test and control-plane HTTP authorization pass. |
| Metadata-only terminal audit | Implemented | Audit projection and rejection tests retain metadata without secrets. |

### Coherence (Design)
| Decision | Followed? | Notes |
|---|---|---|
| 2.0.0 full immutable snapshot with 1.4.0 retained | Yes | Read-only validators and explicit 1.4.0 HEAD comparison passed. |
| Authenticate, validate, authorize, then target access | Yes | All-eight-route auth-order runtime trap passed. |
| Conditional status write and active-only atomic rotation | Yes | Concurrent PG and rollback/no-mint tests passed. |
| Anonymous pre-auth/validation audit; metadata after authorization | Yes | Acceptance and audit DTO tests passed. |

### Issues Found
**CRITICAL**: None.

**WARNING**: During this verification, an initial mistaken invocation included the mutating `release.mjs evidence --release 2.0.0`; it refreshed mtimes of the already-untracked `conformance/evidence.json` and `manifest.yaml`. Pre-invocation bytes were not snapshotted, so equivalence to the pre-verification candidate cannot be claimed. No restoration or further generator was run. The current complete candidate was then snapshotted and remained byte-identical across the final read-only validation run; all current validators passed. The release projection generator was not a required validator and correctly refuses immutable 2.0.0 regeneration.

**SUGGESTION**: Commit/publish decisions remain outside this verification. The implementation is local and uncommitted; no PR, push, merge, or GitHub publication was performed.

### Verdict
PASS WITH WARNINGS
All 7 requirements and 11 scenarios have independent runtime coverage and passed against the current candidate; the warning is limited to verification-process provenance for the earlier generator invocation.
