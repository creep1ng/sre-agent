# Apply Progress: Catalog Foundation (PR 2)

## Cumulative completed tasks

- [x] 1.1 Planning artifacts preserved and workload slices recorded.
- [x] 1.2 Planning artifacts structurally read; issue #127 remains untouched.
- [x] 2.1 PyYAML is pinned as a direct dev dependency and locked.
- [x] 2.2 Versioned grants/scenario catalog foundations and seed-matrix tests are present.
- [x] 2.3 Nested schema, strict scalar types, stable IDs, and maturity/automation rules are validated.

## TDD Cycle Evidence

| Task | Safety net | RED | GREEN | Triangulation | REFACTOR |
|---|---|---|---|---|---|
| 2.1 | `uv lock --check` → resolved 37 packages | `uv run pytest tests/test_security_catalogs.py -k dependency` → 1 failed: direct PyYAML absent | `uv run pytest tests/test_security_catalogs.py -k dependency` → 1 passed after manifest/lock update | N/A — one pinned structural declaration | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py -k dependency` → passed; imports/message formatted |
| 2.2 | `uv run pytest tests/test_security_catalogs.py -k dependency` → 1 passed | `uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 2 failed: catalog files absent | `uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 2 passed, 1 deselected | `uv run pytest tests/test_security_catalogs.py` → 3 passed | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → passed; assertion wrapped |
| 2.3 | `uv run pytest tests/test_security_catalogs.py` → 3 passed | `uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 1 failed: scenarios empty | `uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 3 passed, 1 deselected | `uv run pytest tests/test_security_catalogs.py` → 4 passed | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py` → passed; import/constants formatted |

## Test Summary

- Total tests written: 4 unit tests.
- Final result: 4 passed; focused result: 3 passed, 1 deselected.
- Approval tests: none; pure functions: none — catalogs are read-only evidence.

## Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused test | `uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 3 passed, 1 deselected |
| Full structural test | `uv run pytest tests/test_security_catalogs.py` → 4 passed |
| Ruff | `uv run ruff check tests/test_security_catalogs.py` → all checks passed |
| Runtime harness | N/A — the catalogs are read-only release evidence; no runtime boundary changes |
| Rollback | Revert both catalog files, test file, `pyproject.toml`, and `uv.lock` together |

Stacked PR 2 boundary: catalog dependency, immutable catalogs, and structural/seed validation only. Threat model, locator resolution, and runtime semantic proof remain PR 3.

## PR 3 completed tasks

- [x] 3.1 Threat model documents assets, boundaries, maturity, mitigations, residual risks, exclusions, ADR links, metadata-only audit, and absent runtime redaction.
- [x] 3.2 Semantic checks validate both `SEC-002` and `SEC-003` as `403 resource_unavailable` with zero upstream calls, resolve current locators, and reject executable future entries.
- [x] 3.3 Markdown catalog/ADR links and locator readability are checked without adding runtime behavior.

## PR 3 TDD Cycle Evidence

