# Apply Progress: Reusable Authorization Decision Engine

## Completed
- [x] 1.1 Authorization engine RED tests
- [x] 2.1 Engine, facts, and deterministic precedence

## Deferred
- [ ] 2.2 is not implemented in PR 2. PR 4 will add persistence fact ports and remove/narrow `GrantRepository.decide()` after `ResponsesService` migrates.

## TDD Cycle Evidence
| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 1.1/2.1 | `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev pytest tests/test_authorization.py -q`: collection failed (`ModuleNotFoundError`) | Same command: 16 passed | `uv run pytest tests/test_authorization.py -q`: 16 passed; Ruff exit 0 |

## Work Unit Evidence
| Evidence | Result |
|---|---|
| Focused tests | `uv run pytest tests/test_authorization.py -q` exit 0: 16 passed in 0.07s. |
| Ruff | `uv run ruff check src/sre_agent/governance/authorization.py tests/test_authorization.py` exit 0. |
| Runtime harness | N/A: this PR is a pure governance engine with in-memory fact readers; Responses/routing integration is PR 4. |
| Rollback boundary | Revert `governance/authorization.py`, `tests/test_authorization.py`, `tasks.md`, and this `apply-progress.md`. |
