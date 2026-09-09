# Tasks: Uniform Governed Authorization (Issue #202)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 850–950 total, including the existing 416-line untracked planning set |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 planning + Responses; PR 2 design/specs + administration; PR 3 bypass gate + guidance |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Current tooling: `strict_tdd: true`; test command: `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q` (the old config is stale).
One honest pass keeps each PR below 400 lines including planning overhead (PR 1 ≈390, PR 2 ≈380, PR 3 ≈180); do not compress artifacts.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Shared access boundary and Responses contract | PR 1 | `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_responses.py tests/test_responses_openapi.py` | `scripts/worktree-compose --profile issue-14 run --build --rm issue-14-harness` | Revert `authentication.py`, `responses.py`, and Responses tests |
| 2 | Uniform administration and grant evidence | PR 2 | `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_control_plane.py` | N/A — TestClient is the runtime boundary | Revert `control/service.py` and control tests |
| 3 | Four-route inventory, real bypass probe, guidance | PR 3 | `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_governed_authorization.py` | N/A — composed TestClient probe exercises real routes | Revert `tests/test_governed_authorization.py` and `docs/architecture.md` |

## Unit 1: RED → GREEN → REFACTOR — PR 1 Responses

- [x] 1.1 RED: Add failing tests for server-owned `(action, resource_type, resource_id)`, invalid Bearer zero effects, and Responses OpenAPI Bearer/401/403 plus `x-governed-scope`.
- [x] 1.2 GREEN: Add `authorize_governed_access` in `src/sre_agent/gateway/authentication.py`; wire `src/sre_agent/gateway/responses.py` after validation, preserving routing/provider order and audit gating.
- [x] 1.3 REFACTOR: Reuse one credential path, keep `body.model` as the only client resource input, then run focused tests and issue-14 harness.

## Unit 2: RED → GREEN → REFACTOR — PR 2 Administration

- [x] 2.1 RED: Add `tests/test_control_plane.py` spies: invalid → 401, denied create/list/get → 403 before repository effects, authorized missing target → 404, allowed event has `grant_ref`.
- [x] 2.2 GREEN: Replace duplicated auth in `src/sre_agent/control/service.py` with the shared function; normalize denied get to 403 and retain control evidence at an evidence-bearing terminal stage.
- [x] 2.3 REFACTOR: Add metadata for the three operations; preserve `CONTROL_SCOPES`, provisioning, seeds, migrations, and lifecycle; run focused Docker tests.

## Unit 3: RED → GREEN → REFACTOR — PR 3 Architecture

- [ ] 3.1 RED: Add inventory tests for all four real /v1 operations, Bearer security, exact scopes, and 401/403 declarations; edit only `tests/test_governed_authorization.py`.
- [ ] 3.2 GREEN: Drive composed real routes with recording provider/principal adapters and denied credentials; assert zero business effects. A synthetic direct-adapter case is secondary only.
- [ ] 3.3 REFACTOR: Update `docs/architecture.md` with the governed-entry rule for future LLM/MCP/skill/knowledge consumers; run focused Docker tests.
