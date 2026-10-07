# Issue 25 integrated closure-gap verification

## Candidate and scope
The tested joint source candidate is `e1847a66554285c4e0400728fdc5c2bc46515ea8`:
PR378 → PR379 → PR385 → PR386 → PR490 → PR491 (`343402e`) plus the five
bounded correction commits. Its contract base is merged main `ef5ba500` (2.7.0).
Later evidence/tracking-only commits do not replace the tested source identity.
Every new capture below is from this joint candidate, **not** evidence that an
earlier parent independently implements its descendants' UI functions.
Runtime source manifest SHA-256: `13a2b1fb891a93835205cf81fd8c2ab2e4889a3952290690b434a0d5088ffe03`.
The manifest hashes sorted `src/**/*.py` paths, NUL, file hash, and newline.
The HTTP helper also records its own hash; browser captures record served UI hash.

Live Projects #8 lists #25 as Done; the issue was human-closed at
2026-10-07T03:24:35Z, but the runtime stack remains open and unmerged.
Pagination remains explicitly deferred to #470; it is not accepted as delivered.
Scope is the five requested closure gaps. The active goal authorizes conditional
PR merges, not protection bypass or treating the closed issue as proof of delivery.
Route: delegated direct. AGENTS failure-first policy, no verified strict-TDD toggle.
RDD: disabled/unmanaged (global off); independent human acceptance remains required.

## Criteria and evidence
| Criterion | Observed proof / boundary |
| --- | --- |
| CA1 bounded filters | HTTP/SQL producer correspondence; forbidden parameters tested with valid decision filter. Truncation is explicitly partial. Stable pagination is deferred, not fulfilled. |
| CA2 safe detail | Actual persisted producer status/latency and SQL correlation; connected allow/deny navigation. SQL helper emits only request UUID and HMAC references, never raw IDs/content. |
| CA3 no content | Browser sensitive-marker checks before Apply while detail is open and after Apply; forbidden parameters + valid filter reject422. |
| CA4 no invented consumption | Existing metadata-only projection and browser checks; no tokens/cost computation added. |
| CA5 authorization/outage | HTTP401/403 no partial items; query-only fault after authenticated/authorized lookup persists503. Connected DB fault clears prior UI rows/details and displays503. |
| CA6 durable terminal/release gate | Actual per-request SQL deltas for read200/401/403/404/422/503. Append failure returns503 and zero rows; no-op/double-append mutations are rejected by the capture probe. |

`issue-25-audit-http.json`: controlled FastAPI/PostgreSQL + deterministic provider,
not a live provider outage. Producer statuses200/403/401/422/503 have counts1 each;
failed producer append503 has count0. `read_controls.sql_count` refers only to
`responses.create` rows for an unused selector, not to the new terminal read rows.
`issue-25-terminal.jsonl` records those terminal rows independently.
`issue-25-audit-browser.json` labels injected detail404/503 and truncation as mocks.
`issue-25-correlation.json` and `issue-25-query-failure.json` are connected UI proof.
The connected fault deliberately renames the audit table: both its SELECT and append
become unavailable while identity/grant tables remain intact. It is not a killed
database or query-only append-success proof; the HTTP boundary suite covers that.

## Verification
- API failure-first: 7 failed/22 passed on baseline; corrected five-file run29 passed44.54s.
- Browser failure-first: 3 failed/8 passed; first correction run10/11 exposed a
  malformed503 mock fixture, fixed to the contractual `audit_unavailable` envelope.
- Worker browser GREEN11/11 in22.2s; parent independent browser GREEN11/11 in31.3s.
- Parent full Python:1567 passed,1 skipped in691.34s; Ruff/format/locked deps,
  import boundaries and mypy passed. The skip is the opt-in live OpenRouter case.
- Connected captures: allow/deny200→403→200; actual list-query fault200→503
  cleared1 prior row/detail to0/0, visible error; table restoration verified.
- All three new browser JSON artifacts match served UI SHA-256
  `12497e0a9287d8f5890c3ac3fb81c550cd99b63f20ef57f83e0bdc4571aa8ae2`;
  SQL/HTTP helper source manifest matches the actual committed Python source.
- Existing compact/braced UUID parser permissiveness was not expanded; an abandoned
  experiment added no surviving tests or runtime changes for that separate behavior.
