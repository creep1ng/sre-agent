# Issue 25 audit review evidence

Reviewed stack: #378 -> #379 -> #385 -> #386, integrated with current main
`677fb76ae345e223d4313e8c5bcbdbd7acb9bbf3`; evidence unit #490 is based on
`080bef8c109b5d21c108ce501ea1aaaff460c8db`. The user corrected the target to
#25, not #330. Live Project midnight.agent: Todo. P0/P1 findings were confirmed
and corrected in bounded follow-ups: observable leakage checks on #386 and safe
correlation-detail rendering on child #491. No unverified finding is represented
as fixed; no issue closure or merge is claimed. RDD disabled/unmanaged.

## Findings and remaining gaps

- **P2** `public/admin/audit-events.js`: ignores `truncated`; partial results are
  announced as ordinary counts. Pagination remains deferred to #470.
- **P2** detail 404 is hidden by list reload; current browser assertion checks
  hidden text, not visible error state.
- P1 source-scanning browser checks were replaced with behavior assertions for
  rendered DOM, storage and requests. The selected-event detail now renders
  request UUID and opaque incident/run/task HMAC digests via text content only;
  no raw identifiers or links are derived from those refs. No trace ref was
  produced by this producer input, so trace rendering is not evidenced.

## Observed results and criterion mapping

Latest controlled HTTP/SQL capture: `2026-10-07T03:11:46.012109+00:00`;
correlation browser capture: `2026-10-07T03:12:59.985Z`. On final #491 leaf,
8 Playwright journeys passed (16.4s), and 68 targeted Python checks passed
(57.24s). Full `python-checks` on prior current-main/#386 candidate
`080bef8c109b5d21c108ce501ea1aaaff460c8db`: 1562 passed, 1 skipped
(483.51s); this full-suite result predates the #491 UI-only change. No strict-TDD
mode was verified; browser failure-first checks were observed for the fixes.

| Criterion | Evidence / boundary |
| --- | --- |
| CA1 | Actual filtered/bounded HTTP list, exact request correlation and empty query; existing PostgreSQL matrix checks window/order/limit. Pagination is deferred; truncated notice remains P2. |
| CA2 | Allow200, deny403, auth401, invalid422 and provider503 each have a matching persisted HTTP/list/detail/SQL row. Connected UI screenshots show metadata and opaque refs. |
| CA3 | Missing-filter/content-query controls return422. Audit projections/UI omit content; synthetic-marker checks exclude audit metadata. |
| CA4 | UI omits token/cost; capture does not invent consumption. Provider is deterministic/injected, not an external model. |
| CA5 | Unauthorized/admin-boundary reads return401/403 with zero rows; injected audit-store failure returns producer503 and no persisted row. Real database outage was not tested. |
| CA6 | Injected store-failure case returns503, SQL count0 and empty list. No event is fabricated. |

`issue-25-audit-http.json` records actual metadata responses and SQL projection;
`issue-25-audit-connected.png` is a real Chromium capture through Nginx/API/DB.
The separately refreshed #491 correlation JSON and allow/deny screenshots show
same request/event IDs as that HTTP artifact, read statuses200/403/200, zero
restricted rows, and visible incident/run/task refs. All screenshots were
inspected; artifacts contain no credentials, prompt or provider output. This is
controlled integration with real PostgreSQL and an injected provider, not live
external-provider or database-outage evidence.

## Repeatable containerized recipe

Prerequisites: candidate checkout and committed capture helpers; Docker; ignored
`.env.worktree` based on `.env.example` with synthetic unique keys, long audit
HMAC key, lab model/provider values, no OpenRouter credentials, and isolated
`DATABASE_URL` host `db`, database `sre_agent`. Never print/share the env file.
The verifier rejects another DSN and does not reset/drop schema or tables.

```sh
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml up -d --build web
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks build python-checks
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks run --rm python-checks pytest -q tests/test_audit_reads_unit.py tests/test_audit_reads_http.py tests/test_demo_seeds.py tests/test_audit_events_ui.py
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/audit-events.spec.js
docker run --rm --network audit25-review_runtime --env-file .env.worktree -v "$PWD/scripts/verify_issue25_audit.py:/app/scripts/verify_issue25_audit.py:ro" audit25-review-python-checks python /app/scripts/verify_issue25_audit.py > docs/evidence/issue-25-audit-http.json
docker run --rm --user "$(id -u):$(id -g)" --network audit25-review_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_audit.mjs:/e2e/capture_issue25_audit.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-review-e2e node /e2e/capture_issue25_audit.mjs
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks --profile e2e down
```

Expected producer statuses allow200, deny403, auth401, invalid422, provider503,
audit-store503; observed SQL row counts 1,1,1,1,1,0. Reads: unauth401,
nonadmin403, missing/content filter422, empty query200 with no rows. Each run
creates fresh correlated demo rows; compose cleanup retains its named volume.

## Acceptance boundary

No live provider, killed-database, browser-offline or independent human acceptance
was run. Full Python suite belongs to the pre-#491 candidate stated above; do not
attribute it to the final leaf. CA1-CA6 have the bounded evidence listed, but
#25 acceptance remains partial while P2s, outage cases and human acceptance are
open. Screenshot inspection is not a substitute for human PR review.
