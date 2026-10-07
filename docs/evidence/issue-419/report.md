# Issue 419 — authenticated identity evidence

> **Historical evidence — superseded candidate.** `replay.json` and `review-receipt.png` describe the former combined #488 candidate and are preserved for provenance. The refreshed evidence below is bound to the local #489 candidate source SHA `aac524061716635339a91e2f84d8ebf00ce58249`; it is not evidence of hosted CI, human review, PR integration, or issue closure. The historical sections below remain only as provenance.

## Final local #489 candidate (2026-10-07)

The local candidate is branch `work/issue-489`, source commit `aac524061716635339a91e2f84d8ebf00ce58249` (`fix(ui): prevent refresh during pending command`), based on combined local merge `5f36349f67bc2bbef58f2889f54c2eab658f081a`. That merge combines the unchanged local #488 backend candidate `06fb91efccae99e23d8c5fd9f693c7270de11418` and #416 frontend candidate `161258165a0cd29e2243efae85cf8fb1fe71363c`, both descended from main `a3541a96d83364a126ceff418ed3cbf7dbdc2d82`. The sibling branch heads were not modified. The #489-only Refresh-lock source/test change was transplanted from the immutable original range `81796a1803f470eb22b8d02c3294c6423db598f8..87878e6365a9a039194bc4ba0b30ee52f7a2ed9f` (source commit `fa4c0d46e70ecf9a354da50ea2ec35514f34526d`); no other behavior was added. The selected two-file transplant patch is byte-for-byte identical to the corresponding paths in that original range (patch SHA-256 `a5433005540330433783494565ee5a578107cf32f9a2af790c4c3d2c5649c6ef`).

The parent reports a fresh #416 review at `161258165a0cd29e2243efae85cf8fb1fe71363c` with P2 comment `4207229849` requesting this pending-command Refresh lock. The combined #489 candidate addresses that finding in `public/incident-ui/review.js` (`setSubmitting` disables Refresh; `loadAll` returns while submitting; `submissionComplete` prevents a second action after acceptance) and `tests/browser/review.spec.js` (the request is held pending while the test asserts Refresh remains disabled and exactly one command is sent). This is code-level remediation on combined #489, not a claim that standalone #416 contains the fix or that the review thread has been replied to/resolved; the parent owns those review operations.

### Observed checks

- Strict TDD reproduced the race before the source edit: the browser assertion that Refresh stays disabled while a command POST is pending failed, with **1 failed / 11 passed**. After the transplanted fix, the existing browser review suite passed **12 tests**. This browser suite uses its declared mock HTTP seam for credential-change/clear cancellation, action stability, reason recovery, and the in-flight double-submit/Refresh lock; it is not the packaged-server proof below.
- Combined focused Python command passed **96 tests**:

  ```sh
  docker compose --env-file .env.example -p issue419final --profile checks run --build --rm python-checks pytest -q tests/test_authentication.py tests/test_incident_command_http.py tests/test_incident_run_http.py tests/test_run_api_contract.py tests/test_incident_workflow_provisioning.py tests/test_incident_review_ui.py
  ```

