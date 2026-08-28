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
| 2.1 | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv lock --check` → resolved 37 packages | `uv run pytest tests/test_security_catalogs.py -k dependency` → 1 failed: direct PyYAML absent | same command → 1 passed after manifest/lock update | N/A — one pinned structural declaration | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py -k dependency` → passed; imports/message formatted |
| 2.2 | `uv run pytest tests/test_security_catalogs.py -k dependency` → 1 passed | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 2 failed: catalog files absent | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 2 passed, 1 deselected | `uv run pytest tests/test_security_catalogs.py` → 3 passed | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run ruff check tests/test_security_catalogs.py && UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → passed; assertion wrapped |
| 2.3 | `uv run pytest tests/test_security_catalogs.py` → 3 passed | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 1 failed: scenarios empty | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 3 passed, 1 deselected | `uv run pytest tests/test_security_catalogs.py` → 4 passed | `uv run ruff check tests/test_security_catalogs.py && uv run pytest tests/test_security_catalogs.py` → passed; import/constants formatted |

## Test Summary

- Total tests written: 4 unit tests.
- Final result: 4 passed; focused result: 3 passed, 1 deselected.
- Approval tests: none; pure functions: none — catalogs are read-only evidence.

## Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Focused test | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant'` → 3 passed, 1 deselected |
| Full structural test | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run pytest tests/test_security_catalogs.py` → 4 passed |
| Ruff | `UV_CACHE_DIR=/tmp/sre-agent-uv-cache uv run ruff check tests/test_security_catalogs.py` → all checks passed |
| Runtime harness | N/A — the catalogs are read-only release evidence; no runtime boundary changes |
| Rollback | Revert both catalog files, test file, `pyproject.toml`, and `uv.lock` together |

Stacked PR 2 boundary: catalog dependency, immutable catalogs, and structural/seed validation only. Threat model, locator resolution, and runtime semantic proof remain PR 3.
