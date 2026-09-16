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

Stack: planning PR241 -> foundation PR242 (`8171c80`) -> provider PR243 (`dd124a0`) -> billing correction PR244 (`17fbd56`) -> active-contract parity PR245 (`5bd4f484`) -> contract snapshot/tooling PR246 (`0af00af8`) -> DTO OpenAPI parity PR247 (`7767f15`) -> response/audit + runtime activation PR248 (final `6cfb2ef`) -> independent verify -> issue #129 contract-only 2.2.
Unit 3’s indivisible snapshot may exceed 400; native `size:exception-contract-update` applies only there, never runtime/persistence.

### Suggested Work Units

| Order | Deliverable | Stack / evidence | Boundary |
| --- | --- | --- | --- |
| 0 | Planning | PR241; establishes the verified #202 baseline | Historical planning only |
| 1 | Foundation + readiness follow-up | PR242 -> `main`; source `8171c80`; 358 authored lines; readiness four focused tests plus real Compose healthy (`/tmp/sdd-apply-130-readiness-result.md`) | Runtime/persistence/health; no size exception |
| 2 | Provider | PR243 -> PR242; source `dd124a0`; 394 authored lines; provider full evidence remains 794 passed, 1 skipped | Runtime/provider; no size exception |
| 2a | Corrective billing context | PR244 -> PR243; source `17fbd56`; 59 authored lines; full Python evidence 797 passed, 1 skipped | Runtime/provider contract parity; no size exception |
| 2b | Active-contract parity boundary | PR245 -> PR244; source `5bd4f484`; 31 authored lines; full Python evidence 797 passed, 1 skipped; runtime remains explicitly 2.0.0 | Test/tooling boundary only; no size exception |
| 3 | Contract | PR246 -> PR245; source `0af00af8`; 4,227 authored lines / 170 files; validation ref `8c77241` has identical schemas, 797 Python passed + 1 skipped and 78 Node/all-release/lint/conformance checks | `size:exception-contract-update` applies only here; rollback snapshot/tooling paths |
| 3a | DTO OpenAPI parity | PR247 -> PR246; source `7767f15`; 143 authored lines; 294 focused Docker checks plus Ruff and mypy passed; full archive 798 passed, 1 skipped | Generated schema parity; no size exception |
| 4 | Response + audit / activation | PR248 -> PR247; implementation `551fe577`, final format-corrected head `6cfb2ef`; 268 final authored lines; 8 release/OpenAPI and 29 issue-14 checks; full archive 801 passed, 1 skipped | Runtime 2.1 activation; no size exception |
| 5 | Independent verify | SDD verification of the integrated stack | Verification-only; not yet run |
| 6 | Issue #129 | Dependent contract-only 2.2 catalog work after independent verification | Blocked until independent verification passes |

## Phase 1: Integration Gate and RED Tests

- [x] 1.1 Integrate #202 candidate `2ec6a2f`; preserve shared validation → `authorize_governed_access`, reconcile current main `eb0d1c5` (#229 merged), never restore local auth. Verified on inherited baseline `aa1b4c8` with report `c7e1688` (773 passed, 1 skipped).
- [x] 1.2 RED-test `tests/test_governance_dto.py` and `tests/test_openrouter.py` for complete/partial/absent/invalid, exact-decimal/time, invariants, and raw-body exclusion.
- [x] 1.3 RED-test `tests/test_responses.py`, `tests/test_persistence_projections.py`, and `tests/test_migrations.py` for ordering, zero-call deny, unavailable states, equal projections, and round-trip.
- [x] 1.4 RED release checks in `schemas/tooling/test/release-validation.test.mjs` and `tests/test_release_metadata.py` for 2.0.0 byte identity, complete 2.1.0 coverage, and explicit active-snapshot selection; published with the PR245/PR246 contract gates.

## Phase 2: Runtime Contract

- [x] 2.1 Add closed typed `Consumption` DTO and optional `AuditEvent.consumption` in `src/sre_agent/governance/dto.py`, preserving nullable values and decimal text.
- [x] 2.2 Extend `src/sre_agent/gateway/providers.py` and `src/sre_agent/gateway/openrouter.py` to normalize validated OpenRouter evidence, preserve failure evidence, and discard raw bodies.
- [x] 2.3 Wire projection through `src/sre_agent/gateway/responses.py` and `src/sre_agent/gateway/audit.py` while preserving #202 ordering and error taxonomy.

## Phase 3: Persistence and Audit

- [x] 3.1 Add nullable JSONB consumption to `src/sre_agent/persistence/models.py` and `migrations/versions/20260910_07_add_audit_consumption.py`; keep legacy rows NULL and append-only controls intact.
- [x] 3.2 Update `src/sre_agent/persistence/repositories.py` and `src/sre_agent/persistence/projections.py` to preserve nulls, decimal text, time, pricing context, and redaction.

## Phase 4: Release and Verification

- [x] 4.0 Add the prerequisite active-contract parity boundary before the 2.1 snapshot: select explicit runtime `CONTRACT_VERSION`, require the matching published snapshot/manifest, and prove a staged higher snapshot does not change runtime OpenAPI selection; delivered by PR245 `5bd4f484` without activating 2.1.
- [x] 4.1 Create additive `schemas/releases/2.1.0/`; update 2.1.0 identifiers, schemas, examples, fixtures, manifests, compatibility, and conformance evidence; delivered by PR246 `0af00af8` under `size:exception-contract-update`.
- [x] 4.2 Update release tooling/runtime version discovery and metadata checks to use explicit active `CONTRACT_VERSION`; delivered through PR247 `7767f15` and PR248 final `6cfb2ef`.
- [x] 4.3 Run focused Python/Node checks and the issue-14 harness; PR248 full archive records 801 passed, 1 skipped, with 8 release/OpenAPI checks and 29 issue-14 checks passing.
- [x] 4.4 Prepare the complete 2.1.0 candidate and handoff evidence for independent SDD verification; final integrated runtime active contract is 2.1.0. Independent verification is still pending, so issue #129 remains blocked and may later add only a contract-only 2.2.0 snapshot/tooling slice.