- Full checks passed at the source SHA: `docker compose --env-file .env.example -p issue419final --profile checks run --build --rm python-checks` — exit 0, **1,575 passed, 1 skipped**. The skip is the opt-in live OpenRouter smoke test. Repository format/lint, contracts, typing, migration and isolation checks completed successfully in that run.
- A one-off browser replay against the original production API/web Dockerfiles first returned 403 when loading the synthetic run because the isolated seed contained no demo-human run grants. No application code changed. I then used the repository's governed `scripts/provision_incident_workflow.py` against only that isolated database; it returned 201 for the workflow and all four grants and read each grant back active. The real packaged replay then passed **1 Playwright test**.
- Two earlier provisioner invocations also failed before database writes: the first exited 2 because the local adapter passed a 128-character audit value where the script requires 64 hex characters; the second exited 1 with `ModuleNotFoundError: No module named 'asyncpg'` after forcing an unsupported driver. The successful invocation passed the existing hex HMAC value and the repository's `postgresql://` DSN, which the `Database` helper adapts to installed psycopg. No source or database behavior changed to mask these setup errors.
- The real replay used synthetic credentials/data, original packaged API image `sha256:7851425b28732efb5d6f58bc7c8286eef5c0e0eee56ec918e2cb47bf69218f99`, web image `sha256:67dbcef4507e9d5e935f79cebe606fc7c76a13e1c88cdab1773d2abd25cf7758`, and API build revision `aac524061716635339a91e2f84d8ebf00ce58249` (Nginx 1.27.5, Playwright 1.63.0). All containers/data were scoped to Compose project `issue419finalreplay`.
- Real packaged `GET /api/v1/whoami` returned only `demo-human` for that credential and only `admin-human` for the distinct admin credential. The invalid synthetic credential received the generic 401 envelope with no principal. OpenAPI exposed the mounted Bearer-protected endpoint and `principal_id` response. The database grant readback shows demo-human has only its four `run.*` workflow grants, with no `admin.read` grant.
- The packaged UI submitted `approve_mitigation` with `actor_reference` `demo-human`; the API returned 202. SQL readback shows exactly one persisted decision for that run, attributed to `demo-human`. A separate command claiming `admin-human` under the demo credential received 403 `actor_attribution_mismatch`; its run has **zero** persisted decisions.
- Existing `tests/test_authentication.py::test_all_authentication_failures_are_uniform_and_stop_before_resources_or_upstream` covers missing, malformed, unknown, revoked, expired, and inactive-principal credentials. It asserts the same generic 401 response, no credential leakage, and no resource/upstream access. The focused suite above passed this check. The actual packaged replay independently confirmed the invalid-credential case.

The sanitized actual outputs are [the replay response](current-replay.json), [the SQL readback](current-sql.txt), and [the browser screenshot](current-review-receipt.png). The screenshot was captured from the real packaged UI after the credential field was cleared; SHA-256 `ba880b2769b53b714041d28f2d3126566f33c68274e5d09fd66a1734e73f5498`. The one-off replay script/config and exact captured inputs remain in local scratch directory `work/issue-419-final-evidence/`; they are not production source or committed test harness.

### Reproduction commands

Focused browser review suite:

```sh
docker compose --env-file .env.example -p issue419final --profile e2e run --build --rm --no-deps -v "$PWD:/workspace:ro" -v /tmp/playwright-issue419-review.config.js:/e2e/playwright-review.config.js:ro e2e npx playwright test --config=/e2e/playwright-review.config.js
```

Reproduction command for the packaged replay (the observed run mounted `/tmp/issue419-final-replay.spec.js` and `/tmp/playwright-issue419-final.config.js`; the retained `work/` copies below are byte-identical. These exact container commands document the local run; they are not turnkey from a GitHub checkout because the referenced helper files, output mount, and `/tmp/issue419finalreplay.env` are local-only and uncommitted. No reusable replay harness is included. The environment contains only synthetic credentials and is not committed):

```sh
docker compose --env-file /tmp/issue419finalreplay.env -p issue419finalreplay -f compose.yaml -f compose.e2e.yaml --profile e2e run --build --rm --no-deps -v "$PWD/work/issue-419-final-evidence/replay.spec.js:/e2e/tests/browser/issue419-final-replay.spec.js:ro" -v "$PWD/work/issue-419-final-evidence/playwright.config.js:/e2e/playwright-review.config.js:ro" -v "$PWD/work/issue-419-final-evidence:/evidence" e2e npx playwright test --config=/e2e/playwright-review.config.js
```

The synthetic records were seeded from the tracked fixture with the local-only helper, then workflow/grants were established through the existing governed provisioner. The original seed invocation used the identical script copy in `/tmp`:

```sh
docker compose --env-file /tmp/issue419finalreplay.env -p issue419finalreplay run --rm --no-deps -T -v "$PWD/agent/fixtures/incidents/otel-payment-failure/initial-state.yaml:/fixtures/initial-state.yaml:ro" --entrypoint python api - < /tmp/issue419-final-seed.py
set -a; . /tmp/issue419finalreplay.env; set +a
docker compose --env-file /tmp/issue419finalreplay.env -p issue419finalreplay --profile checks run --rm --no-deps -e "DATABASE_URL=${DATABASE_URL}" -e "ADMIN_API_KEY=${ADMIN_HUMAN_API_KEY}" -e "AUDIT_KEY_HEX=${AUDIT_HMAC_KEY}" python-checks python scripts/provision_incident_workflow.py
```

