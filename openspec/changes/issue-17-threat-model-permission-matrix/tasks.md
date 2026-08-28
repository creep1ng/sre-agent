# Tasks: MVP Threat Model and Security Evaluation Catalog

## Review Workload Forecast

Planning artifacts already authored total **362 lines**. Estimated implementation adds **500–620 lines**, for a total delivery forecast of **862–982 authored lines**.

| Field | Value |
|-------|-------|
| Estimated changed lines | 862–982 total (362 planning + 500–620 implementation) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes — three reviewable slices |
| Suggested split | PR 1 planning artifacts → PR 2 catalogs/dependency/structural validation → PR 3 threat model/semantic traceability |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Start → finished boundary | Likely PR | Per-PR estimate | Focused check | Runtime harness | Rollback boundary |
|------|---------------------------|-----------|-----------------|---------------|-----------------|-------------------|
| 1 | Existing proposal/exploration/spec/design → all OpenSpec planning artifacts readable and internally consistent; no implementation | PR 1 | 362 lines (≤400) | `git diff --check` and `test -s` on each change artifact | N/A — planning-only | Revert the entire change directory |
| 2 | PR 1 merged to main → both catalogs, PyYAML dev dependency/lockfile, and structural/seed tests pass | PR 2 | 290–360 lines (≤400) | `uv run pytest tests/test_security_catalogs.py -k 'structure or seed or grant' && uv run ruff check tests/test_security_catalogs.py` | N/A — catalogs are read-only evidence | Revert both YAML files, `tests/test_security_catalogs.py`, `pyproject.toml`, and `uv.lock` |
| 3 | PR 2 merged to main → threat model and semantic/locator/traceability checks pass | PR 3 | 200–260 lines (≤400) | `uv run pytest tests/test_security_catalogs.py && uv run ruff check tests/test_security_catalogs.py` | N/A — runtime behavior is unchanged; existing tests remain evidence | Revert `docs/security/threat-model.md` and PR 3 test additions |

## Phase 1: Planning verification (PR 1)

- [x] 1.1 Preserve proposal, exploration, capability spec, and design; update only this tasks file with dependency-ordered slices and exact forecast lines.
- [x] 1.2 Structurally read all five change artifacts; confirm no files under issue #127 are modified.

## Phase 2: Catalog foundation (PR 2)

- [ ] 2.1 Add `pyyaml==6.0.3` to dev dependencies and update `uv.lock`.
- [ ] 2.2 Write RED structural tests, then create both v1 YAML catalogs with all required fields, four seeded principals, one resource, and exactly one active incident-harness grant.
- [ ] 2.3 Quote YAML 1.1-sensitive scalars (`on`/`off`/`true`/`false`) and assert strict Python scalar types after `safe_load`; enforce seed parity, unique IDs, and actionable drift failures.

## Phase 3: Security evidence completion (PR 3)

- [ ] 3.1 Create `docs/security/threat-model.md` with assets, boundaries, maturity, mitigations, residual risks, exclusions, ADR links, metadata-only audit, and unimplemented redactor.
- [ ] 3.2 Add semantic checks for 403 `resource_unavailable` equivalence, zero upstream calls, current locator resolution, and future-only MCP/admin expectations; run existing runtime evidence tests.
- [ ] 3.3 Verify catalog/Markdown links and locators resolve; do not implement redactor, MCP, or admin runtime.
