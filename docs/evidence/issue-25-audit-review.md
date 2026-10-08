# Issue 25 audit review evidence

Reviewed stack: #378 -> #379 -> #385 -> #386, integrated with current main
`ef5ba500e673160aa73d92fffc61ee452c284bc6`; #490 restacked base is #386 at
`f87d134ab69e743e9c1662224c29ca0912961f2e`. PR #493 contract 2.7.0 is merged
on this main; the full release was accepted and hosted gates passed. Runtime and
public source trees are unchanged from main 677fb76, so prior controlled HTTP/UI
captures remain byte-matched. The user corrected the target to #25, not #330.
Live Project midnight.agent: Todo. Some P1s were corrected: observable leakage
checks on #386, safe correlation detail on child #491, and additive contract ID
compatibility in #493. Two runtime P1s remain open in separate follow-ups; no
issue closure or merge of the audit stack is claimed. RDD disabled/unmanaged.

## Findings and remaining gaps

- **P2** `public/admin/audit-events.js`: ignores `truncated`; partial results are
  announced as ordinary counts. Pagination remains deferred to #470.
- **P2** detail 404 is hidden by list reload; current browser assertion checks
  hidden text, not visible error state.
- **P1 pending** #378 still lacks terminal audit records for audit-read outcomes;
  a separate authorized runtime follow-up is in progress. The independent legacy
  event-ID lookup path also still needs the governed-404 compatibility follow-up.
- **P1 corrected** source-scanning browser checks were replaced by behavior
  assertions for rendered DOM, storage and requests. Child #491 renders the
  selected event request UUID and opaque incident/run/task HMAC digests with
  text content only. No trace ref was produced, so trace rendering is not evidenced.
- **P1 corrected separately** #493 preserves the additive contract ID union; PR
  #493 was human-accepted, all hosted gates succeeded, and it merged as
  `ef5ba500e673160aa73d92fffc61ee452c284bc6`.

## Observed results and criterion mapping

Latest controlled HTTP/SQL capture: `2026-10-07T03:11:46.012109+00:00`;
correlation browser capture: `2026-10-07T03:12:59.985Z`. On final #491 leaf,
8 Playwright journeys passed (16.4s), and 68 targeted Python checks passed
(57.24s) on the pre-restack #491 source. Docker access was unavailable for a new
run on the exact restacked leaf. Full `python-checks` on `080bef8c109b5d21c108ce501ea1aaaff460c8db`
(main 677, before the contract-only main merge): 1562 passed, 1 skipped
(483.51s); neither result is claimed as a fresh full-suite run on the final leaf.
No strict-TDD mode was verified; browser failure-first checks were observed.

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
open. The two runtime P1s above remain pending. #493 is merged with its hosted
gates successful; this is separate from acceptance of the audit stack. Screenshot
inspection is not a substitute for human PR review.
