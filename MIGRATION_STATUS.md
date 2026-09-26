# Rust Gateway/Core Migration Status

**Snapshot: 2026-09-26.** This migration candidate belongs to `worktree/rapid-meadow-d2ee`. Its verified pre-migration base and merge-base with local `main` is `137b101b6d1f294e7fcb302d4fd4bfeb7d760fa8`; that SHA is **not** the migrated candidate. Use `git rev-parse HEAD` after checkout to identify the commit containing this snapshot, and verify remote publication separately. No PR, hosted CI, live provider call, or full Rust gateway cutover is claimed. For the stable target and sequencing, see [MIGRATION_PLAN.md](MIGRATION_PLAN.md); for granular tasks, see [the ODD task](odd/tasks/rust-gateway-core.md).

## Completed local slices

- **RGC-01/02:** Rust workspace, maturin/PyO3 `sre_agent._core`, and Rust-owned authorization decision behind Python fact readers.
- **RGC-03a, 03b1, 03b3a/b:** Rust-owned responses-audit projection, provider-failure mapping, OpenRouter consumption projection, and completed assistant text selection. Python still owns request/DTO validation and provider effects.
- **RGC-03c1, 03d1, 03e1–e3:** Rust-owned terminal control-audit policy, generic incident transition admission, and OpenRouter response/inline/catalog routing-evidence decisions. Broader control and incident workflows remain Python-owned.
- **RGC-04a/a1:** ADR-005 HMAC computation in the Rust PyO3 adapter, with Python-compatible formatting and whole-string `UnicodeEncodeError` diagnostics. Python retains key custody and audit release.

The current FastAPI composition root is `src/sre_agent/application.py`; provider HTTP is in `src/sre_agent/gateway/openrouter.py`, DB adapters in `src/sre_agent/persistence/`, and the mixed Python/native package is configured in `pyproject.toml`, `rust/`, and `docker/api.Dockerfile`. These are live Python boundaries, not completed Rust ports.

## Observed verification (before this documentation handoff)

| Check on the post-Rustfmt local candidate | Observed result |
| --- | --- |
| Rebuilt full Python `pytest -q -rs tests` | 1084 passed; 1 credentialed live OpenRouter smoke skipped |
| Full Cargo workspace `cargo test --locked --manifest-path rust/Cargo.toml` | 29 passed |
| `cargo fmt --check` and `cargo clippy --locked --all-targets -- -D warnings` | Passed in a Python-capable checks image |
| Configured Ruff lint/format, mypy, Import Linter, and `uv lock --check` | Passed in rebuilt checks image |
| Isolated maturin wheel build/install/import and rebuilt runtime API native/adapter smoke | Passed with synthetic inputs |
| `git diff --check` | Passed on the post-format source candidate; rerun after this handoff edit |

The first runtime smoke input lacked required message `status: completed`; its failure was corrected in the synthetic fixture before the passing smoke. The first Clippy image lacked Python; Clippy passed in the Python-capable image. For RGC-03b3b, characterization tests were written first, but the missing-symbol old-image RED was observed **after** source implementation because local Docker access stalled. Do not claim RED-before-implementation for that slice. The later GREEN and post-format checks above are observed, not hosted CI evidence.

## Pending and next action

1. **Next:** Reconcile this worktree with [the ODD task](odd/tasks/rust-gateway-core.md) and inventory RGC-03b2 request normalization plus remaining RGC-03b3 success normalization. Pick one narrow Rust policy boundary; write and observe its focused RED before implementation, then GREEN/refactor/check it. Do not change provider evidence while doing this.
2. Continue RGC-03c and RGC-03d beyond their completed sub-slices, then RGC-04 infrastructure/HTTP/database/provider adapters and RGC-05 packaging, production cutover, and rollback proof.
3. Treat [issue #345](https://github.com/creep1ng/sre-agent/issues/345) as a separate OpenRouter fixture-versus-versioned `X-Generation-Id` contract decision; do not rewrite current behavior to fit the fixture during migration.
4. Before a PR or release, confirm the published candidate SHA, rerun applicable checks when source bytes change, and satisfy the repository's [team workflow](docs/team-workflow.md) and [PR evidence policy](docs/pr-evidence.md). The pre-migration base SHA cannot anchor the local migration test results.

**Rollback boundary:** revert only a newly added policy slice and its PyO3/Python bridge/tests without discarding earlier proven slices. A future full gateway cutover needs a separate deployment rollback procedure; it does not yet exist. The credentialed live provider check remains unverified.
