# Issue #331 — local repair evidence bundle

Issue: [#331](https://github.com/creep1ng/sre-agent/issues/331). Scope: repair and evidence for the existing stacked PRs; no merge or issue closure.

This bundle contains sanitized evidence for a locally repaired stack. It does not claim hosted CI, human approval, merge, or issue closure. Candidates and evidence are frozen to exact source heads in [`source-map.json`](source-map.json); stack order is #387 → #388 → #397 → #403 → #402 → #404 → #405 → #433 validation child → #406 → #407 → #409. PR #433 is the 87-line validation child for malformed-path auditing. It addresses that item separately; do not claim it is fixed in #405 core.

## Reproduction

From an exact candidate checkout whose HEAD equals the SHA in the result record, export `SOURCE_CHECKOUT` to its path on the host. Create ignored clone-local `.env` and `.env.worktree` safe disposable configuration (mode 0600); never commit or upload these. A host-specific ignored Compose network override may be needed when local Docker IPAM defaults overlap; use only an isolated non-overlapping local subnet, never alter global Docker state or prune other projects. Host supplies only Git, Docker, and safe local configuration. Commands below run tests in Docker; no host package managers are used.

Focused PR #409 example (the per-PR report has the exact path list):

```sh
docker compose --project-directory "$SOURCE_CHECKOUT" --env-file "$SOURCE_CHECKOUT/.env" --env-file "$SOURCE_CHECKOUT/.env.worktree" --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_skill_demo.py tests/test_skill_resolution.py'
```

Full default suite:

```sh
docker compose --project-directory "$SOURCE_CHECKOUT" --env-file "$SOURCE_CHECKOUT/.env" --env-file "$SOURCE_CHECKOUT/.env.worktree" --profile checks run --build --rm python-checks
```

A guarded helper is available at [`scripts/reproduce-slice.sh`](scripts/reproduce-slice.sh); it checks the exact HEAD and safe local env-file modes before invoking Docker Compose. The capture helper is for maintainers reproducing the evidence: set `SOURCE_CHECKOUT`, `OUTPUT_DIR`, and a disposable `CAPTURE_PROJECT` with a locally configured non-overlapping network; it mounts the co-located probe read-only and writes only allowlisted JSON. An initial fresh-project invocation was blocked before tests by local Docker IPAM overlap. After inspecting and removing only the completed prior owned DB/network (no volumes), the helper passed against exact #409 (1 passed in 3.34s) in its unique project; that DB/network was then removed by scoped Compose down. The 11 actual captures were executed with the preconfigured isolated project. The helper makes no provider calls. The included capture-test fixture replaces its original private synthetic payload string with `SYNTHETIC_SENTINEL`; this does not affect measured response fields or SQL counts.

## Evidence limits and review

Each PNG is an actual headless-browser render of an executed local FastAPI/PostgreSQL probe at the named source HEAD. The JSON records allowlisted response metadata and measured SQL counts. Screenshots do not replace tests: in particular, #387/#403 snapshots show zero rows and are readiness/schema evidence only; #404’s screenshot does not prove DTO rejection. See focused tests above and per-slice reports.

At the last parent-refreshed status snapshot, some hosted checks were terminal green but six contract checks remained active; the complete hosted outcome is pending. Review snapshot: 16 COMMENTED reviews, 9 unresolved inline threads, zero replies, zero approvals. Human review remains pending; refresh before final delivery.

Video: Deferred: media storage unavailable; screenshot evidence is mandatory.
