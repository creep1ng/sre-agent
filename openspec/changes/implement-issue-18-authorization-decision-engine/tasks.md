# Tasks: Implement Reusable Authorization Decision Engine

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 650–850 authored lines (including contract fixtures and migration) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 stable SDD contract → PR 2 engine authority → PR 3 audit 1.3.0/persistence → PR 4 Responses integration and repository decision removal |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Engine authority, typed facts/result, deterministic precedence | PR 2 | `uv run pytest tests/test_authorization.py -q` | N/A: pure governance | Revert `authorization.py` and engine tests only |
| 2 | Audit-only cause contract, migration, projection/readback, release 1.3.0 | PR 3 | `uv run pytest tests/test_governance_dto.py tests/test_audit.py tests/test_persistence_projections.py tests/test_migrations.py -q` | `docker compose --profile checks run --build --rm python-checks` | Revert DTO/model/migration/audit and `schemas/releases/1.3.0/**` |
| 3 | Responses wiring, non-enumeration, and remaining repository decision removal | PR 4 | `uv run pytest tests/test_responses.py -q` | `docker compose --profile issue-14 run --build --rm issue-14-harness` (403 deny has zero routing/provider calls) | Revert gateway/application integration and response tests |

## Phase 1: RED — Contract and Threat Tests

- [x] 1.1 Add failing `tests/test_authorization.py` table tests for human/agent parity, every `ResourceType`, exact active allow, revoked/mismatched deny, inactive-principal/resource precedence, short-circuit reader calls, and rejection of role/name/model/YAML inputs.
- [x] 1.2 Add failing audit/DTO/projection/migration tests in `tests/test_governance_dto.py`, `tests/test_audit.py`, `tests/test_persistence_projections.py`, and `tests/test_migrations.py` for nullable historical causes, closed values, stage/decision consistency, invalid-row checks, and 1.3 readback.
- [ ] 1.3 Add failing `tests/test_responses.py` spies for authorization-before-routing, zero assignment/provider access on every deny, uniform 403/non-enumeration, ordinary-log/API cause absence, and exact audit cause population.

## Phase 2: GREEN — Authority and Persistence

- [x] 2.1 Create `src/sre_agent/governance/authorization.py` with typed fact-reader protocols, `ResourceAuthorizationFact`, closed denial taxonomy, frozen `AuthorizationEvaluation`, precedence, and sole `PolicyDecision` construction.
- [ ] 2.2 PR 4: update `src/sre_agent/persistence/repositories.py` to expose authorization facts, retain exact `find_active()`, and remove/narrow `GrantRepository.decide()` after Responses migrates to the engine.
- [x] 2.3 Update `src/sre_agent/governance/dto.py`, `src/sre_agent/persistence/models.py`, `src/sre_agent/persistence/projections.py`, `src/sre_agent/gateway/audit.py`, and `migrations/versions/20260901_03_add_authorization_denial_cause.py`; add nullable `varchar(32)` plus closed check constraint and legacy-compatible readback.
- [x] 2.4 Add immutable `schemas/releases/1.3.0/**` audit contract, fixtures, compatibility/evidence/manifest, leaving public `PolicyDecision` and API deny envelopes unchanged.

## Phase 3: GREEN — Responses Integration

- [ ] 3.1 Wire `src/sre_agent/gateway/responses.py` and `src/sre_agent/application.py` to evaluate once before assignment/provider access; pass only the public decision outside audit and project the internal cause only for authorization denies.

## Phase 4: REFACTOR — Verification and Boundaries

- [ ] 4.1 Remove obsolete decision imports/composition, preserve routing-after-allow and one append/commit semantics, and run `uv run pytest` plus `docker compose --profile checks run --rm harness npm --prefix schemas/tooling run validate:release -- --release 1.3.0`.
