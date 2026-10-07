# Issue 419 — authenticated identity evidence

> **Historical media.** `replay.json` and `review-receipt.png` are retained from a former combined candidate. They are not fresh UI evidence for backend-only #488. The focused browser journeys belong to #416's frontend candidate and use a mock HTTP seam; they are not backend or packaged-stack proof.

## Current local backend candidate (2026-10-07)

The #488 backend candidate tested below was `06fb91efccae99e23d8c5fd9f693c7270de11418`, based directly on main `a3541a96d83364a126ceff418ed3cbf7dbdc2d82`; source commit `a1b61838cee7624c1ef05abb406fc80069bc9cbe` contains its implementation. That implementation is limited to `src/sre_agent/gateway/identity.py`, `src/sre_agent/application.py`, and `tests/test_incident_command_http.py` (132 additions / 2 deletions). It mounts and documents `GET /v1/whoami`, which returns only the authenticated principal ID through the existing bearer-authentication boundary and does not require `admin.read`. This report update is documentation-only; it does not change the tested source or tests.

### Verification

- Strict-TDD RED: **9 failures / 19 deselected** before the endpoint existed.
- Focused backend tests: **92 passed**.

  ```sh
  docker compose --env-file .env.example -p issue419identity --profile checks run --build --rm python-checks pytest -q tests/test_authentication.py tests/test_incident_command_http.py tests/test_incident_run_http.py tests/test_run_api_contract.py tests/test_incident_workflow_provisioning.py
  ```

- Full checks: **1,574 passed, 1 skipped** (opt-in live OpenRouter smoke), exit 0.

  ```sh
  docker compose --env-file .env.example -p issue419identity --profile checks run --build --rm python-checks
  ```

These are local results for the backend candidate, not hosted CI results. This report does not claim a fresh standalone #488 UI screenshot or a packaged UI/API replay. The older screenshot and replay below remain historical only; final UI proof must be paired with the frontend candidate and bound to that combined candidate.

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
