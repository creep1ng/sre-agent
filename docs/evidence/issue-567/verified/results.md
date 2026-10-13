# Observed verification — PR candidate

Tested SHA: `8b4316ca77637fcbed3750bfeb2121d294469b7b`.
Main validation base: `763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`.

## Passed

- Actual clean-source Git/Docker wrapper: **exit 0**; independently observed owned
  verification container: **exited 0**.
- **11 external-effect E2E scenarios passed in 151.35s**.
- Independent receiver SQLite/live-runtime PostgreSQL inspection: all 11 agreed.
- **442 scoped incident/investigator/MCP/import/run-contract tests passed in 97.56s**.
- Isolation guard, ShellCheck, Ruff lint/format, locked dependencies, 5 import
  contracts, targeted mypy (11 source files), run API validation (5 paths, 5
  schemas, 6 positive/8 negative examples), Alembic no new upgrade operations.
- Fresh native Chromium SQL screenshot; source/image byte hashes agree; source
  remained clean. Logs and per-scenario reports contain the observed details.

Two known third-party websockets/uvicorn deprecation warnings; no failing test.

## Historical failed/non-credit attempts

Initial Docker address-pool exhaustion and disappearance of the owned checks DB
prevented earlier acceptance runs. Runtime continuation deleted old temporary
artifacts; those results were not substituted for delivered proof. Persistent
reruns resolved the environment issues. No production behavior defect was inferred.

## Not executed / not claimed

Hosted CI acceptance, unrelated complete repository suite, paid/live provider or
billing, product UI E2E, production remediation, reconciliation/cancellation,
general external exactly-once, merge, issue closure and ordinary human acceptance.
The screenshot displays actual SQL export, not a live product UI.

The source stack remains partial per PR. These are tests of the **full-stack
candidate**, not separate executions at the first two branch heads. Human evidence
review remains required, regardless of subsequent CI status.