- No hosted CI pass, independent human acceptance, live provider, killed-DB or
  offline demonstration is inferred from local results.

## Environment and safe reproduction
Git/Docker host; Python3.12.14, PostgreSQL17.4 pinned digest and Playwright1.63.0
images/lockfiles from the tested source. Prepare ignored mode600 `.env.worktree`
from `.env.example`: DB `audit25_closure`, user `sre_agent`, URL host `db`, fresh
synthetic keys/HMAC, `lab/model` + `lab`, no external keys, contract2.7.0,
build revision equal to the tested SHA. Never print/source/upload this file.
Use a fresh Compose project; choose an unused `ISSUE25_EVIDENCE_SUBNET` when needed.
Existing services only; combine the no-host-port overlay with the small IPAM overlay.
The terminal helper resets only disposable `python_checks`, never the evidence DB.

```sh
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml up -d --build web
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks run --build --rm python-checks
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/audit-events.spec.js
docker run --rm --network audit25-closure_runtime --env-file .env.worktree audit25-closure-python-checks python scripts/verify_issue25_audit.py > docs/evidence/issue-25-audit-http.json
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks run --rm python-checks sh -c 'pytest -q tests/test_audit_read_terminal_boundary.py && python scripts/capture_issue25_audit_terminal.py'
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_audit.mjs:/e2e/capture.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_correlation.mjs:/e2e/capture.mjs:ro" -v "$PWD/public/admin/audit-events.js:/candidate/audit-events.js:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
```

## Connected query-fault reproduction
Only run on this fresh synthetic stack. The browser runs in the existing Playwright
image. A separate controller in the existing Python checks image waits for the
connected browser's precondition, renames only `public.audit_events`, activates the
browser fault, and restores/verifies the table in `finally` after success, capture
failure, marker-write failure, or bounded timeout. It accepts only the isolated
database host `db` and database `audit25_closure`; it has no Docker socket or new
service. The browser's own query-failure wait is bounded at90seconds; controller
marker waits default to120seconds. Do not terminate the controller or stop the
Docker daemon while the fault is active; external process interruptions do not
guarantee cleanup. The marker-writing browser/controller containers use the host UID
and GID so the host can inspect and remove their files.

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e sh -c 'rm -f /evidence/query-fault-ready.json /evidence/query-fault-active /evidence/query-fault-done /evidence/issue-25-query-failure-failed.json'
docker run --rm --detach --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_query_failure.mjs:/e2e/capture.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/control_issue25_query_fault.py:/app/scripts/control_issue25_query_fault.py:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-python-checks:latest python /app/scripts/control_issue25_query_fault.py
docker run --rm --network audit25-closure_runtime --env-file .env.worktree audit25-closure-python-checks:latest python -c 'from sre_agent.settings import Settings; import os,psycopg; s=Settings.from_environment({k:v for k,v in os.environ.items() if not k.startswith("OPENROUTER")}); c=psycopg.connect(s.database_url); print("table_flags="+str(c.execute("SELECT to_regclass(%s) IS NOT NULL,to_regclass(%s) IS NULL",("public.audit_events","public.audit_events_issue25_fault")).fetchone())); c.close()'
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks --profile e2e down
```

The controller exits nonzero for a failed browser capture or a timeout, but still
checks and restores the table after the rename; the readback prints `(True, True)`
only when the original table exists and the temporary fault name is absent.

## Technical acceptance
Historical local technical acceptance covered the five requested corrections on
source candidate `e1847a66554285c4e0400728fdc5c2bc46515ea8`, based on independent
Docker verification, HTTP/SQL invariants and inspected real browser captures.
CA1 is accepted only for bounded filtering and truthful truncation; #470 remains
deferred. This is local technical acceptance, not independent human acceptance,
hosted CI, merge permission, issue closure or delivery of stable pagination.
Fresh Codex findings on PR498–502 qualify this historical acceptance. The next
corrected candidate requires new behavioral checks, populated correlation evidence
and capture-failure restoration verification before renewed explicit acceptance.
Rollback: revert the bounded follow-up commits; immutable contract releases untouched.
Sanitized: yes. Only synthetic metadata and actual browser captures may be published.