The successful provisioning output was `catalog_status: 201`, all four grant status fields `201`, and all four persisted-active checks `true`. Retained local scratch copies of the seed/replay helpers and config are under `work/issue-419-final-evidence/`; their hashes match the original `/tmp` inputs. The one-off replay helper calls the packaged service through Nginx and records only synthetic identities, response bodies, command attribution, and the credential-cleared UI. It does not persist Authorization headers or provider secrets.

### Remaining boundary

This is local candidate evidence only. It does not establish the subsequent PR branch/base state, a fresh human review, GitHub merge, or issue closure; those remote operations belong to the parent and were not observed in this local replay. After sibling integration, preserve the tested #489 source bytes when retargeting; re-run final checks if any candidate bytes change.

## Former local backend candidate — historical (2026-10-07)

The candidate mounts `GET /v1/whoami` on the application and returns only the authenticated principal identifier through the existing bearer-authentication boundary. The endpoint has focused HTTP/OpenAPI coverage. Strict TDD observed 9 failures / 19 deselected before the endpoint existed; after implementation, the focused backend suite passed 92 tests and the full checks service passed 1,574 tests with 1 skipped (the existing opt-in live OpenRouter check). These are local code-test results, not hosted CI, packaged UI proof, or final #419 acceptance. Exact backend candidate commands and boundaries are recorded in [the committed backend candidate evidence above](#final-local-489-candidate-2026-10-07); these older result counts remain historical evidence only.

---

The remainder of this report records the prior combined candidate and its historical evidence only.

## Scope and contract
Local dependency-first implementation; no remote merge, publication or issue closure. Live Project #8 (`midnight.agent`) recorded #419 and #330 as Todo on 2026-10-06. Prepared dependency base: `683d1acc97adb3392e7b26e39b99c9c558a5c0bf` on original `fe6fca024fec4f89f7538dc5dc03159a99f12a2a`; imported PR #458, #416, #410 and #413 as separate local commits. Route: delegated direct. RDD: disabled/unmanaged.

`GET /v1/whoami` reuses the bearer authentication boundary, requires no administrative grant and returns exactly `{ "principal_id": "<authenticated principal>" }` with `Cache-Control: no-store`. Missing, malformed, unknown, revoked, expired credentials and inactive principals receive the existing generic 401 envelope (`authentication_failed`, request_id, retryable=false, WWW-Authenticate: Bearer). Runtime `/openapi.json` documents the typed response and bearer requirement. It is not an arbitrary-principal lookup.

The published `run-command:1.0.0` request remains unchanged: `actor_reference` is required with reference_version `1.0.0` and principal_id. The browser fetches whoami at each submission and retains no identity cache. Credential clear/change invalidates outstanding UI work. The #330 handler authenticates independently, resolves authorization server-side and rejects a mismatched claimed principal; the claim never supplies authority or the persisted principal ID.

## Observed evidence
- Strict TDD: endpoint RED 9 failures/19 existing passes; browser RED 4 failures/7 passes. An initial expiry-fixture constraint error was corrected and is not counted as feature RED.
- Writer relevant API/auth/contract checks: 78 passed. Independent Chromium review journeys: 11 passed (mock HTTP seam, explicitly not live API evidence).
- Original API and web Dockerfiles built successfully. The first API build with `--network none` could not download uv; the normal locked-dependency build passed. Packaged source hashes match the checked-out source.
- Real Chromium through packaged Nginx/FastAPI/PostgreSQL: whoami 200 (`demo-human`); approval 202 and current_state `verifying`; mismatched `sender-human` claim 403 `actor_attribution_mismatch`. This is controlled integration, not an external remediation demonstration.
- SQL confirmed one decision for `inc-issue419-browser`; `inc-issue419-mismatch` stayed `mitigating` with zero decisions. [Actual sanitized responses](replay.json) and [actual UI receipt](review-receipt.png). Screenshot SHA256: `763ab97a5d9bd6e1554847d06a6470921c563a14eb76f4d19882b89585320a1b`.
- An initial live replay raced API startup and received 502. Retried only after Uvicorn startup; the observed accepted receipt is from the ready run at `2026-10-07T00:09:36Z` (2026-10-06, America/Bogota).
- Repository-wide Ruff lint/format, offline uv lock check, run API validator, all five import-boundary contracts and mypy (13 source files, including whoami) passed after one mechanical test-format correction. First independent full suite: 1562 passed, 1 skipped, 2 failures and 11 setup errors. Duplicate provisioned grants and the obsolete UI principal_id ban were reconciled in existing tests; migration downgrade failed because roles are cluster-global and the separate synthetic demo database still depended on sre_incident_reader. After preserving the replay, the entire owned cluster was replaced with a fresh checks-only cluster; final independent full suite passed **1575 tests**, with **1 skipped** opt-in live OpenRouter request (`RUN_OPENROUTER_LIVE_SMOKE=1`), in 283.00 seconds. No migration or production behavior was changed to mask the environment failure. Compose isolation guard, shellcheck and Alembic check passed (`No new upgrade operations detected`).

