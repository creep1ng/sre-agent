# Apply Progress: LLM Consumption Contract 2.1.0

## Execution Summary

- Change: `implement-issue-130-consumption-contract`
- Implementation mode: Standard Mode (`strict_tdd: false`; repository config does not enable strict TDD).
- Delivery strategy: auto-chain
- Chain strategy: stacked-to-main
- Current cumulative scope: foundation/readiness, provider, billing, active-contract parity, immutable 2.1 snapshot/tooling, DTO OpenAPI parity, response/audit, and runtime 2.1 activation are published and evidenced; independent SDD verification remains pending.
- Stack boundaries: planning PR241 -> foundation PR242 (`8171c80`) -> provider PR243 (`dd124a0`) -> billing PR244 (`17fbd56`) -> active parity PR245 (`5bd4f484`) -> contract PR246 (`0af00af8`; identical-schema validation ref `8c77241`) -> DTO OpenAPI PR247 (`7767f15`) -> runtime activation PR248 (final `6cfb2ef`) -> independent verify -> issue #129 contract-only 2.2.
- End boundary: all 14 apply tasks are complete through runtime 2.1 activation and final archive checks; candidate handoff is prepared, but independent SDD verification has not run and #129 remains blocked.
- Review split: local provider checkpoints `cdb5f8a`, `871f17f`, and `44ffe0b` are historical pre-split checkpoints, not published PR boundaries. The published stack now references foundation `8171c80`, provider `dd124a0`, billing `17fbd56`, active parity `5bd4f484`, contract `0af00af8`, DTO parity `7767f15`, and final activation head `6cfb2ef`; earlier checkpoints remain historical and parent owns final ancestry. The `_json_body`/precision boundary and one focused test may move into the foundation without behavior changes or code golf. The size exception is limited to the immutable contract snapshot/tooling slice.



## Published Stack Evidence (v4)

The current published stack is planning PR241 -> foundation PR242 -> provider PR243 -> billing PR244 -> active-contract parity PR245 -> contract snapshot/tooling PR246 -> runtime activation -> independent verification -> issue #129 contract-only 2.2. The v3 section below is retained unchanged as historical evidence.

- Foundation PR242: `8171c80`, 358 authored lines; readiness correction evidence `/tmp/sdd-apply-130-readiness-result.md` records four focused health tests and real Compose healthy; no size exception.
- Provider PR243: `dd124a0`, 394 authored lines; prior full archive `/tmp/issue130-provider-full-check-v3.log` records 794 passed, 1 skipped; no size exception.
- Billing PR244: `17fbd56`, 59 authored lines; `/tmp/sdd-apply-130-billing-context-fix-result.md` and `/tmp/issue130-billing-full-check.log` record 797 passed, 1 skipped; no size exception.
- Active-contract parity PR245: `5bd4f484`, 31 authored lines; `/tmp/sdd-apply-130-activation-result.md` and `/tmp/issue130-selection-full-check.log` record 797 passed, 1 skipped; runtime remains explicitly 2.0.0.
- Contract PR246: `0af00af8`, 4,227 authored lines across 170 files, label `size:exception-contract-update`; `/tmp/sdd-apply-130-contract-result.md` records validation on identical-schema ref `8c77241`: 797 Python passed, 1 skipped, 78 Node tests, all-release validation, OpenAPI lint, and issue-130 conformance passed. This exception applies only to the immutable contract snapshot/tooling.
- DTO OpenAPI PR247: `7767f15`, 143 authored lines; `/tmp/sdd-apply-130-dto-openapi-result.md` records 294 focused Docker checks plus Ruff and mypy passes; `/tmp/issue130-dto-full-check.log` records 798 Python passed, 1 skipped.
- Response/audit activation PR248: implementation source `551fe577` (270-line slice), final format-corrected head `6cfb2ef` (268 authored lines); `/tmp/sdd-apply-130-activation-final-result.md` records 8 release/OpenAPI and 29 issue-14 checks; `/tmp/issue130-activation-full-check-v2.log` records 801 Python passed, 1 skipped and ends with no new upgrade operations.
- Candidate handoff is prepared but independent verification is pending; `/tmp/sdd-apply-130-activation-prep-result.md` remains historical preparation evidence and #129 stays blocked.

## Stacked Delivery and Evidence Archive (v3)

The delivery order is planning PR241 -> foundation PR242 -> provider PR243 -> contract 2.1 snapshot/tooling -> response/audit + release activation 2.1 -> independent verification -> issue #129 2.2. Earlier local checkpoints remain historical and are not PR boundaries.

