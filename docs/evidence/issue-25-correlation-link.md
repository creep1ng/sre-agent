# Issue 25 safe correlation navigation

Authorized follow-up: safe same-origin request-ID navigation plus explicit safe
rendering of the event's opaque correlation references. Current main is
`677fb76ae345e223d4313e8c5bcbdbd7acb9bbf3`; the connected capture uses the #491
leaf. UI Git blob: `06164fbb18614a298afd98f8f806cfda80f30e4b`; served SHA-256:
`cb60f3b4003dabc221f1091a093a973792f3b6ace6529dc950bb8b612e9f942c`.
The capture verifies the served bytes match the candidate UI before use.

## Behavior and observed proof

Detail's **View correlated events** link uses only a valid contract
`correlation.request_id`, to a fixed same-origin URL. It clears unrelated query
state; credentials are not carried in URLs and the destination requires new
authentication. Detail renders `request_id` and explicit incident/run/task/trace
reference digest values using text content only; it does not expose raw IDs or
create links from HMAC refs. The observed producer generated incident/run/task
refs, but `trace_ref` was null and is not claimed as visible proof.

Failure-first browser assertions exercise valid UUID navigation, authentication,
malicious values as inert text, and no unexpected navigation/network request.
The current #491 candidate passed **8 Playwright journeys (16.4s)**; targeted
Python audit/UI checks passed **68 tests (57.24s)**. The full Python suite
(1562 passed, 1 skipped) ran on the earlier current-main/#386 candidate
`080bef8c109b5d21c108ce501ea1aaaff460c8db`, before this UI-only change; it is
not attributed to the #491 leaf.

Fresh connected captures at `2026-10-07T03:12:59.985Z` follow actual allow and
deny producer events retained in isolated PostgreSQL. Both request IDs and SQL
event IDs match `issue-25-audit-http.json` from the parent evidence. Each browser
sequence is **200 -> 403 -> 200** (admin, restricted identity with zero rows,
admin); each of three list reads uses exactly the producer request ID. Both
screenshots show the selected event and its request/incident/run/task metadata.
The artifact records visible refs; trace is null. Screenshots were inspected.
These are controlled integrations using a deterministic injected LLM provider,
real PostgreSQL and the connected gateway, not live external-provider proof.

## Containerized reproduction

Use the isolated `.env.worktree` and producer capture recipe in
`issue-25-audit-review.md` first. No external provider keys or shared database.

```sh
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml up -d --build web
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/audit-events.spec.js
docker run --rm --user "$(id -u):$(id -g)" --network audit25-review_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_correlation.mjs:/e2e/capture_issue25_correlation.mjs:ro" -v "$PWD/public/admin/audit-events.js:/candidate/audit-events.js:ro" -v "$PWD/docs/evidence:/evidence" audit25-review-e2e node /e2e/capture_issue25_correlation.mjs
docker compose -p audit25-review --env-file .env.worktree -f compose.yaml -f compose.e2e.yaml --profile checks --profile e2e down
```

## Remaining acceptance gaps

P2 truncation notice and hidden 404 remain. Missing-filter interactions with
forbidden query keys, real database outage, browser-offline behavior, live
provider, and independent human acceptance were not demonstrated. Do not treat
these captures or the full-suite result on the earlier candidate as full #25
acceptance. RDD disabled/unmanaged. Keep #490 and this #491 follow-up as separate
size-bounded delivery units; no merge or issue closure is claimed.
