# Tasks: Governed LLM Responses Vertical Slice

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 900–1,300 authored lines plus 1.2.0 snapshot |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 contracts/DTO → PR 2 persistence → PR 3 provider → PR 4 gateway/audit → PR 5 runtime/docs |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Release 1.2.0 and latency DTO | PR 1 | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_governance_dto.py` | `docker compose --profile checks run --build --rm harness npm --prefix schemas/tooling run validate:release -- --release 1.2.0` | Revert release snapshot/tooling and `governance/dto.py` |
| 2 | Latency migration and projections | PR 2 | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_migrations.py tests/test_persistence_projections.py tests/test_persistence_repositories.py` | `docker compose run --rm migrate` twice | Revert migration/models/projections/repositories |
| 3 | OpenRouter adapter | PR 3 | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_openrouter.py` | N/A: adapter is mocked; no provider secret/network | Revert provider files, settings, lock wiring |
| 4 | Ordered route, audit gate | PR 4 | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_responses.py tests/test_audit.py` | `docker compose --profile harness run --rm harness` | Revert gateway/audit and response route |
| 5 | Compose, smoke, CI/docs | PR 5 | `docker compose --profile checks run --build --rm python-checks` | `docker compose up --build --wait` then harness profile | Revert compose/workflow/docs/smoke |

## Phase 1: Contract and Persistence Foundation

- [x] 1.1 Complete 1.2.0 and RED `latency_ms` tests; copy 21 schemas/OpenAPI docs/examples/fixtures/ADR/conformance/manifest inventories; update release validation.
- [x] 1.2 Add `latency_ms` to DTO; add DTO tests.
- [x] 1.3 Add `latency_ms` to models/projections/repositories and migration/backfill (`0`, `NOT NULL`, `CHECK >= 0`); test persistence.

## Phase 2: Provider Boundary (RED → GREEN)

- [x] 2.1 Write RED `tests/test_openrouter.py` for routing injection (422), invalid/extra evidence (502), one request/no fallback, bounded `Retry-After`, and redaction.
- [x] 2.2 Implement bounded provider port/result and OpenRouter adapter with pinned async `httpx`, metadata-only request, allow-list, timeout taxonomy, lifecycle injection; refresh `pyproject.toml`/`uv.lock`.

## Phase 3: Governed Gateway and Audit (RED → GREEN)

- [x] 3.1 Write RED PostgreSQL/recording-provider tests for pre-allow denial (zero calls), correlation/order, missing-resource indistinguishability, closed transactions, and audit-failure suppression.
- [x] 3.2 Implement `responses_router`, normalization/errors, separated safe reads, HMAC `AuditProjector` (`content_state=absent`), terminal commit gate, latency timer, and application wiring.
- [x] 3.3 Complete allow/deny/failure/readback tests; assert no prompt, output, or provider-secret persistence.

## Phase 4: Runtime Proof and Documentation

- [x] 4.1 Add one-request secret-gated `tests/test_openrouter_live.py`; skip without enablement/secrets and assert normalized response/protected metadata only.
- [x] 4.2 Update Compose/env/CI/README/architecture for provider settings, issue-14 harness, migration/readiness, CI ownership, and container-only commands; run checks, release validation, conformance, Compose smoke, and diff hygiene.