- Foundation PR242: source `a84d26d`, 350 authored lines, 786 passed / 1 skipped; full archive `/tmp/issue130-foundation-full-check-v3.log`.
- Provider PR243: source `a1550da`, image-only candidate head `5cff7b`, 394 authored lines, 794 passed / 1 skipped; full archive `/tmp/issue130-provider-full-check-v3.log`.
- Persistence focused evidence: `/tmp/sdd-apply-130-persistence-result.md` (159 passed) and `/tmp/sdd-apply-130-persistence-format-result.md` (Ruff formatter root cause and two-file fix).
- Response/audit focused evidence: `/tmp/sdd-apply-130-response-result.md` (29 runtime and 292 DTO/audit checks).
- Provider focused evidence: `/tmp/sdd-apply-130-provider-result.md`.
- Migration regression evidence: `/tmp/sdd-apply-130-migration-regression-result.md` (stale upgrade-head assertion corrected from `20260907_06` to `20260910_07`; 12 passed).
- Prior cumulative envelope: `/tmp/sdd-apply-130-progress-result.md`; these earlier checkpoints are historical, not final PR boundaries.

## Completed Tasks

- [x] 1.1 Integrate the verified #202 baseline. Preserve validation → `authorize_governed_access`, reconcile current main `eb0d1c5` (#229 merged), and never restore local auth. Verification report `c7e1688` recorded 773 passed and 1 skipped on inherited baseline `aa1b4c8`.
- [x] 1.2 Add focused provider contract/adapter coverage for complete, partial, absent, unavailable, malformed, exact-decimal, timestamp, invariant, failure, and raw-body exclusion behavior.
- [x] 1.3 Add response, persistence, and migration RED/GREEN coverage for ordering, zero-call denial, unavailable states, equal projections, exact round-trip, legacy NULL rows, and append-only protection.
- [x] 1.4 Add release RED coverage; PR245/PR246 published the byte-identity, active-snapshot, and 2.1.0 coverage gates.
- [x] 2.1 Add the closed `Consumption` DTO, `PricingContext`, optional `AuditEvent.consumption`, and deny-with-consumption rejection.
- [x] 2.2 Extend `ProviderResult`/`ProviderFailure` and normalize OpenRouter usage/cost evidence without retaining raw bodies.
- [x] 2.3 Wire the same normalized projection through Responses and audit while preserving #202 ordering and error taxonomy.
- [x] 3.1 Add nullable JSONB consumption storage and migration `20260910_07`; keep legacy rows NULL and append-only controls intact.
- [x] 3.2 Preserve nulls, exact decimal text, timestamps, pricing context, and redaction through the existing repository model-dump and field-driven projection paths.
- [x] 4.0 Add the active-contract parity boundary; PR245 `5bd4f484` selects explicit runtime `CONTRACT_VERSION` and validates the matching published snapshot while runtime remains 2.0.0.
- [x] 4.1 Create and validate the additive 2.1.0 snapshot/tooling; PR246 `0af00af8` carries the scoped `size:exception-contract-update` and its validation ref `8c77241` is schema-identical.
- [x] 4.2 Apply runtime release activation/version discovery and metadata checks; final activation head is PR248 `6cfb2ef`.
- [x] 4.3 Run integrated Python/Node/Compose checks, including issue-14; PR248 full archive records 801 passed, 1 skipped.
- [x] 4.4 Prepare the active-2.1.0 candidate and independent-verification handoff; independent verification is pending and #129 remains blocked.

## Notes and Decisions

- OpenRouter `usage` is the sole provider evidence source. Token values are strict non-negative integers; no missing value is inferred as zero.
- JSON is parsed from raw response bytes with `Decimal` float parsing so numeric cost text such as `0.0012300` remains exact. Decimal fixed-length bounds are checked from digits/exponent before formatting to reject extreme exponents without allocating huge strings.
- Complete cost evidence receives `currency=USD`, `precision=exact`, and a `PricingContext` based on the provider `created_at` observation timestamp. Missing or malformed context leaves a partial projection.
- Successful responses without usage are `absent`; provider failures without usable evidence are `unavailable`. Valid failure evidence is retained only as the normalized DTO.
- Unknown provider-body fields and secrets are never copied into `ProviderResult`, `ProviderFailure`, public response metadata, or audit metadata.
- The persistence migration is additive: legacy audit rows retain `consumption=NULL`, and the existing append-only trigger is untouched. Existing generic repository serialization and projection are reused rather than duplicated.
- Response and audit use the same normalized `Consumption` object. Denials remain provider-call-free and consumption-free; audit failure still suppresses release.
- Task 4.4 is an apply handoff: complete candidate/evidence preparation may finish the apply ledger, while mandatory independent SDD verification remains a separate gate before #129 is unblocked; this avoids a circular apply/verify dependency.
- The immutable 2.1 snapshot/tooling, DTO OpenAPI parity, runtime 2.1 activation, and issue-14/integrated archive checks are complete through PR248. Candidate handoff is pending independent SDD verification; do not claim independent verification or unblock #129.


## Final Handoff Evidence

