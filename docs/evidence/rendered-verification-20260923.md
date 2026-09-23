# Rendered local verification artifacts — 2026-09-23

These images document **observed local checks**, not a live application UI, a terminal photograph, a production provider, or human acceptance. They use synthetic or fixture-backed data and do not replace independent review.

## PR #337 seed authorization

- Tested source: `d8f8dc823aaf47ba058080a6e3cb31ebe5649a5c`.
- Isolated Docker/PostgreSQL checks: `pytest -q tests/test_demo_seeds.py tests/test_mcp_seed.py` → `10 passed in 20.57s`; focused alias-grant test → `1 passed in 8.03s`.
- Read-only SQL returned one active `administrative_control/model_aliases` resource, only active `allow` grants for `admin-human` `admin.read` and `admin.write`, and zero grants to other principals.
- `pr337-seed-grants-rendered-verification.png` is an offline Chromium screenshot of a rendered transcript built from those captured outputs. It is **not** a screenshot of the running admin UI.
- PNG SHA-256: `9a53bf5b0458cd08e16b3687c296ae470bc382372476a17b9e43eb4ce8d48d1e`.

## PR #293, PR #343, and HAR #296–301

- Exact source candidates: PR #293 `154276c1632d9c1ab386054b628e20b1c4d3294e`; PR #343 `77780f36a9acb277654e9aa40ca12968bba99750`; HAR stack tip #301 `5360bb9b6493ea6aa30fe680bd4b95ef16f0b072`.
- Captured local outputs: PR #293 harness `v22.14.0`; PR #343 runtime tests `18 passed in 3.33s`; HAR tests `64 passed in 5.74s` and six fixture/stub scenario results ending `RESULT: all scenarios as expected`.
- `pr293-pr343-har-rendered-verification.png` is a raster rendering of captured local outputs and read-only candidate context. It is **not** a terminal, live application, Windows runner, or provider screenshot.
- PNG SHA-256: `9aaf0e7f7a0513cd43f55e2b7619631d5cf65ee7f514326fa21b190868ddb6a7`.
