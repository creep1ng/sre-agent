# Issue 25 audit review evidence

Reviewed stack: #378 -> #379 -> #385 -> #386, runtime/UI SHA
`0af22e97d815a1c511b1a24eec14f70d3611be75`. The user corrected the target to #25,
not #330. Live Project midnight.agent: Todo. No production edits, no confirmed
P0/P1, no publication/merge/closure. Route: delegated direct; RDD disabled/unmanaged.

## Findings

- **P2** `public/admin/audit-events.js:134-143`: ignores `truncated`; a partial
  result is announced as an ordinary count. Pagination remains deferred to #470.
- **P2** `public/admin/audit-events.js:186-189,126`: detail 404 is immediately
  hidden by list reload. Existing journey checks hidden title text, not visibility.
- Both are reproduced in `issue-25-audit-browser.json` with explicitly mocked
  responses. They remain unchanged: only P0/P1 correction was authorized.

## Observed results and criterion mapping

2026-10-06 (America/Bogota), HTTP/SQL capture at `2026-10-07T00:13:04.650855Z`:
24 pytest checks passed (15.04s); 4 browser journeys passed (4.8s, three mocked,
one connected API list). New capture helper completed all six producer scenarios.
Ruff check/format passed after helper refactor; no strict-TDD claim or unit additions.

| Criterion | Observed evidence / remaining boundary |
| --- | --- |
| CA1 | Real bounded/filtered HTTP list, exact request correlation, empty query; existing PostgreSQL matrix verifies window/order/limit. Pagination explicitly deferred to #470; truncation notice P2 remains. |
| CA2 | Real allow/deny/401/422/provider503 rows: matching HTTP list/detail and SQL event/status/latency. Connected screenshot renders status, latency, policy and opaque routing refs. |
| CA3 | Missing filter and content query return 422; list/detail omit content markers. UI offers no content controls. |
| CA4 | UI omits tokens/cost; helper does not manufacture consumption. Provider adapter supplies no consumption evidence. |
| CA5 | 401/403 protected reads expose no list; existing injected-store 503 and mocked browser failures pass. Actual killed-database and offline-browser demonstrations were NOT run. |
| CA6 | Injected audit-store failure returns producer503, SQL count0 and API items[] for that request. No invented persisted event. |

Artifacts: `issue-25-audit-http.json` contains actual metadata response bodies and
SQL projection (`event_id`, `response_status`, `latency_ms`); browser JSON records
connected detail and two mocked P2 demonstrations; `issue-25-audit-connected.png`
is an actual Chromium capture through Nginx/API/PostgreSQL, inspected for secrets.
The checked-in helpers are uncommitted review additions; reviewed runtime files
are unchanged. This is **controlled integration**, not live external-provider proof.

## Repeatable containerized recipe

Prerequisites: Git checkout of the reviewed SHA plus these capture helpers, Docker,
and ignored `.env.worktree` based on `.env.example`, with unique synthetic keys,
long audit HMAC key, lab model/provider values, no OpenRouter credentials, and
DATABASE_URL targeting isolated `db`/`sre_agent`. Never print/share that file.
The helper refuses another DSN host/database and never resets schema or tables.
Containers use pinned base images and repository lockfiles; no host package tools.

```sh
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml up -d --build web
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks build python-checks
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks run --rm python-checks pytest -q tests/test_audit_reads_unit.py tests/test_audit_reads_http.py tests/test_demo_seeds.py tests/test_audit_events_ui.py
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/audit-events.spec.js
docker run --rm --network audit25-review_runtime --env-file .env.worktree -v "$PWD/scripts/verify_issue25_audit.py:/app/scripts/verify_issue25_audit.py:ro" audit25-review-python-checks python /app/scripts/verify_issue25_audit.py > docs/evidence/issue-25-audit-http.json
docker run --rm --user "$(id -u):$(id -g)" --network audit25-review_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_audit.mjs:/e2e/capture_issue25_audit.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-review-e2e node /e2e/capture_issue25_audit.mjs
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks --profile e2e down
```

Expected producer statuses: allow200, deny403, auth401, invalid422, provider503,
audit-store503. Observed matching rows: 1,1,1,1,1,0 respectively. Each repeat
creates new correlated demo rows; cleanup removes only this project's containers
and network, deliberately retaining its named volume (no global `down -v`).

## Evidence limits / pending acceptance

Producer HTTP is FastAPI TestClient with an injected deterministic provider and
real PostgreSQL; browser HTTP is the separate running Nginx/FastAPI service.
The provider-unavailable and audit-store-failure injections are declared controls,
not proof of a live provider outage. API release metadata inherits local 2.0.0
settings; the audit-read surface is evaluated against its declared 2.3.0 contract.
Sensitive-marker checks inspect audit responses, not legitimate producer output.
Initial screenshot writing failed due to container UID; rerun with local UID passed.
Full repository suite, live external provider, and independent human acceptance
were NOT performed. Safe correlation navigation/link deliverable is not established
by a manual request-ID filter. #25 is not fully accepted/closed by this review.

Sanitized: yes. Screenshot inspected; no credential/header/prompt/output artifacts.

## Codex correspondence follow-up

The helper now rejects HTTP/SQL disagreement in event ID, producer request
correlation, response status and latency before emitting evidence. A controlled
projection-mismatch probe first accepted all four corruptions; after correction
it rejects all four. The normal six-case real PostgreSQL capture and connected
browser were repeated successfully; this is an injected negative probe, not an
external outage. Capture time: `2026-10-07T01:51:21.269538+00:00`.
