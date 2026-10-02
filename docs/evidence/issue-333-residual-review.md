# Issue #333: cross-incident repair and historical retest

U333-6 is locally fixed; U333-9 is retested. This delegated-direct slice does not close #333. Review `usage.py` selection/aggregation, then its PostgreSQL/FastAPI acceptance scenarios. Schema/release changes remain U333-7/U333-8; publication, independent verification, hosted CI and human acceptance remain pending (U333-10).

## Candidate and environment

Base/HEAD during execution: `5b6109bd2c8100455136cf12ce91c52830833c7f` plus the uncommitted usage/test patch; the parent must bind the tested commit before publication. SHA-256: `usage.py` = `1ca40a23cfd5be08bb272b3ce923b6785a3344999dc0a09d1e6418372d1540c5`; test file = `091f98ad8dec4972211122690bfa1a8a9f9e3c9c0bf247bb58a94740ad4f7591`.
Docker 29.8.1; Python 3.12.14; Ruff 0.11.7; PostgreSQL 17.4 (Compose-pinned digest); Chromium 153.0.8010.52. Dependencies use `uv.lock` SHA-256 `783c78b44e4ab07091d0ee1d44a693b77f1ec0fdc94f9aa3c0e212cd34dc878b`; checks image `sha256:ad20e915c1069354238d01fd19da4e92894b38308af46ee2d33db4fa3f1072d6`.
Prepare ignored `.env` from public `.env.example` with local-only values and `.env.worktree` using `scripts/bootstrap-worktree.py`; never copy a private environment. The unique project is `candidate-wt-9bb3531fa9f1`; only its ephemeral `python-checks-db` was used. No demo or foreign database was touched.
Initial RED launch failed before tests: Docker default address pools were exhausted. After read-only route/network overlap checks, only the owned network was created with `docker network create --driver bridge --subnet 10.253.33.0/24 --label com.docker.compose.project=candidate-wt-9bb3531fa9f1 --label com.docker.compose.network=runtime candidate-wt-9bb3531fa9f1_runtime`. Reproducers need a free pool or an independently verified non-overlapping subnet for their own project; never prune other networks.

## Observed checks and reproduction

