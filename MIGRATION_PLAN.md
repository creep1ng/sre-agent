# Rust Gateway/Core Migration Plan

**Destination:** Rust owns gateway and core behavior without changing the public Python/API contract until an explicitly approved cutover. Migrate one cohesive behavior at a time; do not treat the existing Rust policy slices as a complete gateway replacement. The detailed checklist and test history are in [the ODD task](odd/tasks/rust-gateway-core.md). For the current worktree snapshot, read [MIGRATION_STATUS.md](MIGRATION_STATUS.md).

## Boundary and sequence

1. **Keep one authority per policy.** Put deterministic decisions in dependency-free `rust/core`; expose them through `rust/python` as the versioned `sre_agent._core` PyO3 module. Python fact readers and effectful adapters call Rust rather than reimplement its decision.
2. **Finish core policy inventory.** Characterize request normalization (RGC-03b2), remaining success-response normalization (RGC-03b3), administrative decisions beyond terminal audit (RGC-03c), and incident decisions beyond generic admission (RGC-03d). Add a focused failing regression before each behavior change, preserve the current public contract, then prove the Rust path and record rollback.
3. **Move infrastructure and gateway edges (RGC-04).** Port persistence, provider integration, and HTTP/composition in bounded vertical slices. Preserve authorization order, provider-evidence ordering, DTO validation, audit/release behavior, database transaction semantics, and OpenAPI-visible responses. Choose Rust transport/database dependencies only for a concrete slice, not in advance.
4. **Package and cut over (RGC-05).** Prove reproducible native builds, installed-wheel import, container startup, existing Python/Rust regressions, integration behavior, static checks, and operational rollback. Retire a Python implementation only after the same production entry point exercises its Rust replacement. Do not declare Rust the gateway owner while `create_application` still composes Python HTTP/DB/provider services.

## Ownership today

| Rust-owned through the Python adapter | Still Python-owned |
| --- | --- |
| Authorization decision; responses-audit projection; provider-failure taxonomy; OpenRouter routing evidence, consumption projection, and completed assistant text selection; terminal control-audit policy; generic incident transition admission | FastAPI routes/composition and request DTO validation; authorization fact lookup; database repositories, transactions, audit append, and release gating; provider HTTP, credentials, JSON/Decimal parsing, and DTO construction; incident workflow lookup, reducer, and persistence |
| ADR-005 audit-reference HMAC computation in the PyO3 adapter (`rust/python`) | HMAC key custody, audit-reference validation, and Python public/error boundary |

`rust/core` must remain independent of Python, HTTP, database, and provider SDKs. The HMAC implementation is intentionally in the PyO3 adapter, not the dependency-free core. Preserve `sre_agent._core` importability throughout the transition; no silent Python policy fallback.

## Proof and rollback per slice

- Use the configured strict-TDD sequence: observed focused RED, GREEN, then refactor and rerun checks. Record chronology honestly if an environment delays RED observation.
- Run relevant Rust tests and current Python regressions, Rustfmt/Clippy, configured Ruff/mypy/Import Linter/uv lock checks, installed-wheel import, and runtime smoke when the slice touches packaging or the production boundary. Distinguish local checks from hosted CI and skipped live-provider tests.
- Name the smallest rollback unit: the Rust policy module/export, PyO3 binding and stub, Python adapter call, and its focused tests. Rolling back one policy slice must not revert earlier independent slices. At final gateway cutover, rollback means restoring the prior Python composition/deployment while preserving compatible schemas and public contracts; document deployment-specific mechanics before release.
- Do not silently resolve the OpenRouter fixture-versus-versioned-contract divergence tracked by [issue #345](https://github.com/creep1ng/sre-agent/issues/345) during this migration. Use the current Python runtime/tests as the parity oracle until that contract is separately decided.

## Resume

Read [MIGRATION_STATUS.md](MIGRATION_STATUS.md) and the full [ODD task](odd/tasks/rust-gateway-core.md); compare their evidence to the actual worktree before changing code. The next implementation action is a read-only inventory of RGC-03b2 and the remaining RGC-03b3 boundary, followed by one narrow, test-first slice. Branch publication and any PR are separate authorized delivery steps, not proof of migration completion.