| Unit | Published source | Evidence |
|---|---|---|
| DTO OpenAPI parity | PR247 `7767f15`, 143 lines | 294 focused Docker checks, Ruff, and mypy passed; full archive `/tmp/issue130-dto-full-check.log`: 798 passed, 1 skipped. |
| Response/audit + runtime activation | PR248 final `6cfb2ef`, 268 lines; implementation `551fe577`, 270-line predecessor | 8 release/OpenAPI checks and 29 issue-14 checks passed; full archive `/tmp/issue130-activation-full-check-v2.log`: 801 passed, 1 skipped; `No new upgrade operations detected`. |
| Handoff gate | Candidate active contract 2.1.0 | Apply is complete; independent SDD verification is not complete, so #129 remains blocked. |

## Work Unit Evidence

### Provider / DTO normalization

| Evidence | Exact result |
|---|---|
| Focused tests | `docker compose -p issue130-provider --profile checks run --build --rm --no-deps python-checks pytest -q tests/test_governance_dto.py tests/test_openrouter.py` — exit 0; **324 passed** in 1.38s. |
| Container lint | `docker compose -p issue130-provider --profile checks run --build --rm --no-deps -e RUFF_CACHE_DIR=/tmp/ruff-cache python-checks ruff check --no-cache src/sre_agent/governance/dto.py src/sre_agent/gateway/providers.py src/sre_agent/gateway/openrouter.py tests/test_governance_dto.py tests/test_openrouter.py` — exit 0; all checks passed. |
| Container format | `docker compose -p issue130-provider --profile checks run --build --rm --no-deps -e RUFF_CACHE_DIR=/tmp/ruff-cache python-checks ruff format --check src/sre_agent/governance/dto.py src/sre_agent/gateway/providers.py src/sre_agent/gateway/openrouter.py tests/test_governance_dto.py tests/test_openrouter.py` — exit 0; 5 files already formatted. |
| Static typing | `docker compose -p issue130-provider --profile checks run --build --rm --no-deps -e MYPY_CACHE_DIR=/tmp/mypy python-checks mypy --cache-dir=/tmp/mypy src/sre_agent/governance/dto.py src/sre_agent/gateway/providers.py src/sre_agent/gateway/openrouter.py` — exit 0; no issues in 3 source files. |
| Runtime harness | N/A — `httpx.MockTransport` covers the adapter boundary; response/audit runtime evidence is recorded below. |
| Rollback boundary | Revert `src/sre_agent/governance/dto.py`, `src/sre_agent/gateway/providers.py`, `src/sre_agent/gateway/openrouter.py`, `tests/test_governance_dto.py`, and `tests/test_openrouter.py`. |

### Response / audit projection

| Evidence | Exact result |
|---|---|
| Runtime harness | `docker compose -p issue130-response --env-file /tmp/sre-agent-38f2.env -f compose.yaml --profile issue-14 run --build --rm issue-14-harness pytest -q tests/test_responses.py` — **29 passed**. |
| DTO/audit tests | `UV_PROJECT_ENVIRONMENT=/tmp/sre-agent-38f2-venv UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run --extra dev pytest -q -p no:cacheprovider tests/test_audit.py tests/test_governance_dto.py` — **292 passed**. |
| Lint | Response/audit Ruff check — all checks passed. |
| Expected pending check | `tests/test_responses_openapi.py` has 1 expected parity failure until the 2.1.0 schema snapshot exists. |
| Rollback boundary | Revert `src/sre_agent/gateway/responses.py`, `src/sre_agent/gateway/audit.py`, and `tests/test_responses.py`; leave provider, DTO, persistence, migration, and release work independent. |

### Persistence / migration

| Evidence | Exact result |
|---|---|
| Focused tests and runtime | `docker compose --project-name issue130-persistence --env-file .env.example --profile checks -f compose.yaml run --build --rm python-checks pytest -q tests/test_persistence_projections.py tests/test_persistence_repositories.py tests/test_migrations.py` — isolated PostgreSQL migration/readback harness; **159 passed** in 1.46s. |
| Lint | Ruff on assigned persistence, migration, and test paths — all checks passed. |
| Coverage | Complete evidence round-trips with exact `billed_usd`, timestamps, pricing context, denial NULLs, legacy NULL rows, and append-only UPDATE rejection. |
| Rollback boundary | Revert `src/sre_agent/persistence/models.py`, `migrations/versions/20260910_07_add_audit_consumption.py`, `tests/test_persistence_projections.py`, `tests/test_persistence_repositories.py`, and `tests/test_migrations.py`. |

## RED Evidence

Standard Mode is active because repository testing configuration resolves `strict_tdd: false`; no strict RED/GREEN/REFACTOR ledger is required. Release RED coverage, 2.1 snapshot/tooling, runtime 2.1 activation, and issue-14/integrated checks are complete; independent SDD verification remains a separate mandatory gate.

## Remaining Tasks

- Independent `sdd-verify` remains pending for the completed 14-task apply candidate.
- Issue #129 remains blocked until independent verification passes.

## Status

14/14 apply tasks complete (13 original IDs plus new 4.0). Runtime 2.1 is active and full archive checks pass; candidate handoff is pending independent SDD verification, which is not claimed here. Issue #129 remains blocked.
