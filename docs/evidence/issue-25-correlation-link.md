# Issue 25 safe correlation navigation

Authorized follow-up: safe same-origin request-ID navigation plus explicit safe
rendering of the event's opaque correlation references. Current main is
`ef5ba500e673160aa73d92fffc61ee452c284bc6`; #493 contract 2.7.0 is merged,
human-accepted, and all hosted gates succeeded. The #491 stack is restacked on
that main (parent #386 `f87d134ab69e743e9c1662224c29ca0912961f2e`). UI Git blob: `06164fbb18614a298afd98f8f806cfda80f30e4b`; served SHA-256:
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
The pre-restack #491 source passed **8 Playwright journeys (16.4s)** and **68
targeted Python checks (57.24s)**. Docker socket access was denied during this
restack, so those checks were not rerun on the exact new merge commits. Full
`python-checks` (1562 passed, 1 skipped) ran on `080bef8c109b5d21c108ce501ea1aaaff460c8db`
(main 677, before the contract-only main merge); it is not a fresh full-suite run
on the current leaf. The final restack keeps byte-identical `src`, `public` and
`tests` trees versus the prior #491 candidate.

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

## Remaining findings and acceptance gaps

Two runtime P1s remain outside this navigation UI: #378 still lacks terminal
audit records for audit-read outcomes, and the separate legacy event-ID lookup
path still needs its governed-404 compatibility follow-up. These captures do not
exercise either behavior. The separate contract PR #493 corrected the additive
contract-ID union and is merged on current main; its acceptance is not proof of
the outstanding audit-runtime fixes.

P2 truncation notice and hidden 404 remain. Missing-filter interactions with
forbidden query keys, real database outage, browser-offline behavior, live
provider, and independent human acceptance were not demonstrated. Do not treat
these captures or the full-suite result on the earlier candidate as full #25
acceptance. RDD disabled/unmanaged. Keep #490 and this #491 follow-up as separate
size-bounded delivery units; no merge or issue closure is claimed.