Strict TDD RED: `pytest -q tests/test_usage_read_acceptance.py -k cross_incident` in the checks container yielded **3 failed, 41 deselected (8.08s)** before source edits: identical/different consumption was incorrectly complete, and 1001 related rows returned 200 instead of 413. Container Ruff formatted both files before GREEN. Refactor review retained the narrow implementation without further source edits.
GREEN: **48 passed (18.45s)**; historical regressions: **103 passed (33.87s)**; Ruff lint passed and both files already formatted; `git diff --check` passed. Capture rerun: **2 passed, 42 deselected (7.00s)**. No required local behavioral check failed or skipped after repair. Schema/release checks and live-provider probes were not run in this slice.
Set `EVIDENCE_DIR` to a new, owned, writable local directory before the capture command; pytest recreates its `capture` child. Run sequentially because the isolated database schema is recreated by tests.

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_usage_read_acceptance.py tests/test_audit_events_contract.py'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_demo_seeds.py tests/test_incident_persistence.py tests/test_health.py tests/test_control_authorization_order.py tests/test_control_acceptance.py tests/test_responses.py tests/test_responses_asgi_errors.py'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm python-checks sh -c 'ruff check --no-cache src/sre_agent/gateway/usage.py tests/test_usage_read_acceptance.py && ruff format --check --no-cache src/sre_agent/gateway/usage.py tests/test_usage_read_acceptance.py'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm --user "$(id -u):$(id -g)" -v "$EVIDENCE_DIR:/evidence" python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_usage_read_acceptance.py -k cross_incident_attribution --basetemp=/evidence/capture'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks exec -T python-checks-db psql -U python_checks -d python_checks -P format=unaligned -c "SELECT operation, count(*) AS evidence_rows, count(DISTINCT correlation->>'request_id') AS requests, count(DISTINCT correlation->'incident_ref') AS incident_refs, count(DISTINCT consumption) AS consumption_variants FROM audit_events WHERE operation='responses.create' GROUP BY operation;"
```

## Runtime evidence and criterion mapping

Primary evidence: **controlled integration**, not live external service. Tests project synthetic audit events through `PostgresAuditStore`, then execute real FastAPI GETs with TestClient. The [response](issue-333-cross-incident-response.json) is the successful incident-a body from parameter `0.0012300`, saved under `capture/test_cross_incident_attributio0/incident-a.json`; it was copied unchanged except the test's JSON indentation. Three rows share one request across two incidents; an unrelated fourth row is excluded. Expected/actual: one unknown request, two selected runs, null totals. Both parameter scenarios assert the other incident excludes foreign runs; request/month reads also retain uncertainty.
The [SQL output](issue-333-cross-incident-sql.txt) was captured immediately after the second parameter (`0.0080000`): 4 response rows, 2 requests, 3 protected incident references, 2 consumption variants. The [real screenshot](issue-333-cross-incident-response.png) is Chromium's native rendering of the saved FastAPI JSON, not a mock page, generated image, old capture or Swagger. A fresh local browser profile was used; sandbox execution initially failed before capture, then approved execution succeeded. Open the reproduced JSON in a browser to repeat the view.
CA1/CA2: both new conflict scenarios, real 1000/1001-row boundary, and existing same-incident/UTC/cross-month scenarios pass. CA3/CA4: explicit uncertainty and historical billed precision pass at runtime; schema invariants remain U333-7. CA5/CA6: uncertainty, bounded selectors, authorization, terminal audit and failure suppression pass. CA7: existing controlled-provider response-to-persisted-read scenario passes; no live provider was contacted.
Sanitized: yes. JSON/SQL and the image were inspected: only controlled fixture names and aggregate values; no headers, credentials, personal data, prompts or provider outputs. Deferred: media storage unavailable; screenshot evidence is mandatory.

## Historical review-resolution ledger

All eight threads were read from the parent's refreshed, paginated inventory. All remain unresolved remotely; only the audit-before-release thread is outdated. Reviewed SHA aliases: S=`4f090b9e93cb0ea9a24908ace6091806c5c5674c`, A=`683e5ce50d5fca26fbc9604bf34f54073678b326`, M=`87788510f1b8e4d4d5265a4fd68beb000d877e18`, D=`39da3f17e0d1382f0208eec803bdcd3b91ea8629`. Every current disposition refers to the base-plus-patch identity above; no thread was remotely resolved.

| PR/thread | Reviewed SHA / outdated | Finding / CA | Current disposition and evidence | Next owner/dependency |
| --- | --- | --- | --- | --- |
| [383/4111980005](https://github.com/creep1ng/sre-agent/pull/383#discussion_r4111980005) | S / no | Cost metadata coupling / CA4 | Pending; schema untouched | U333-7 writer |
| [383/4111980011](https://github.com/creep1ng/sre-agent/pull/383#discussion_r4111980011) | S / no | Coverage/count invariant / CA3 | Pending; schema untouched | U333-7 writer |
| [384/4112401286](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112401286) | A / yes | Audit-before-release / CA6 | Already-addressed-and-retested: commit-before-response and all audit-failure outcomes pass in 48-test run | Human review |
| [384/4112422103](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112422103) | A / no | Published contract activation / CA6 | Pending; immutable 2.4.0 untouched | U333-8 version/size coordination |
| [384/4112620099](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112620099) | M / no | Expected Alembic head / CA7 | Already-addressed-and-retested: seed/migration/readiness in 103-test run | Human review |
| [384/4112620102](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112620102) | M / no | Authorization denial cause / CA6 | Already-addressed-and-retested: persisted denial cause in 48-test run | Human review |
| [384/4112620103](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112620103) | M / no | Bearer challenge / CA6 | Already-addressed-and-retested: 401 challenge in 48-test run | Human review |
| [384/4112799605](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112799605) | D / no | Cross-incident duplicate selection / CA1–CA3 | Reproduced then fixed-and-verified: 3 RED failures, 48 GREEN, real capture | Independent verification / human review |

Rollback: revert only this slice's usage query/aggregation, added behavior scenarios and associated evidence/tracker changes; no migration, schema or release rollback. Old recovery roots, remote branches and RDD settings were untouched. No commit, push, PR mutation, merge, issue closure, tag or deployment was performed by this writer.

## Independent verification and parent readback

Independent verification repeated 48 usage/audit tests and 103 regressions, lint/format and whitespace checks successfully; the 2,162-file hash/mode inventory showed zero candidate drift. The saved screenshot and JSON were visually inspected and byte-matched to the actual capture. The verifier confirmed the recorded three RED failures but could not recover the historical RED image's immutable pre-edit source hash; RED is observed writer evidence, not independently reconstructed source evidence. The parent repeated the 48-test usage/audit command: **48 passed in 23.25s**, and inspected the source, evidence and scoped 300-line text diff. Hosted CI and human acceptance remain separate pending requirements; the PR body binds the eventual commit SHA to these unchanged source/test hashes.
