# Apply Progress: Governed LLM Responses Vertical Slice

## Execution Summary

- Change: `implement-issue-14-governed-llm`
- Implementation mode: Standard Mode (`strict_tdd: false`)
- Delivery strategy: chained delivery (`ask-on-risk` resolved)
- Chain strategy: `stacked-to-main`
- Current slice: PR 5 — runtime proof, provider-safe Compose wiring, CI ownership, and operator documentation
- Start boundary: PR 4 commit `18db47a` on `feat/issue-14-governed-responses`
- Target while PR 4 is unmerged: `feat/issue-14-governed-responses`
- End boundary: tasks 4.1–4.2 live-smoke gating, deterministic issue-14 harness, readiness/migration/CI wiring, and container-only operator evidence
- Previous apply progress: tasks 1.1–3.3 complete across PRs 1–4; all evidence below is preserved cumulatively

## Completed Tasks

- [x] 1.1 Complete 1.2.0 and RED `latency_ms` tests; copy 21 schemas/OpenAPI docs/examples/fixtures/ADR/conformance/manifest inventories; update release validation.
- [x] 1.2 Add `latency_ms` to DTO; add DTO tests.
- [x] 1.3 Add `latency_ms` to models/projections/repositories and migration/backfill (`0`, `NOT NULL`, `CHECK >= 0`); test persistence.
- [x] 2.1 Write RED `tests/test_openrouter.py` for routing injection, invalid/extra evidence, one request/no fallback, bounded `Retry-After`, and redaction.
- [x] 2.2 Implement bounded provider port/result and direct OpenRouter adapter with pinned async `httpx`, allow-list, timeout taxonomy, and lifecycle injection; refresh `pyproject.toml`/`uv.lock`.
- [x] 3.1 Write PostgreSQL/recording-provider tests for pre-allow denial, correlation/order, missing-resource indistinguishability, closed transactions, and audit-failure suppression.
- [x] 3.2 Implement `responses_router`, normalized outcomes, HMAC metadata-only audit projection, terminal commit gate, latency timer, and application wiring.
- [x] 3.3 Complete allow/deny/failure/readback coverage proving no prompt, output, credential, or HMAC secret persistence.
- [x] 4.1 Add a one-request live gateway smoke that skips without explicit enablement and API-owned provider/audit configuration.
- [x] 4.2 Add provider-safe Compose/runtime wiring, an isolated deterministic issue-14 harness, head readiness, CI ownership, and operator documentation.

## RED Evidence

| Scope | Command | Exact result |
|---|---|---|
| Governance DTO | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_governance_dto.py` | RED: exit 1; `1 failed, 106 passed`; `test_audit_latency_is_additive_and_non_negative` failed because `latency_ms` was forbidden as extra input. |
| Release/tooling support | `docker compose --profile checks run --build --rm harness npm --prefix schemas/tooling test` | RED: exit 1; `2 failed, 65 passed`; 1.2.0 governance and compatibility tests failed because the release did not yet exist. |
| Audit persistence and safe reads | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_migrations.py tests/test_persistence_projections.py tests/test_persistence_repositories.py` | RED: exit 1; `5 failed, 87 passed`; failures proved the missing migration/column, model field, repository latency guard, and authorization-safe read method. |
| OpenRouter provider | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_openrouter.py` | RED: exit 2 during collection; `ModuleNotFoundError: No module named 'sre_agent.gateway.openrouter'`; 1 collection error proved the adapter boundary was absent. |

## Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command and exact result | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_governance_dto.py` — exit 0; `159 passed in 0.15s`. |
| Runtime harness command/scenario and exact result | `docker compose --profile checks run --build --rm harness npm --prefix schemas/tooling run validate:release -- --release 1.2.0` — exit 0; `Validated immutable release 1.2.0: 142 artifacts and 8 checks.` |
| Additional contract tooling proof | `docker compose --profile checks run --build --rm harness npm --prefix schemas/tooling test` — exit 0; `68 passed, 0 failed`. |
| Rollback boundary | Revert `schemas/releases/1.2.0/**`, the 1.2.0 support in `schemas/tooling/{release.mjs,lib/**,test/**}`, `src/sre_agent/governance/dto.py`, and `tests/test_governance_dto.py`. No 1.1.0 release byte or persistence/runtime behavior must be removed. |