| Task | Safety net | RED | GREEN | Triangulation | REFACTOR |
|---|---|---|---|---|---|
| 3.1 | `uv run pytest tests/test_security_catalogs.py` → 4 passed | `uv run pytest tests/test_security_catalogs.py` → 1 failed, 4 passed: `threat-model.md` absent | `uv run pytest tests/test_security_catalogs.py` → 5 passed | One test asserts independent ADR evidence and current/future boundary sets | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py` → Ruff passed; 5 passed |
| 3.2 | `uv run pytest tests/test_security_catalogs.py` → 5 passed | `uv run pytest tests/test_security_catalogs.py` → 1 failed, 5 passed: runtime-evidence locator section absent | `uv run pytest tests/test_security_catalogs.py` → 6 passed | Current allow/deny/missing locators plus three future scenarios exercise distinct branches | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py` → Ruff passed; 6 passed |
| 3.3 | `uv run pytest tests/test_security_catalogs.py` → 6 passed | `uv run pytest tests/test_security_catalogs.py` → 1 failed, 6 passed: catalog links absent | `uv run pytest tests/test_security_catalogs.py` → 7 passed | Five Markdown targets resolve: two catalogs and ADR-004/005/006 | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py` → Ruff passed; 7 passed |

## Strict Test Summary

- Total tests: 7 unit tests; final catalog result: 7 passed.
- New PR 3 tests: 3; test layer: unit/document-structure validation.
- Approval tests: none. Pure functions: none; the artifacts remain read-only evidence.

## PR 3 Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused catalog proof | `uv run pytest tests/test_security_catalogs.py` → 7 passed |
| Lint | `uv run ruff check tests/test_security_catalogs.py` → all checks passed |
| Runtime evidence | `docker compose --profile issue-14 run --build --rm issue-14-harness` → 11 passed; ran with a disposable out-of-repository Compose environment using repository-standard synthetic local-only values, removed afterward |
| Rollback boundary | Revert `docs/security/threat-model.md` and PR 3 additions in `tests/test_security_catalogs.py`; runtime gateway behavior remains unchanged |

Stacked PR 3 boundary: traceability documentation and read-only verification only. No redactor, MCP/tool, or administrative runtime was implemented.

## Verification remediation evidence

This bounded correction addresses the failed verification revision `sha256:207d87096b05869ea7e0e17caf306dffe5423511b5051a2b76ef793517fa62c7` without changing any runtime behavior.

| Work unit | Safety net | RED | GREEN | Triangulation | REFACTOR |
|---|---|---|---|---|---|
| Future denial and drift validation | `uv run pytest tests/test_security_catalogs.py` → 7 passed | `uv run pytest tests/test_security_catalogs.py` → 1 failed, 7 passed: future scenarios used `not_evaluated` outside contracted future | `uv run pytest tests/test_security_catalogs.py` → 8 passed after future MCP/admin entries declared deny, 403, zero upstream calls, and safe audit evidence | Validates allow, current deny, future deny, contracted future, and non-empty deferred/future sets | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py` → Ruff passed; 8 passed |

## Remediation Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused and full catalog proof | `uv run pytest tests/test_security_catalogs.py` → 8 passed |
| Lint | `uv run ruff check tests/test_security_catalogs.py` → all checks passed |
| OpenSpec | `openspec validate issue-17-threat-model-permission-matrix --strict` → change is valid |
| Runtime harness | N/A — this correction changes read-only future catalog expectations and structural validation only; no runtime boundary changed |
| Rollback boundary | Revert `docs/security/scenarios.v1.yaml`, remediation additions in `tests/test_security_catalogs.py`, and this remediation evidence together |

Cleanup/process evidence: no temporary files, containers, branches, or external artifacts were created by this correction.

## Contradictory not-evaluated remediation evidence

This bounded correction addresses failed verification revision `sha256:30ba588299e4c18ac6e1fa5bb5d27e1be71107c70271c4e304d7cef60c29566e` without changing valid catalog data or any runtime boundary.

| Work unit | Safety net | RED | GREEN | Triangulation | REFACTOR |
|---|---|---|---|---|---|
| Not-evaluated outcome mutation | `uv run pytest tests/test_security_catalogs.py` → 8 passed | `uv run pytest tests/test_security_catalogs.py` → 1 failed, 8 passed: contradictory 403/resource-unavailable mutation did not raise | `uv run pytest tests/test_security_catalogs.py` → 9 passed after general validator required the contracted-future not-evaluated HTTP/code/audit tuple | Valid catalog scenario and contradictory in-memory mutation exercise distinct paths | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py` → Ruff passed; 9 passed |

## Second Remediation Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused and full catalog proof | `uv run pytest tests/test_security_catalogs.py` → 9 passed |
| Lint | `uv run ruff check tests/test_security_catalogs.py` → all checks passed |
| OpenSpec | `openspec validate issue-17-threat-model-permission-matrix --strict` → change is valid |
| Runtime harness | N/A — this correction changes only in-memory structural validation; no runtime boundary changed |
| Rollback boundary | Revert this mutation test and validator tightening together with this evidence section |

Cleanup/process evidence: no temporary files, containers, branches, external artifacts, or catalog-data changes were created by this correction.
