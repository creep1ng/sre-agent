# Issue 25 safe correlation navigation

Authorized follow-up to the audit review: implement the previously absent link,
not the unrelated P2 fixes or pagination. Delivery route: delegated direct.
Base runtime: `0af22e97d815a1c511b1a24eec14f70d3611be75`, plus uncommitted UI/tests.
UI Git blob: `619ced26be1d901ba74cf3847a69905c887243df`.
Served UI SHA256: `68ceb142c7069cfe9dbc7d66cd7029c0afea0e337f7160849e4e04b36300daf6`;
the capture checks served bytes match the candidate before exercising navigation.

## Behavior and observed proof

Detail now offers **View correlated events**, using only a valid contract
`correlation.request_id`. The destination is fixed and same-origin, not supplied
by the server/user. Opening it prefills that UUID, clears unrelated query state,
keeps credentials out of URLs and requires a new authenticated session. It does
not issue a broad/automatic audit read. Invalid/duplicate IDs show validation;
malicious correlation values produce no link. Nil/uppercase UUIDs match the API.

Failure-first: initial three scenarios failed before UI edits (3 failed/4 passed,
23.3s). An added UUID boundary exposed the initial over-strict parser (1 failed/7
passed, 16.6s); corrected to the API-compatible canonical UUID universe. Final
candidate: **8 browser tests passed (10.3s; restored candidate)** and **24 existing HTTP/PostgreSQL/UI
checks passed (20.20s; restored candidate)**. No unit tests added and no retroactive strict-TDD claim.

Real connected capture at `2026-10-07T01:54:09.884Z` followed both gateway-produced
allow and deny events retained in isolated PostgreSQL. For each, the clicked URL
and all three API reads retain exactly the producer's request ID. Read statuses
are **200 -> 403 -> 200**: admin, restricted identity (zero rows), then admin.
Reload does not carry credentials or query automatically. The reopened detail
matches the SQL event ID and producer status (200/403), with metadata only.

Artifacts: `issue-25-correlation.json`, `issue-25-correlation-allow.png`,
`issue-25-correlation-deny.png`. Both screenshots were visually inspected and
actual synthetic credentials/prompt-output markers checked absent from JSON/DOM.
This proves the safe-link deliverable in the local candidate, not full issue25
acceptance. Other P2s, #470 pagination and independent human review remain pending.

## Containerized reproduction

Use the original review's isolated `.env.worktree` and producer capture recipe in
`issue-25-audit-review.md` first; no external provider keys or shared database.

```sh
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml up -d --build web
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/audit-events.spec.js
docker run --rm --user "$(id -u):$(id -g)" --network audit25-review_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_correlation.mjs:/e2e/capture_issue25_correlation.mjs:ro" -v "$PWD/public/admin/audit-events.js:/candidate/audit-events.js:ro" -v "$PWD/docs/evidence:/evidence" audit25-review-e2e node /e2e/capture_issue25_correlation.mjs
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks --profile e2e down
```

Published navigation evidence; no merge or issue closure. Full repository suite, live external
provider, actual killed-DB/offline demonstrations and human acceptance NOT run.
RDD disabled/unmanaged. Keep review evidence and navigation as separate delivery
units, each <=400 additions+deletions; do not submit the combined diff as one PR.
Rollback: revert the UI/tests navigation unit; backend/storage contracts unchanged.
Sanitized: yes.

## Refreshed parent correspondence

After parent HTTP/SQL evidence refreshed, correlation artifacts were regenerated
from that exact producer artifact on `0295805211ce516bcc6d9a076d29d4b7285947ff`.
Both allow/deny request IDs and SQL event IDs agree with the parent artifact;
actual connected capture again observed200/403/200 and unchanged served UI hash.