## Reproduce
Host prerequisites: Git, Docker/Compose, an untracked configuration prepared from `.env.example` with all required interpolation values filled with local, non-production values. No provider credential is needed for these checks. Never print or commit that configuration. The checks service uses its own tmpfs PostgreSQL, not demo data.

```sh
docker compose --profile checks run --build --rm python-checks pytest -q tests/test_authentication.py tests/test_incident_command_http.py tests/test_incident_run_http.py tests/test_run_api_contract.py tests/test_incident_workflow_provisioning.py tests/test_incident_review_ui.py
```

The exact Compose recipe above was executed in a separate ephemeral project: **96 passed**, including the previously failing start fixture and UI guard.

The real receipt can also be reproduced in the UI with a synthetic incident/run awaiting mitigation approval and an active human credential granted run.read/run.approve by the governed workflow provisioner: open the review URL, enter that credential and approve. Observe GET `/api/v1/whoami` followed by POST `/api/v1/incidents/{incident_id}/runs/{run_id}/commands`; the body includes the returned actor_reference. Against a fresh equivalent run, use the same credential but a different claimed principal; expect 403 and no decision. The real local replay used only dedicated `issue419-*` containers/network and separate checks/demo databases; no shared database was touched.

## Safety, risks and remaining gates
Sanitized: yes. Only synthetic IDs, bounded responses and the credential-free UI were retained; bearer material stays outside the repository and evidence. The screenshot is a browser capture, not a generated illustration. No mitigation effect, hosted CI, human acceptance or remote integration is claimed. Ordinary independent human review and publication remain pending. Rollback the #419 change without reverting the separately imported dependency work.

## Artifact binding
API image: `sha256:04a5880467916fe64851cb3a079f12922454bf2786887f6c0000460f8cf8319e`; web image: `sha256:3fd87e156e7c0935872c1f2005df5c2e33308d7ebe412688bff9b3fb8682f17a`. Python 3.12.14, PostgreSQL 17.4, Playwright 1.63.0. Packaged source SHA256: identity.py `7333a2b50be1a4dabac31c77398eff6c54185a00f95e4374f164deffec085606`; application.py `0195242bc0a22f3f51f1dd3f765fb732f84dc6cce1291035132de8803ea4ea40`; client.js `a04e513be13e4e22bbc33a3c61638496165a88cff8e90ea600cb3fe9aacd408b`; review.js `31c38f4c20700a67469052d873b023fe1100dce334b329207d2a71280c928871`. Subsequent edits only correct existing test fixtures/guards/format and add evidence; they do not change these packaged behavior hashes.

## PR review follow-up
Draft [PR #488](https://github.com/creep1ng/sre-agent/pull/488) published after authorization. Codex reviewed2e5284c and found P2 action switching during pending identity; test-first RED reproduced two commands, then disabled action/comment/submit through the request. GREEN12 review journeys; parent independent offline browser56passed/59skipped (two unrelated showcase cases explicitly excluded after networkless asset failures). Existing premature request-array assertions now poll request arrival. Hosted original unit passed; static-web failed that assertion; refreshed CI/re-review pending. Current review.js SHA2564ed113aceceafe65897b860007c6b790e1de065da3159556a2be1de9117cde01 differs from the historical packaged image/screenshot above; fresh packaged replay and human acceptance are required before main integration.
