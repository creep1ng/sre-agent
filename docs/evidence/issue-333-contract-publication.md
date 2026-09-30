# Issue #333: 2.5.0 usage contract publication evidence

## Status and scope

U333-8 is complete locally: the existing release generator published immutable,
self-contained `2.5.0` with the runtime usage-read contract; `2.4.0` is unchanged.
This is local evidence for the uncommitted candidate on `fix/issue-333-contract-publication`,
base/HEAD `8965cb1978f9363a807279b6ec1b60c76d739e42` (PR #428 parent). The
candidate is **not** a hosted CI result or human acceptance. U333-10 remains
pending parent publication, hosted CI on the eventual candidate, and human review.
No commit, push, PR/GitHub mutation, release tag or deployment was done here.

Release inventory: 197 files; generator reports 202 artifacts and 17 checks.
All 194 published files in 2.4.0 retain their prior hashes; the focused diff
against that release is empty. Existing all-release validation covers 11 releases
(1.0.0–2.5.0). The publication-only size exception was explicitly authorized;
the writer measured 7,461 text additions plus deletions before final metadata
readback; bind the final complete diff at commit, including binary evidence.

## Reproduce locally

Commands use only this checkout's isolated project `candidate-wt-9bb3531fa9f1`
and disposable `python-checks-db`; do not point them at another project or the
demo database. `.env` and `.env.worktree` are ignored local non-production files.
Run sequentially because acceptance fixtures recreate the disposable schema.

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm harness npm --prefix schemas/tooling test
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm harness npm --prefix schemas/tooling run validate:releases
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm harness npm --prefix schemas/tooling run lint:openapi
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm python-checks sh -c 'ruff check --no-cache docs/evidence/issue-333-contract-capture.py && ruff format --check --no-cache docs/evidence/issue-333-contract-capture.py'
```

Observed on the candidate before evidence-only files were added: full Python
runner **1,250 passed, 1 skipped** (60.76s); the sole skip was
`tests/test_openrouter_live.py::test_openrouter_gateway_live_smoke`, disabled
unless `RUN_OPENROUTER_LIVE_SMOKE=1` because it makes a live provider request.
No live provider request was made. Ruff, format, architecture, typing, repository
contract and Alembic checks passed. Tooling: **124 passed**; release validation
passed for all 11 releases; OpenAPI lint passed. Generation completed with 202
artifacts / 17 checks. `git diff --check` passed and `git diff --quiet HEAD --
schemas/releases/2.4.0` confirmed no modifications.

The first tooling run had 121 pass / 3 fail: the active release tail was pinned
to the old version and generated projections were stale after canonical selector
alignment. Both were corrected using existing release tooling; a focused rerun
passed 9/9 and the final full suite passed 124/124. Earlier OpenAPI parity also
exposed nullable optional query schemas and inherited bearer security; the
published canonical contract now matches the actual runtime shape. No previous
release was split, thinned, or regenerated in place.

## Actual HTTP and persisted behavior

Controlled integration, not a live-provider demonstration: the new capture
helper resets only the guarded test database via existing fixtures and reuses
the existing `ControlledAcceptanceProvider`. Reproduce the final capture with:

```sh
docker compose --project-directory "$PWD" --project-name candidate-wt-9bb3531fa9f1 --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm --user "$(id -u):$(id -g)" -e ISSUE333_CAPTURE_PROJECT=candidate-wt-9bb3531fa9f1 -v "$PWD/docs/evidence:/evidence" python-checks python docs/evidence/issue-333-contract-capture.py --output /evidence
```

Observed: `GET /openapi.json` returned 200, advertised contract version 2.5.0
and canonical `/v1/usage/consumption`; `POST /v1/responses` returned 200, then
`GET /v1/usage/consumption?request_id=…` returned 200. The actual read reported
one request/run, tokens 11/7/18, exact billed USD `0.0012300`, and complete
coverage. PostgreSQL contained the matching successful `responses.create` row
and a successful `usage.read` audit row. The shared correlation/request UUID
binds producer, read filter, and SQL rows.

Sanitized evidence (real responses/results, not fabricated fixtures):

- [`/openapi.json` HTTP projection](issue-333-contract-openapi-http.json):
  actual application OpenAPI response, status and 2.5.0 extension, route,
  operation ID, selector constraints, security and response codes.
- [Producer HTTP response](issue-333-contract-producer-http.json),
  [usage-read HTTP response](issue-333-contract-usage-read-http.json), and
  [persisted SQL result](issue-333-contract-persisted-sql.json).
- [Rendered proof](issue-333-contract-usage-read.png): native Chromium JSON
  viewer screenshot of the actual HTTP usage response; opened and visually
  inspected. The capture run is the controlled integration proof; the image is
  rendered proof, not a live-provider claim.

Chromium displayed the local capture, but its background GCM registration
attempt emitted a `DEPRECATED_ENDPOINT` diagnostic despite disabling ordinary
background networking; no credentials or provider endpoint were used. The
capture data contains no authorization headers, secrets, personal data, prompts,
or uncontrolled provider output. The helper checks both the exact Compose project
and exact disposable database URL before using the existing destructive fixture.

## Acceptance criteria mapping

| Criterion | Evidence / result |
| --- | --- |
| CA1 — Cross-incident attribution is resolved before aggregation | U333-6 cross-incident response scenarios; invariant report; current persisted single-request controlled read. |
| CA2 — Bound evidence and preserve request/month deduplication | U333-6 1,000/1,001-row boundary and UTC/month scenarios; current published `x-maximum-evidence-rows: 1000` and selectors. |
| CA3 — Counts, coverage, and status are arithmetically consistent | U333-7 semantic positive/negative conformance fixtures and `issue-333-contract-invariants.md`; final generated conformance validation. |
| CA4 — Cost amount, currency, precision, and price version remain coherent | U333-7 semantic fixtures; actual read and persisted producer evidence show billed USD `0.0012300`, exact precision, and price-version metadata. |
| CA5 — Deny/error/timeout uncertainty preserves the #130 semantics | Existing usage acceptance covers denied/error/timeout and unavailable consumption without invented totals; the new release preserves the prior consumption contract and all previous positive fixtures. Selector/OpenAPI parity is additional contract proof, not a substitute for CA5. |
| CA6 — Admin authorization and audit-before-response behavior remain explicit | Published `usage.read` governance/audit operation and 401/403/503 responses; U333-9 authorization, bearer challenge, audit ordering and failure-suppression tests. |
| CA7 — Read is grounded in persisted producer data and migration-ready runtime | Controlled POST → PostgreSQL → GET integration plus matching `responses.create` and `usage.read` SQL rows; U333-9 migration/seed/readiness regressions. |

## Eight-thread review disposition

This records the parent's inspected historical inventory; no remote thread was
resolved here. The audit-before-release thread was outdated, not automatically
resolved. Revalidate current thread metadata before publication; local
disposition does not imply remote reviewer acceptance.

| Thread | Finding / CA | Current disposition and next dependency |
| --- | --- | --- |
| [#383 / 4111980005](https://github.com/creep1ng/sre-agent/pull/383#discussion_r4111980005) | Cost metadata / CA4 | Locally covered by U333-7 and current actual persisted read; remote thread unresolved, human review remains. |
| [#383 / 4111980011](https://github.com/creep1ng/sre-agent/pull/383#discussion_r4111980011) | Coverage/count invariant / CA3 | Locally covered by U333-7 semantic checks and final release validation; remote unresolved. |
| [#384 / 4112401286](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112401286) | Audit-before-release / CA6 | Outdated thread; U333-9 retested commit-before-response and audit failure outcomes. Remote resolution still needed. |
| [#384 / 4112422103](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112422103) | Published contract activation / CA5–6 | U333-8 now locally activates 2.5.0 with live route parity; candidate hosted CI and human review pending. |
| [#384 / 4112620099](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112620099) | Migration head / CA7 | U333-9 retested migration/seed/readiness; remote unresolved. |
| [#384 / 4112620102](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112620102) | Authorization denial cause / CA6 | U333-9 retested persisted denial cause; remote unresolved. |
| [#384 / 4112620103](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112620103) | Bearer challenge / CA6 | U333-9 retested 401 challenge; remote unresolved. |
| [#384 / 4112799605](https://github.com/creep1ng/sre-agent/pull/384#discussion_r4112799605) | Cross-incident duplicate selection / CA1–3 | U333-6 reproduced/fixed and verified with bounded evidence scenarios; remote unresolved pending independent/human review. |

## Parent CI evidence, explicitly separate

The parent reports PR #428's original exact-head hosted CI run
[36669102065](https://github.com/creep1ng/sre-agent/actions/runs/36669102065)
passed all eight jobs and governance run
[36669572776](https://github.com/creep1ng/sre-agent/actions/runs/36669572776)
passed. These validate PR #428's original base, **not this uncommitted 2.5.0
candidate**. Earlier PR #421 CI [36657302250](https://github.com/creep1ng/sre-agent/actions/runs/36657302250)
and governance [36659223751](https://github.com/creep1ng/sre-agent/actions/runs/36659223751)
likewise belong to prior evidence. Current-candidate hosted CI, independent
verification, and human acceptance remain pending parent coordination.

## Source identity and rollback

SHA-256 identities below were checked before and after capture/report authoring;
source implementation and release contract did not change during U333-10.

| File | SHA-256 |
| --- | --- |
| `src/sre_agent/release.py` | `d49f29fb60f9b49a8b9316876218b3efdf621fd97c1fbd72a55fbcfeb418e127` |
| `src/sre_agent/gateway/usage.py` | `50398d281787490eb8f5c4184d749307d3bac695542dab48980cfc90660234be` |
| `schemas/releases/2.5.0/manifest.yaml` | `a4a73ecebe1f8928430ae80486aec66d9e6c2a483552e4a7f28cb392461a0830` |
| `schemas/releases/2.5.0/openapi/control-plane.yaml` | `d14ffa683a63abc6a6fd8947a12a3fb5a473ffd7e2555ca7ba9085eb0dfb8c1c` |
| `schemas/releases/2.5.0/json-schema/http/usage-read.schema.json` | `00fec6b57cb767189b4babd702df0f23e84733eca96f1eba5ca2acf8a3ff3e3f` |
| `tests/test_usage_read_openapi.py` | `f485852510a45cff7d92aaa7f31a45a5888472982655d7c4e6af2ad31fa869a3` |
| `schemas/tooling/test/usage-release.test.mjs` | `00aec3aa2edfe6bd5295bdcf9ab5525202b5bfe0f5c05c184965212b3121b983` |

Rollback is additive: remove only the new 2.5.0 snapshot, its activation/test
changes, and associated evidence if publication is rejected; retain every prior
release including 2.4.0. No migrations or runtime behavior rollback is implied.

Final staging caught one trailing blank line in the new release test that
untracked-only `git diff --check` had missed. The parent normalized that line
and reran the affected release test successfully; source behavior is unchanged.