## PR 2 Persistence Evidence

| Evidence | Exact result |
|---|---|
| Focused persistence suite | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_migrations.py tests/test_persistence_projections.py tests/test_persistence_repositories.py` — exit 0; `92 passed in 0.62s`. |
| Migration runtime, first run | `docker compose run --rm migrate` — exit 0 against the migrated database. |
| Migration runtime, second run | `docker compose run --rm migrate` — exit 0 again, proving head migration idempotency. |
| Container lint | `docker compose --profile checks run --build --rm python-checks ruff check --no-cache migrations/versions/20260825_02_add_audit_latency.py src/sre_agent/persistence/models.py src/sre_agent/persistence/repositories.py tests/test_migrations.py tests/test_persistence_projections.py tests/test_persistence_repositories.py` — exit 0; `All checks passed!`. |
| Container format | `docker compose --profile checks run --build --rm python-checks ruff format --check --no-cache migrations/versions/20260825_02_add_audit_latency.py src/sre_agent/persistence/models.py src/sre_agent/persistence/repositories.py tests/test_migrations.py tests/test_persistence_projections.py tests/test_persistence_repositories.py` — exit 0; `6 files already formatted`. |
| Diff hygiene | `git diff --check` — exit 0 with no output. |

- Migration `20260825_02` adds nullable `latency_ms`, temporarily removes the append-only trigger, backfills legacy rows to `0`, recreates the trigger, applies `NOT NULL`, and adds `ck_audit_events_latency` (`latency_ms >= 0`) without a server default.
- Migration tests upgrade to `20260822_01`, insert a legacy audit row, upgrade to head twice, verify the backfill and constraints, and confirm append-only enforcement remains active.
- `ResourceRepository.authorization_view()` selects only `resource_type`, `resource_id`, and `status`; captured SQL proves routing fields are absent. `resolve_assignment()` separately selects routing assignment fields only for an active LLM resource, providing the post-allow lookup boundary required by the design.
- Audit persistence rejects DTOs with omitted optional-contract latency before flush; persisted issue-14 audit rows therefore always contain a non-negative integer latency.
- Rollback boundary: revert `20260825_02`, the `AuditEventRow` latency field/check, the repository latency guard and resource read split, plus their three focused test files. Do not revert PR 1 contract release or DTO changes.

## PR 3 Provider Evidence

| Evidence | Exact result |
|---|---|
| Focused adapter suite | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_openrouter.py` — exit 0; `15 passed in 0.44s`. |
| Application regression | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_health.py` — exit 0; `3 passed in 0.43s`. |
| Container lint | `docker compose --profile checks run --build --rm python-checks ruff check --no-cache src/sre_agent/gateway/providers.py src/sre_agent/gateway/openrouter.py src/sre_agent/settings.py src/sre_agent/application.py tests/test_openrouter.py` — exit 0; `All checks passed!`. |
| Container format | `docker compose --profile checks run --build --rm python-checks ruff format --check --no-cache src/sre_agent/gateway/providers.py src/sre_agent/gateway/openrouter.py src/sre_agent/settings.py src/sre_agent/application.py tests/test_openrouter.py` — exit 0; `5 files already formatted`. |
| Lock consistency | `docker compose --profile checks run --build --rm python-checks uv lock --check --no-cache` — exit 0; `Resolved 37 packages in 1ms`. |
| Diff hygiene | `git diff --check` — exit 0 with no output. |

- The adapter issues exactly one non-streaming `POST /api/v1/responses`, enables `X-OpenRouter-Metadata`, uses a single server-selected provider order with fallback and storage disabled, and never interprets provider/model-like text from the client input as routing.
- Successful results require bounded response ID/model/text plus direct, first-attempt metadata with exactly one selected provider/model match; absent, contradictory, or additional selected evidence fails closed.
- Provider failures expose only the bounded taxonomy `evidence_invalid`, `invalid_response`, `unavailable`, or `timeout`; response bodies, transport messages, prompts, and the API key are not propagated. Numeric `Retry-After` is admitted only in the range 1–999999 seconds.
- `OPENROUTER_API_KEY` is optional and secret-safe in settings so existing non-provider startup remains compatible; when configured, the application owns one shared async client at the fixed production origin and closes it during shutdown.
- Runtime harness: N/A. `httpx.MockTransport` exercises the exact request, routing evidence, one-call behavior, taxonomy, redaction, and shared-client lifecycle deterministically; this slice is not permitted a provider secret or network call.
- Lock refresh command: `docker compose --profile checks run --build --rm --user 1000:1000 -v /home/creep/Documents/Codex/2026-08-25/im/work/sre-agent:/workspace -w /workspace python-checks uv lock --no-cache` — exit 0; `Resolved 37 packages in 1.53s`.
- Rollback boundary: revert `src/sre_agent/gateway/{providers,openrouter}.py`, `tests/test_openrouter.py`, compatible provider settings/application lifecycle wiring, and the `pyproject.toml`/`uv.lock` runtime dependency change. Do not revert PR 1 contract/DTO or PR 2 persistence changes.

## PR 4 Governed Gateway and Audit Evidence

| Evidence | Exact result |
|---|---|
| Focused gateway/audit suite | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_responses.py tests/test_audit.py` — exit 0; `12 passed in 1.13s`. |
| Auth/provider/persistence/health regressions | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_authentication.py tests/test_openrouter.py tests/test_persistence_projections.py tests/test_persistence_repositories.py tests/test_api_key_persistence.py tests/test_health.py` — exit 0; `118 passed in 1.18s`. |
| Container lint | `docker compose --profile checks run --build --rm python-checks ruff check --no-cache src/sre_agent/gateway/audit.py src/sre_agent/gateway/responses.py src/sre_agent/application.py src/sre_agent/settings.py tests/test_audit.py tests/test_responses.py` — exit 0; `All checks passed!`. |
| Container format | `docker compose --profile checks run --build --rm python-checks ruff format --check --no-cache src/sre_agent/gateway/audit.py src/sre_agent/gateway/responses.py src/sre_agent/application.py src/sre_agent/settings.py tests/test_audit.py tests/test_responses.py` — exit 0; `6 files already formatted`. |
| Available runtime harness | `docker compose --profile harness run --build --rm harness` — exit 0; `Validated issue-10 via fixtures-transport.` The current harness is not yet issue-14-aware; that wiring remains task 4.2. |
| Diff hygiene | `git diff --check` — exit 0 with no output. |
| Rollback boundary | Revert `src/sre_agent/gateway/{audit,responses}.py`, `tests/test_{audit,responses}.py`, and the PR 4 additions in `src/sre_agent/{application,settings}.py`. Preserve PRs 1–3 contracts, persistence, provider adapter, and provider lifecycle wiring. |

- Validation and authentication failures commit terminal metadata and perform zero provider calls; client-supplied provider routing is rejected with 422.
- Missing and inactive logical resources are externally indistinguishable from a missing grant: all return 403 `resource_unavailable`, omit routing evidence, and make zero provider calls.
- The allow path resolves assignment only after authorization, closes governance reads before the single provider call, normalizes provider failures without fallback, and commits audit evidence before releasing the intended response.
- Audit-store failure suppresses both intended 200 and 403 outcomes with retryable 503 `audit_unavailable`.
- Audit readback contains HMAC-projected identity/resource/routing metadata and non-negative `latency_ms`; prompt, output, API credentials, and the HMAC secret are absent. One server-generated `request_id` correlates the HTTP response and audit event.
- Standard Mode RED note: the interrupted candidate already contained the mapped threat tests and implementation, but no trustworthy pre-implementation failing command result survived the interruption. Recovery preserved the applicable tests and verified their GREEN result rather than fabricating RED evidence.

## PR 5 Runtime Proof and Documentation Evidence

| Evidence | Exact result |
|---|---|
| Focused live-smoke default gate | `docker compose --profile checks run --build --rm python-checks pytest -q tests/test_openrouter_live.py tests/test_harness_runtime.py` — exit 0; `4 passed, 1 skipped in 0.06s`; no live provider request was enabled. |
| Focused live-smoke missing-secret gate | `docker compose --profile checks run --rm -e RUN_OPENROUTER_LIVE_SMOKE=1 python-checks pytest -q tests/test_openrouter_live.py` — exit 0; `1 skipped in 0.05s`; explicit enablement without the API secret-presence flag still made no provider request. |
| Deterministic issue-14 runtime harness | `docker compose --profile issue-14 run --build --rm issue-14-harness` — exit 0; `11 passed in 1.06s`; isolated PostgreSQL plus the recording provider proved allow, deny, zero-call, normalized failures, audit protection, and release gating. |
| Complete Python/container gate | `docker compose --profile checks run --build --rm python-checks` — exit 0; Ruff passed, `64 files already formatted`, lock resolved, `308 passed, 1 skipped in 2.61s`, and `alembic check` reported no new upgrade operations. |
| Complete contract/tooling gate | One Compose harness run executed tooling tests, canonical validation, immutable release validation for 1.0.0/1.1.0/1.2.0, both OpenAPI checks, issue-10/11/13/14 conformance, and JavaScript syntax — exit 0; `68 passed, 0 failed`; 1.2.0 validated `142 artifacts and 8 checks`; issue-14 validated via `ordered-responses`. |
| Migration and readiness | `docker compose run --rm migrate && docker compose run --rm migrate` — exit 0 twice. A fresh isolated `docker compose ... up --build --wait` reached healthy PostgreSQL, API, and web after migrate/seed, proving readiness expects head `20260825_02`. |
| Compose harness smoke | The fresh isolated stack ran the existing issue-10 harness (`Validated issue-10 via fixtures-transport`) and the issue-14 recording-provider harness (`11 passed in 1.33s`) before its disposable volume was removed. |
| Diff hygiene and budget | `git diff --check` plus trailing-whitespace inspection of the untracked live test — exit 0. PR5 authored source/test/config/docs scope is 210 changed lines against `18db47a`, excluding OpenSpec planning/progress artifacts. |
| Rollback boundary | Revert `tests/test_openrouter_live.py`, `tests/test_harness_runtime.py`, `compose.yaml`, `.env.example`, `.github/workflows/ci.yml`, `README.md`, `docs/architecture.md`, and the readiness-head change in `src/sre_agent/gateway/health.py`. Preserve PRs 1–4 contracts, migration, provider, gateway, and audit behavior. |

- Compose passes `OPENROUTER_API_KEY`, its timeout, and `AUDIT_HMAC_KEY` only to `api`; seed uses an explicit bootstrap-variable allow-list, while deterministic and live-smoke client containers never receive the provider credential.
- `tests/test_openrouter_live.py` makes one client request through the complete API only when the operator enable flag and safe provider/audit presence flags are set. It asserts the closed normalized envelope, UUID correlation, protected routing metadata, and bounded text without inspecting provider bodies or raw audit rows.
- Ordinary CI explicitly ignores the live test, owns immutable 1.2.0 and issue-14 conformance, runs governed response/audit tests against PostgreSQL, and executes the isolated recording-provider harness in Compose smoke.
- Live provider traffic was N/A for this apply: no operator provider secret was available, so both focused paths correctly skipped and made zero upstream calls. A real request remains an explicit operator-only smoke, never an ordinary CI prerequisite.

## Release Evidence

- The immutable manifest reports version `1.2.0`, additive baseline `1.1.0`, 21 JSON Schemas, two OpenAPI documents, ten examples, 97 fixture files, six ADR inventory entries, and six conformance artifacts.
- All 21 schema IDs use `:1.2.0`; the only remaining `1.1.0` references in the new release are the required previous-release baseline and compatibility evidence.
- `latency_ms` is optional-additive in the schema and DTO, bounded to integer `0..2147483647`, and present in 1.2.0 audit examples plus positive/negative fixtures.
- `git diff --exit-code -- schemas/releases/1.1.0` passed, proving the prior immutable release remains unchanged.

## Review Workload

- Authored tracked implementation/tooling/tests outside the release snapshot: 46 changed lines (39 additions, 7 deletions).
- Copied/generated 1.2.0 snapshot: 137 files, 1,027 lines, approximately 672 KiB; reported separately from the authored review budget.
- Semantic latency evidence inside the snapshot is concentrated in the audit-event schema, six audit examples, the issue-14 positive fixture, and one negative latency fixture; generated projections/evidence/manifest bind the complete snapshot.
- OpenSpec planning/progress artifacts are excluded from the implementation line counts above.
- PR 2 authored persistence/tests: 229 changed lines (218 additions, 11 deletions), including the 26-line migration; below the 400-line review budget.
- PR 3 authored provider/settings/dependency/tests: exactly 400 changed lines (346 lines in new files plus 54 additions/deletions in tracked files); OpenSpec planning/progress artifacts excluded. The slice meets, but does not exceed, the 400-line review budget.
- PR 4 authored gateway/audit/application/tests: exactly 400 changed lines (399 additions, 1 deletion) against parent commit `86afb5a`; OpenSpec planning/progress artifacts excluded. The slice meets, but does not exceed, the 400-line review budget.
- PR 5 authored runtime/test/config/docs: 210 changed lines (197 additions, 13 deletions) against parent commit `18db47a`; OpenSpec planning/progress artifacts excluded. The final slice remains below the 400-line review budget.

## Deviations

No scope deviations. The projection helper already copies every declared `AuditEvent` DTO field, so task 1.3 required projection regression coverage rather than redundant production projection code. Ruff's default cache failed in the read-only container mount; the required container checks passed with `--no-cache`. The PR 3 RED tests exercise adapter validation/failure types rather than public 422/502 mappings because the HTTP route is explicitly reserved for tasks 3.1–3.3. The production OpenRouter origin is fixed rather than user-configurable, reducing misrouting surface and keeping settings within the provider boundary. Source-mutating `uv lock` and Ruff formatting used a writable repository bind with host UID while still running only inside Docker Compose. A local ignored `.env` continued to isolate the Compose project name and host PostgreSQL port; no repository runtime configuration changed. The existing runtime harness still validates issue 10 and cannot prove the issue-14 response path until task 4.2; PR 4 therefore relies on its real PostgreSQL/TestClient gateway suite for runtime-boundary proof. The interrupted executor left no trustworthy pre-implementation RED command output for tasks 3.1–3.3, so recovery records that limitation explicitly instead of inventing a receipt. The first PR5 stack smoke used the ignored local `.env` and stopped safely at seed validation because it still contained nonfunctional API-key placeholders; the authoritative smoke retry used a fresh temporary Compose project with valid disposable seed values and removed its volume afterward. No provider secret was supplied, so the live request remained an intentional skip rather than fabricated evidence.

## Remaining Tasks

None. Tasks 1.1–4.2 are complete; independent SDD verification remains outside this apply phase.

## Status

10 of 10 tasks complete. PR slice 5 is ready for orchestrator gatekeeping and independent `sdd-verify`.
