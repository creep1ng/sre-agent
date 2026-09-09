# Apply Progress: Uniform Governed Authorization

## Completed Tasks

- [x] 1.1 RED: Added governed-access and Responses OpenAPI contract tests.
- [x] 1.2 GREEN: Added the shared governed authorization boundary and routed Responses through it.
- [x] 1.3 REFACTOR: Consolidated credential parsing/context resolution and completed focused, harness, and full checks.

Previous apply progress: none.

## TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/test_authentication.py`, `tests/test_responses_openapi.py` | Unit | 29 passed | `authorize_governed_access` import failed | 2 passed | Valid scope and malformed Bearer cases: 3 passed | N/A |
| 1.2 | Same | Unit/integration | 29 passed | Same shared-boundary import failure | Shared boundary and route metadata: 2 passed | 3 passed | Import and dependency cleanup retained behavior |
| 1.3 | Same | Unit/integration | 29 passed | N/A — refactor task | 46 focused tests passed | Full suite covers Responses behavior | 679 passed, 1 skipped; Ruff/format/lock/Alembic checks passed |

## Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command | `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_authentication.py tests/test_responses.py tests/test_responses_openapi.py` — 46 passed, 1 warning |
| Runtime harness | `scripts/worktree-compose --profile issue-14 run --build --rm issue-14-harness` — 26 passed, 1 warning |
| Full test command | `scripts/worktree-compose --profile checks run --build --rm python-checks` — 679 passed, 1 skipped, 1 warning; lint, format, lock, and Alembic checks passed |
| Rollback boundary | Revert `src/sre_agent/gateway/authentication.py`, `src/sre_agent/gateway/responses.py`, `tests/test_authentication.py`, and `tests/test_responses_openapi.py`. |

## Rebased PR Proof

- Base: `origin/main` at `f65781b7ec630bf05b40223d70104db7ccf0ec09`.
- Full configured checks: 766 passed, 1 skipped; lint, format, import contracts, type checks, lock, and Alembic checks passed.
- The base's existing FastAPI Bearer dependency was retained while adding governed-scope metadata and shared authorization.

## Evidence Logs

- `/tmp/issue202-unit1-baseline.log` — baseline 29 passed.
- `/tmp/issue202-unit1-red.log` — expected missing `authorize_governed_access` import failure.
- `/tmp/issue202-unit1-green.log` — 2 passed.
- `/tmp/issue202-unit1-triangulate.log` — 3 passed.
- `/tmp/issue202-unit1-focused.log` — 46 passed.
- `/tmp/issue202-unit1-harness.log` — 26 passed.
- `/tmp/issue202-unit1-full-final.log` — full configured checks passed.
- `/tmp/issue202-unit1-rebased-proof-final.log` — full configured checks passed on current `origin/main`.

## Completed Tasks — Unit 2

- [x] 2.1 RED: Added executable spies covering invalid credentials, denied create/list/get before repository effects, authorized missing target, and matched-grant audit evidence.
- [x] 2.2 GREEN: Routed the three principal operations through `authorize_governed_access`; denied list/get now return 403 before business access, while an authorized missing target remains 404.
- [x] 2.3 REFACTOR: Declared exact governed metadata for the three operations and updated existing control authorization/acceptance evidence to the uniform 403 contract.

## TDD Cycle Evidence — Unit 2

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|---|---|---|
| 2.1 | `tests/test_control_plane.py` | Unit | 13 passed | shared authorization attribute missing during test collection | 14 passed | invalid 401, three denied 403/no effects, and authorized-missing 404/grant evidence | N/A |
| 2.2 | `tests/test_control_plane.py`, `tests/test_control_authorization_order.py`, `tests/test_control_acceptance.py` | Unit/integration | 13 passed | Unit 2 shared-boundary test failed before the import existed | 28 passed | existing eight-operation ordering and acceptance paths confirm the three migrated operations use the shared boundary | No further extraction needed |
| 2.3 | `tests/test_control_plane.py` | Unit | 13 passed | `x-governed-scope` KeyError | 14 passed | create/write and list/get/read metadata cases | Kept existing `CONTROL_SCOPES`; no provisioning or lifecycle changes |

## Work Unit Evidence — Unit 2

| Evidence | Result |
|---|---|
| Focused test command | `scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_control_plane.py tests/test_control_authorization_order.py tests/test_control_acceptance.py` — 28 passed |
| Runtime harness | N/A — composed FastAPI/TestClient acceptance coverage is the applicable runtime boundary. |
| Full test command | `scripts/worktree-compose --profile checks run --build --rm python-checks` — 767 passed, 1 skipped; lint, format, import contracts, lock, Alembic, and upgrade checks passed. |
| Rollback boundary | Revert the Unit 2 changes in `src/sre_agent/control/service.py`, `tests/test_control_plane.py`, `tests/test_control_authorization_order.py`, and `tests/test_control_acceptance.py`; no grants, seeds, migrations, schemas, or lifecycle files changed. |

## Evidence Logs — Unit 2

- `/tmp/issue202-unit2-baseline-retry.log` — 13 passed.
- `/tmp/issue202-unit2-red.log` — expected missing shared authorization import failure.
- `/tmp/issue202-unit2-green.log` — 14 passed.
- `/tmp/issue202-unit2-metadata-red.log` — expected missing `x-governed-scope` failure.
- `/tmp/issue202-unit2-focused-final.log` — 28 passed.
- `/tmp/issue202-unit2-full-final.log` — final full configured checks passed.
