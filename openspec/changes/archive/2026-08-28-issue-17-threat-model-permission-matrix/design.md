# Design: MVP Threat Model and Security Evaluation Catalog

## Technical Approach

Publish one reviewer-oriented threat model and two YAML 1.2 catalogs, then enforce their structure and current-runtime claims with database-independent pytest tests. The catalogs describe evidence; they do not become authorization inputs or alter `POST /v1/responses`. This implements every `mvp-security-evaluation` requirement while preserving the existing 403 non-enumeration and metadata-only audit boundaries.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
| --- | --- | --- | --- |
| Artifact split | Markdown threat model plus separate versioned grant/scenario YAML | One Markdown file; new contract release | Humans get a clear entry point while tests consume stable data without expanding governance schema ownership. |
| Validation owner | New database-independent `tests/test_security_catalogs.py` using `yaml.safe_load` | Node contract tooling; runtime validator | Pytest already owns repository behavior and runs automatically in the Python CI job. Add `pyyaml==6.0.3` as an explicit dev dependency rather than relying on its transitive installation. |
| Evidence locator | Pytest node ID: `tests/<file>.py::test_<name>` | Line numbers; prose references | Node IDs survive line movement, are resolvable by AST/file checks, and can be run directly. A function-level locator may cover all parameterized cases. |
| Maturity model | `current`, `contracted_future`, `future`; automation `executable` or `non_executable` | Boolean `implemented` | Separate vocabularies prevent ADR-backed future redaction from being confused with executable MCP/admin behavior. |
| Drift boundary | Import `PRINCIPALS` for seed identity parity; validate exact matrix graph and scenario semantics | Parse Python source; duplicate unchecked lists | Importing the public seed tuple avoids brittle source parsing. Existing seed/runtime tests remain the behavioral evidence for the single grant. |

## Data Flow

```text
seeds.py ───────┐
existing tests ─┼─→ test_security_catalogs.py ─→ parsed matrix/scenarios ─→ PASS/FAIL
main specs/ADRs ┘                  ↑
                         threat-model.md links
```

Catalogs are read-only release evidence. Runtime authorization continues to read PostgreSQL grants, never these files.

## File Changes

| File | Action | Description |
| --- | --- | --- |
| `docs/security/threat-model.md` | Create | Assets, trust boundaries, maturity-tagged threats, mitigations, residual risk, exclusions, and ADR/evidence links. |
| `docs/security/demo-grants.v1.yaml` | Create | Four principals, one resource, exact active grant, default deny, and `names_confer_roles: false`. |
| `docs/security/scenarios.v1.yaml` | Create | Stable scenario records for current allow/deny/auth/resource hiding and non-executable redaction/MCP/admin cases. |
| `tests/test_security_catalogs.py` | Create | Structural, seed-parity, semantic, locator, and cross-document checks. |
| `pyproject.toml` | Modify | Pin PyYAML in the dev extra. |
| `uv.lock` | Modify | Record the direct dev dependency without changing runtime behavior. |

## Interfaces / Contracts

`demo-grants.v1.yaml` has `schema_version`, `default_decision`, `names_confer_roles`, `principals[]`, `resources[]`, and `grants[]`. Grant identity is `(principal_id, action, resource_type, resource_id)`; exactly one active `allow` is permitted.

`scenarios.v1.yaml` has `catalog_version` and `scenarios[]`. Every scenario requires `id`, `maturity`, `threat`, `preconditions`, `credential_state`, `principal`, `action`, `resource`, `request`, `expected`, and `automation`. `expected` contains HTTP status/code, policy decision or `not_evaluated`, upstream/tool call counts, and audit behavior. Executable entries require a resolvable `test_locator`; non-executable entries require `evidence_required` and forbid a passing claim.

## Testing Strategy

| Layer | What to test | Approach |
| --- | --- | --- |
| Structural | YAML shape, required fields, versions, unique `SEC-*` IDs | `yaml.safe_load` plus explicit assertions and actionable failure messages. |
| Semantic | Four seed principals, one resource/grant, default deny, 403 equivalence, zero-call denies, maturity/automation consistency | Compare with `PRINCIPALS` and fixed accepted contract values. |
| Traceability | Evidence files/functions exist; threat model links ADR-004/005/006 and both catalogs | Resolve node IDs through `Path` and Python AST; read Markdown links. |
| Existing runtime | Allow, deny, authentication, audit gate | Reuse the cataloged pytest node IDs; no new runtime behavior. |

## Threat Matrix

N/A — this change does not alter routing, shell commands, subprocesses, VCS/PR automation, executable-file classification, or process integration. Catalog assertions describe existing/future boundaries but execute none of them.

## Migration / Rollout

No data migration or feature flag is required. Revert documents, catalogs, tests, and the direct dev dependency together. If tasks forecast over 400 authored lines, use the confirmed stacked-to-main auto-chain: first deliver matrix/catalog interfaces with structural validation, then threat-model and semantic/traceability completion. Each slice must pass its scoped pytest and Ruff checks.

## Open Questions

None. Runtime redaction, MCP/tool execution, and administrative endpoints remain explicitly outside this design.
