# PR #433 — 331-validation-child evidence

- **Source:** `94d14d9e37c5b456b441201b4d98a13bacc056d1`; tested base `3b525e0a305e8b44bdcd54495284950393a7b415`.
- **Changed-line count:** from immediate tested base, as recorded in `source-map.json`; all candidates are below the repository’s 400-line PR gate.
- **CA coverage:** CA6 malformed exact-resolution path/audit (the finding is fixed in child #433, not #405 core).
- **Checks image:** per-candidate manifest-list SHA-256 `59349e0aa3213586f0a92cb72d9c55e412ea359d6c5294a177b42da3ca250635` (Dockerfile base and PostgreSQL digests are recorded in the result JSON).
- **Evidence kind/freshness:** controlled synthetic-data FastAPI/PostgreSQL integration observed `2026-09-30T07:36:44+00:00` at this exact local source head. This is not hosted CI or human approval.
- **Correction/root cause:** Malformed exact-resolution paths could reach authorization/content handling without a bounded correlated terminal audit.
- **Fix/outcome:** Child #433 validates a syntactically valid 33-character version before auth/content and emits 422 with one correlated terminal audit row.
- **Expected vs observed:** 422 observed as `422`; SQL counters/metadata recorded from queries in [`../results/331-validation-child.json`](../results/331-validation-child.json). See the capture caveat below for the scope of what a screenshot alone proves.

## Reproduce the focused behavior tests

Use an exact checkout at the source SHA above and safe ignored local `.env`/`.env.worktree` files in mode 0600. Host supplies Git, Docker and safe local config only.

```sh
docker compose --project-directory "$SOURCE_CHECKOUT" --env-file "$SOURCE_CHECKOUT/.env" --env-file "$SOURCE_CHECKOUT/.env.worktree" --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_skill_resolution.py'
```

The focused command invokes the DB-isolation guard before pytest inside the checks container. **Current local full default suite:** 1,261 passed; 1 opt-in live-provider skip (85.98s). The sole skip is opt-in live-provider smoke, not run/authorized. Static, type/import, lock and Alembic checks were green for the recorded candidate run. Raw logs remain private; the summaries and exact rerun command are provided here.

- **Screenshot:** [`../screenshots/331-validation-child.png`](../screenshots/331-validation-child.png); SHA-256 in `SHA256SUMS`; actual browser render of allowlisted probe JSON.
- **Rollback boundary:** reverting the small behavior slice restores the exact previously delivered immediate-parent candidate; migration history is append-only and no historical migration is edited/deleted/stamped. For status/audit changes the transaction rollback test leaves persisted status/timestamp and audit rows unchanged on injected failure.


## Deep behavior/persistence proof

Deep selectors: `tests/test_skill_resolution.py::test_malformed_paths_return_correlated_terminal_validation_audit` and `tests/test_skill_resolution.py::test_resolution_openapi_keeps_bounded_path_patterns`; valid-semver 33-character case returns 422 with one persisted correlated audit, before protected-content read.
