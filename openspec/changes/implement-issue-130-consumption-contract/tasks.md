# Tasks: LLM Consumption Contract 2.1.0

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 2,800–3,600 authored lines; non-golden snapshot included |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Bases: PR 1 starts at verified #202 tip; PR 2 bases PR 1; PR 3 bases PR 2; after each merge, rebase next slice onto main.
Unit 3’s indivisible snapshot may exceed 400; native `size:exception-contract-update` applies only there, never runtime/persistence.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Runtime normalization/projection | PR 1 | `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_governance_dto.py tests/test_openrouter.py tests/test_responses.py` | `scripts/worktree-compose --profile issue-14 run --build --rm issue-14-harness` | Revert runtime/test files |
| 2 | Persistence round-trip | PR 2 | `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_persistence_projections.py tests/test_persistence_repositories.py tests/test_migrations.py` | Issue-14 migrated-DB readback | Revert persistence/test files |
| 3 | Immutable release and conformance | PR 3 (`size:exception-contract-update`) | `scripts/worktree-compose --profile checks run --build --rm harness npm --prefix schemas/tooling test` | `scripts/worktree-compose --profile checks run --build --rm harness sh -c 'npm --prefix schemas/tooling run validate:releases && npm --prefix schemas/tooling run lint:openapi'` | Revert snapshot/tooling/test files |

## Phase 1: Integration Gate and RED Tests

- [ ] 1.1 Integrate #202 candidate `2ec6a2f`; preserve shared validation → `authorize_governed_access`, reconcile current main `eb0d1c5` (#229 merged), never restore local auth.
- [ ] 1.2 RED-test `tests/test_governance_dto.py` and `tests/test_openrouter.py` for complete/partial/absent/invalid, exact-decimal/time, invariants, and raw-body exclusion.
- [ ] 1.3 RED-test `tests/test_responses.py`, `tests/test_persistence_projections.py`, and `tests/test_migrations.py` for ordering, zero-call deny, unavailable states, equal projections, and round-trip.
- [ ] 1.4 RED release checks in `schemas/tooling/test/release-validation.test.mjs` and `tests/test_release_metadata.py` for 2.0.0 byte identity and complete 2.1.0 coverage.

## Phase 2: Runtime Contract

- [ ] 2.1 Add closed typed `Consumption` DTO and optional `AuditEvent.consumption` in `src/sre_agent/governance/dto.py`, preserving nullable values and decimal text.
- [ ] 2.2 Extend `src/sre_agent/gateway/providers.py` and `src/sre_agent/gateway/openrouter.py` to normalize validated OpenRouter evidence, preserve failure evidence, and discard raw bodies.
- [ ] 2.3 Wire projection through `src/sre_agent/gateway/responses.py` and `src/sre_agent/gateway/audit.py` while preserving #202 ordering and error taxonomy.

## Phase 3: Persistence and Audit

- [ ] 3.1 Add nullable JSONB consumption to `src/sre_agent/persistence/models.py` and `migrations/versions/20260910_07_add_audit_consumption.py`; keep legacy rows NULL and append-only controls intact.
- [ ] 3.2 Update `src/sre_agent/persistence/repositories.py` and `src/sre_agent/persistence/projections.py` to preserve nulls, decimal text, time, pricing context, and redaction.

## Phase 4: Release and Verification

- [ ] 4.1 Create additive `schemas/releases/2.1.0/`; update 2.1.0 identifiers, schemas, examples, fixtures, manifests, compatibility, and conformance evidence.
- [ ] 4.2 Update `schemas/tooling/lib/release-validation.mjs`, `schemas/tooling/release.mjs`, `src/sre_agent/release.py`, and release tests to discover and validate 2.1.0 and prove 2.0.0 immutability.
- [ ] 4.3 Run focused Python/Node checks and the issue-14 harness; block release if audit commit fails, any state infers zero, or sensitive provider content appears.
- [ ] 4.4 Verify 2.1.0 before issue #129 creates its dependent 2.2.0 catalog snapshot; do not modify the #129 change here.
