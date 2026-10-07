# Issue #333: 2.5.0 usage contract publication evidence

## Status and scope

Earlier sections retain their historical checkpoints. The final reopened
corrections section describes the current runtime input-validation change and
current source hashes; earlier “runtime unchanged” statements refer only to the
preceding schema-only repairs. The PR body binds the final frozen SHA and CI.

U333-8 is complete locally, including the verified PR #429 audit-contract
correction: the existing release generator published immutable, self-contained
`2.5.0` with the runtime usage-read contract; `2.4.0` is unchanged.
The original publication evidence bound the candidate to PR #428 head
`8965cb1978f9363a807279b6ec1b60c76d739e42`. A follow-up on PR #429 base/HEAD
`47673b9b4e9306c3c40aec638874b5505d002de6` corrected a published OpenAPI
parity defect, then parent commit `1445ad9f82698842ec2e2a4071a6f9790c7ac609`
was pushed with all eight hosted CI jobs passing ([run 36682652995](https://github.com/creep1ng/sre-agent/actions/runs/36682652995)); its governance check
also passed ([run 36682650924](https://github.com/creep1ng/sre-agent/actions/runs/36682650924)).
Those results are historical for `1445ad9`, not for the current uncommitted
audit correction. U333-10 remains pending parent verification, hosted CI on the
final candidate, and human review.
No commit, push, PR/GitHub mutation, release tag or deployment was done here.

Current release inventory: 199 files; generator reports 204 artifacts and 17 checks.
All 194 published files in 2.4.0 retain their prior hashes; the focused diff
against that release is empty. Existing all-release validation covers 11 releases
(1.0.0–2.5.0). The publication-only size exception was authorized at an
estimated 6,500–7,500 changed lines. At the initial publication checkpoint the candidate diff from PR #428 was
8,702 additions + 33 deletions. After authorized reopened corrections, the final
count against exact base `8965cb1978f9363a807279b6ec1b60c76d739e42` is
9,091 text additions + 35 deletions (9,126 changed text lines), plus the binary
PNG; this is above the estimate and is reported transparently, not code-golfed
or claimed as a new exception. Parent owns final scope/size disposition.

## PR #429 finding 4141505117: selector nullability parity

Verified finding: `schemas/releases/2.5.0/openapi/usage-read.yaml` had nonnullable
schemas for optional `request_id`, `incident_id`, and `month`, while the proposal,
published control-plane OpenAPI, and FastAPI runtime emitted nullable `anyOf`
schemas. Added a permanent assertion over all four real artifacts. Its strict
Docker RED on base `47673b9` failed first at standalone `request_id`'s missing
`type: 'null'`; after repair all three selectors retain their UUID, min/max, and
month-pattern constraints while explicitly allowing null. No runtime model or
HTTP behavior changed, so the existing actual runtime HTTP capture above remains
current; no browser was relaunched.

```sh
docker compose --project-directory "$PWD" --project-name candidate-wt-9bb3531fa9f1 --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_usage_read_openapi.py::test_every_published_usage_openapi_selector_preserves_optional_null_semantics tests/test_usage_read_openapi.py::test_active_runtime_publishes_the_versioned_usage_contract'
```

Observed GREEN: **2 passed**; final configured Python run: **1,251 passed,
1 skipped** (96.34s), with all configured lint/format, lock, import-boundary,
typing, pytest, and Alembic checks passing. The same full runner was initially
launched twice with overlapping access to the one disposable test database; that
overlapping run reported nine unrelated auth/control failures alongside missing
database objects and audit rows. After both runs stopped, one sequential full
rerun passed as above; no product-code change was made for those failures. Tooling remains
**124 passed / 0 failed**; all 11 releases validate and OpenAPI lint passes.
Existing `2.5.0` immutable generator data were backed up outside the candidate,
then only `2.5.0` evidence and manifest were regenerated with the existing
`node schemas/tooling/release.mjs evidence --release 2.5.0` harness workflow.
The resulting manifest/evidence changes are limited to the standalone OpenAPI
and evidence hashes; every older release, including 2.4.0, remains unchanged.
The release artifact, refreshed generated metadata, and permanent test comprise
84 additions/deletions; with this evidence-report and tracker update, the current
candidate diff is 150 additions/deletions. This is separate from the original
publication-only size exception and does not request or imply a new exception.

## PR #429 finding 4141907709: operation-scoped audit context matrix

Before adding tests, failure modes were enumerated from the actual publisher and
existing PostgreSQL/FastAPI acceptance boundary (`tests/test_usage_read_acceptance.py`):

| Persisted usage.read outcome | Expected action and context |
| --- | --- |
| `authorization/success/200` | `admin.read`; authenticated identity, administrative-control resource, allow decision; no denial cause. |
| `authentication/error/401` | `admin.read`; no identity, resource, decision, or denial cause. |
| `authorization/denied/403` | `admin.read`; authenticated identity/resource, deny decision, one of four reachable causes; principal state must match the cause. |
| `validation/error/422` | `admin.read`; selector validation precedes auth context, so no identity/resource/decision. |
| `validation/error/413` | `admin.read`; bounded projection occurs after auth, so include authenticated identity/resource and allow decision. |
| `audit/error/503` storage failure | `admin.read`; authorized storage failure is auditable, include authenticated identity/resource and allow decision; reason `upstream_unavailable`, retryable. |
| audit append unavailable response `503` | No persisted `usage.read` event exists; do not invent one or add unauthenticated principal/context. Existing acceptance asserts audit store failure suppresses response and persists no row. |

Negative tests reject operation changes to `invoke` (including 401), invented
unauthenticated 401 identity context, missing authenticated deny context,
context leaked into pre-auth 422, missing post-auth 413/503 context, and the
non-persisted `audit_unavailable` 503. The schema constrains usage.read to
`admin.read` operation-wide and exact stage/outcome/status/reason/retryability
combinations; generic validation/audit stage rules and unrelated operations
remain in force. Existing `responses.create` audit fixtures remain valid.

### Independent verifier finding: reachable denial causes

The independent verifier exercised three additional legitimate persisted
usage-read 403 events against the owned database. Each had one row with action
`admin.read`, stage `authorization`, outcome `denied`, top-level reason
`no_matching_grant`, policy decision `deny`, and an `administrative_control`
resource:

| Cause | Principal state |
| --- | --- |
| `principal_inactive` | `inactive` |
| `resource_inactive` | `active` |
| `resource_missing` | `active` |
| `grant_not_applicable` | `active` |

The old schema accepted only `grant_not_applicable`. Before changing the schema,
three new positive 403 cases and two mismatch negatives were added permanently;
the Docker RED log showed positive fixture cases 7–9 rejected. The correction
accepts all four complete contexts while rejecting mismatches, such as
`principal_inactive` with an active identity or a resource/grant cause with an
inactive identity. A separate extra DB probe first failed because shell quoting
stripped a value; as reported by the independent verifier (not observed from
its raw log here), its successful parameterized-SQL rerun established the
three additional causes. The successful runtime output is preserved at
`/tmp/sre-issue333-residual-gv176v/audit-contract-independent/logs/runtime-403-reachability.log`.

### Observed RED / GREEN for finding 4141907709

Before schema edits, the permanent test and nine-event positive fixture were run
in the owned Docker harness. The original matrix RED rejected persisted `403`,
`413`, and storage `503` events while admitting `401` with action `invoke` and
an invented principal. The independent-cause RED additionally rejected all
three valid new 403 contexts: Docker failures identify positive fixture cases
7–9 (`principal_inactive`, `resource_inactive`, `resource_missing`). After the
2.5.0 schema repair, all nine positive events (six status classes, four 403
causes) validate, and all nine negative mutations reject, including the two
cause/principal-state mismatches. The append-unavailable response
remains a distinct no-row outcome, verified by existing Python acceptance
rather than fabricated as an event. Non-usage `responses.create` still
validates. Two intermediate schema-only runs caught and fixed authoring issues:
first the project closed-object checker rejected a partial nested identity
matcher, then strict AJV required its `type: object`. Adding the authenticated
identity reference plus `unevaluatedProperties: false` and explicit object type
fixed those checks; no runtime code changed.

Focused commands and observed GREEN:

```sh
docker compose --project-directory "$PWD" --project-name candidate-wt-9bb3531fa9f1 --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm harness node --test schemas/tooling/test/usage-release.test.mjs
docker compose --project-directory "$PWD" --project-name candidate-wt-9bb3531fa9f1 --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_usage_read_acceptance.py tests/test_audit_events_contract.py tests/test_usage_read_contract.py'
docker compose --project-directory "$PWD" --project-name candidate-wt-9bb3531fa9f1 --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm harness sh -c 'npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate:releases && npm --prefix schemas/tooling run lint:openapi'
```

Observed after the denial-cause update: focused schema **2 passed**, Python
acceptance **74 passed** (10.86s), full tooling **125 passed / 0 failed / 0
skipped** (390.35s), all 11 releases validate, and OpenAPI lint/bundle checks
pass. `git diff --check` passes. No runtime implementation changed.

The audit schema changes alter the resolved `AuditEventMetadata` schema used by
`/v1/audit-events`, so the 2.5.0 normalized FastAPI projection hashes changed.
The first evidence generation failed closed on the stale projection (`f4ce…`
expected vs `7fe9…` generated). In disposable harness tmpfs only, the existing
`projection --release 2.5.0` command regenerated the new release's
match/missing/extra goldens; existing `evidence --release 2.5.0` then generated
203 artifacts / 17 checks. Only these 2.5.0 outputs were copied back. No older
release file was edited or regenerated.

Final correction artifact hashes:

| File | SHA-256 |
| --- | --- |
| `schemas/releases/2.5.0/json-schema/domain/audit-event.schema.json` | `3a72d3ac325575c0856bb02c94584844ff591d4ecbae3c450571379efddbda77` |
| `schemas/releases/2.5.0/fixtures/positive/audit.usage-read.runtime-outcomes.positive.v2.5.0.fixture.json` | `c10601d2800b57fd2e4b4c3ba25fca4e26e3d89cc28971dc2dc2a0b0f2315f5b` |
| `schemas/releases/2.5.0/fixtures/positive/future-fastapi.match.projection.json` | `00f3e291aa616bc06b56345c1a82f6353a0a574c7209fadef1133dcca0f90767` |
| `schemas/releases/2.5.0/manifest.yaml` | `db268e21c979421069776f2fa65ce4330dcee509b6203d72c2744123b05cc654` |
| `schemas/releases/2.5.0/conformance/evidence.json` | `9de74449f31381064862315cfdb136f4b3e8e9d41fd37951bccad95d3a51aba4` |
| `schemas/tooling/test/usage-release.test.mjs` | `aac812f04a70b10e08fcc2ca15778a83285be8680b0df4a2c838fc1faaa643d0` |
| `src/sre_agent/gateway/usage.py` (unchanged) | `50398d281787490eb8f5c4184d749307d3bac695542dab48980cfc90660234be` |

The new nine-event fixture is a faithful contract projection of the event
shapes emitted by the existing usage-read publisher: values are derived from
its event-building branches and cross-checked against the existing
FastAPI/PostgreSQL acceptance tests plus the independent parameterized denial
probe. It is not a raw capture or a claim that one HTTP transaction emitted all
nine events. Those actual runtime
boundaries are independently exercised by the 74-test controlled acceptance
run; append-unavailable is explicitly asserted to leave no audit row. Detailed
stdout logs from this correction are preserved outside the candidate at
`/tmp/sre-issue333-residual-gv176v/audit-contract-correction-evidence/`:
`audit-matrix-red.log`, `denial-causes-red.log`,
`denial-causes-schema-green.log`, `denial-causes-focused-green.log`,
`denial-causes-python-acceptance.log`, and
`denial-causes-tooling-all-releases-lint.log`. The independent runtime outcome
logs are under `/tmp/sre-issue333-residual-gv176v/audit-contract-independent/logs/`.

Tracked paths under every prior release directory from 1.0.0 through 2.4.0
have an empty Git byte/mode diff against the exact local base `1445ad9`; no
older release file was touched. In particular, the prior 194-file 2.4.0
snapshot retains its original hash set.

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

The parent reports PR #429 head `1445ad9f82698842ec2e2a4071a6f9790c7ac609`'s
hosted CI run
[36682652995](https://github.com/creep1ng/sre-agent/actions/runs/36682652995)
passed all eight jobs and governance run
[36682650924](https://github.com/creep1ng/sre-agent/actions/runs/36682650924)
passed. These are historical results for the current committed parent, **not
for this uncommitted audit-contract correction**. The parent also reports PR
#428's exact-head hosted CI run
[36669102065](https://github.com/creep1ng/sre-agent/actions/runs/36669102065)
passed all eight jobs and governance run
[36669572776](https://github.com/creep1ng/sre-agent/actions/runs/36669572776)
passed. These validate PR #428's original base, **not this uncommitted 2.5.0
candidate**. Earlier PR #421 CI [36657302250](https://github.com/creep1ng/sre-agent/actions/runs/36657302250)
and governance [36659223751](https://github.com/creep1ng/sre-agent/actions/runs/36659223751)
likewise belong to prior evidence. Current-candidate hosted CI, independent
verification, and human acceptance remain pending parent coordination.

## Source identity and rollback

Runtime implementation hashes below are unchanged from the verified capture;
the domain audit schema and generated metadata were changed afterward only for
the audit-contract correction. All hashes below identify the final local
candidate after regeneration.

| File | SHA-256 |
| --- | --- |
| `src/sre_agent/release.py` | `d49f29fb60f9b49a8b9316876218b3efdf621fd97c1fbd72a55fbcfeb418e127` |
| `src/sre_agent/gateway/usage.py` | `50398d281787490eb8f5c4184d749307d3bac695542dab48980cfc90660234be` |
| `schemas/releases/2.5.0/openapi/usage-read.yaml` | `022069365e0604912a6f3e389382e0a3653ef6ef80a6869bdf38a1def736c6de` |
| `schemas/releases/2.5.0/manifest.yaml` | `db268e21c979421069776f2fa65ce4330dcee509b6203d72c2744123b05cc654` |
| `schemas/releases/2.5.0/conformance/evidence.json` | `9de74449f31381064862315cfdb136f4b3e8e9d41fd37951bccad95d3a51aba4` |
| `schemas/releases/2.5.0/openapi/control-plane.yaml` | `d14ffa683a63abc6a6fd8947a12a3fb5a473ffd7e2555ca7ba9085eb0dfb8c1c` |
| `schemas/releases/2.5.0/json-schema/http/usage-read.schema.json` | `00fec6b57cb767189b4babd702df0f23e84733eca96f1eba5ca2acf8a3ff3e3f` |
| `schemas/releases/2.5.0/json-schema/domain/audit-event.schema.json` | `3a72d3ac325575c0856bb02c94584844ff591d4ecbae3c450571379efddbda77` |
| `schemas/releases/2.5.0/fixtures/positive/audit.usage-read.runtime-outcomes.positive.v2.5.0.fixture.json` | `c10601d2800b57fd2e4b4c3ba25fca4e26e3d89cc28971dc2dc2a0b0f2315f5b` |
| `schemas/releases/2.5.0/fixtures/positive/future-fastapi.match.projection.json` | `00f3e291aa616bc06b56345c1a82f6353a0a574c7209fadef1133dcca0f90767` |
| `tests/test_usage_read_openapi.py` | `ebcab7e5d5fcce6c9974c163348921306a272ce11f6f81c1a6c6c6c27e171b81` |
| `schemas/tooling/test/usage-release.test.mjs` | `aac812f04a70b10e08fcc2ca15778a83285be8680b0df4a2c838fc1faaa643d0` |

Rollback is additive: remove only the new 2.5.0 snapshot, its activation/test
changes, and associated evidence if publication is rejected; retain every prior
release including 2.4.0. No migrations or runtime behavior rollback is implied.

Final staging caught one trailing blank line in the new release test that
untracked-only `git diff --check` had missed. The parent normalized that line
and reran the affected release test successfully; source behavior is unchanged.

## Final independent audit correction verification

The independent verifier reran the final schema conformance (2 passed), targeted
Python setup and audit-append failure (2 passed), all 11 release validations,
and both canonical OpenAPI lint checks. Three real HTTP403 requests and SQL
readbacks reproduced the additional denial causes.
[Sanitized actual denial-context output](issue-333-audit-denial-contexts.json)
is included separately from the faithful-projection conformance fixture.
The earlier attempt to delete audit rows was rejected by the append-only trigger;
the successful probe did not delete audit events or bypass the trigger.
All 1,579 pre-2.5 release files retained their bytes/modes; the verifier's
2,375-file candidate inventory and Git status were unchanged. No runtime source
changed, so the existing real HTTP/SQL screenshot remains applicable; no new
browser or provider was used. Final frozen SHA and hosted CI are bound by the
PR body after commit; human acceptance remains pending.

The parent published and executed the [guarded repeat helper](issue-333-audit-denial-probe.py):
one fixture setup test passed, then all three actual HTTP403/SQL contexts matched
the independent output. The helper rejects a missing project guard before DB
mutation and verifies exact owned database URL/identity; it removes only the
seeded usage grant/resource for the final case and never deletes audit rows.
Run it only in the disposable checks database, after the setup test, using the
exact Docker replay command in the sanitized JSON. Initial Ruff cache permission
errors under the unprivileged capture UID were resolved with `--no-cache`; lint
and format then passed without changing runtime source.

## Authorized reopened corrections — 2026-09-30 (findings 4142861478 / 4142861488)

The parent-authorized candidate starts at `6ed5335ab91f0056ccb4f93bb6f961ac0e25728a`; no source commit was made here. The frozen 6ed CI/governance results recorded above are historical and do not validate this uncommitted candidate. User explicitly selected early rejection for unsupported months. No terminal-month calendar implementation, billing change, provider access, or browser capture was added.

### 4142861478 — reject unsupported query months before authorization

TDD first: the permanent acceptance/OpenAPI tests were written and run against the old runtime before production changes. RED: **3 failed / 3 passed**; `0000-01` and `9999-12` reached authorization and produced the guarded 503, and the generated selector constraints did not match. The portable `SUPPORTED_MONTH_PATTERN` now accepts `0001-01` through `9999-11` (including ordinary valid months) and rejects zero-year or `9999-12`. It is applied to the query, typed request filter, proposal and 2.5.0 inputs. The explicit runtime check runs before authorization: for this optional-month query path, the Query pattern appeared in OpenAPI but did not reject these tested values at runtime. The output month-list schema/model is unchanged. GREEN focused tests: **6 passed**; valid boundaries `0001-01` and `9999-11`, plus `2026-09`, still succeed. A controlled test-database HTTP capture shows an actual 422 and persisted context-free validation event at `docs/evidence/issue-333-input-month-422.json`; this is separate from the successful-flow screenshot and producer/read/SQL bundle. Its repeatable acceptance test is `tests/test_usage_read_acceptance.py::test_unrepresentable_month_is_rejected_before_authorization` (exact test name retained in source); no live service/provider is involved.

### 4142861488 — pre-authorization storage-failure audit envelope

The permanent schema/conformance test was first run against the stale 2.5.0 contract. RED: the actual complete context-free `usage.read/admin.read` audit error for an injected pre-context storage failure was rejected. The 2.5.0 schema now permits the distinct complete context-free `audit/error/upstream_unavailable/503/retryable` envelope, while keeping operation-wide `admin.read`, forbidding invented authorization denial cause, and separately requiring full identity/resource/policy context for the authenticated storage-failure variant. Negative cases reject partial context, wrong action, and a fabricated persisted `audit_unavailable` event. No runtime behavior or principal was invented. Focused schema GREEN: **1 passed**. Controlled actual FastAPI/PostgreSQL acceptance plus existing append-failure cases: **5 passed**. The sanitized HTTP/SQL observation is `docs/evidence/issue-333-preauth-storage-503.json`; it shows the independently persisted context-free usage.read row. PostgreSQL JSONB encodes Python `None` as JSON `null`; readback compares against `'null'::jsonb`, not SQL NULL. The append-failure path still produces no audit row and is covered by its existing acceptance case. The separately labeled positive fixture is a faithful contract projection, not a raw capture.

### Runtime OpenAPI and evidence freshness

Because the runtime month selector changed, `docs/evidence/issue-333-contract-openapi-http.json` was refreshed from the actual current `GET /openapi.json` using the existing guarded capture process; it advertises 2.5.0, the canonical route, and the supported pattern. This is a controlled local application capture, not a hosted or live-provider result. The existing actual successful producer/read/SQL bundle and its real Chromium screenshot are retained as the previously captured normal valid-month flow: the successful flow was not changed, but the prior screenshot is not evidence for the new 422/503 errors. The new JSON/SQL 422 and 503 observations above are the actual error-path evidence; no new screenshot was produced.

Only proposed 2.5.0 projections, evidence, and manifest were regenerated with the existing release CLI after backing up the proposed manifest/evidence outside the candidate. The generator produced three future-FastAPI projection fixtures; the evidence reports 204 artifacts / 17 checks. No 1.0.0–2.4.0 release was regenerated or edited. A byte-and-mode comparison of the exact older-release inventory recorded before regeneration found **zero drift across 1,579 files**; `git diff --quiet 6ed5335 -- schemas/releases/1.0.0 ... schemas/releases/2.4.0` also returned zero.

### Final local checks and remaining delivery boundary

After all artifact normalization, the exact owned Docker compose project ran the full configured Python check command (`docker compose ... --profile checks run --build --rm python-checks`) sequentially: Ruff lint passed; all **165 Python files** formatted; five import-boundary contracts kept; typing succeeded for 12 source files; **1,257 passed, 1 skipped** in 101.81s; no new Alembic upgrade operations. The one skip is `tests/test_openrouter_live.py::test_openrouter_gateway_live_smoke`, intentionally disabled unless `RUN_OPENROUTER_LIVE_SMOKE=1` because it makes a live provider request. No live provider request was made. The complete tooling run after the schema/projection normalization was **125 passed / 0 failed / 0 skipped**; all **11 releases (1.0.0–2.5.0)** validate and OpenAPI lint/bundle checks pass. The focused Python acceptance/OpenAPI suite was **82 passed**; the focused usage-release Node suite was **2 passed**. `git diff --check` and manual untracked-file whitespace checks are recorded at terminal handoff.

The complete candidate remains uncommitted at base `6ed5335ab91f0056ccb4f93bb6f961ac0e25728a`; current local results do not supersede the hosted CI run on that prior frozen SHA. Against exact base `8965cb1978f9363a807279b6ec1b60c76d739e42`, final candidate diff is 9,091 text additions + 35 deletions (9,126 text lines), plus the existing binary PNG. The original 6,500–7,500 changed-line estimate was advisory, not a ceiling; actual size is reported without code-golf or a claim of a new exception. U333-10, current-candidate hosted CI, PR reconciliation, and human review remain pending parent verification; no acceptance/deployment is claimed.

Current key SHA-256 values after final normalization:

| Artifact | SHA-256 |
| --- | --- |
| `src/sre_agent/gateway/usage.py` | `107c2f09f76cb673f2733c96e162ee7529b151bfd846411b6c90a99d4a16b2b7` |
| `docs/evidence/issue-333-contract-openapi-http.json` | `cf52d10279655b07acfe6bba8069b237cbeedb751c50910e94bb1fb6667222da` |
| `docs/evidence/issue-333-input-month-422.json` | `78155a93a823850a9a26031510cf1dcdce9abf3ac62722b6ee400b4c23cb61b4` |
| `docs/evidence/issue-333-preauth-storage-503.json` | `494330e023c6d231eaf44eb59342769849d06e356cff4c20503510dce7e02ab6` |
| `schemas/releases/2.5.0/json-schema/domain/audit-event.schema.json` | `121baa0eabc13c76ae52f04d701abfcf8bacfdba52343cc882cd8f1039f0dc75` |
| `schemas/releases/2.5.0/openapi/usage-read.yaml` | `4d05ed8c23ea48fea54af3758b3dfc534605b76169be360bdea4dd882541daa6` |
| `schemas/releases/2.5.0/manifest.yaml` | `9a6b566c2aa843f8d914d810297d9b0a4fb6d1c194e69f5a23f538874088a263` |
| `schemas/releases/2.5.0/conformance/evidence.json` | `e33807475e7426ac1c552206154b6da1f3b9a0a3cd31024cdd3d8c03ef044089` |

### Final independent and parent spot verification

Independent checks on these exact source/schema bytes passed: 82 Python
acceptance/OpenAPI cases, two focused Node conformance tests, all 11 release
validations, both canonical OpenAPI lint checks and whitespace checks. The
verifier compared 1,579 earlier-release paths and a 2,380-entry candidate
inventory: no content/mode or status drift. It confirmed the current inventory
of 199 files/204 artifacts/17 checks; stale report metadata was corrected only
after its terminal check. The parent rebuilt and ran both rejected-month cases
and the pre-authorization storage-failure case: three passed in 2.97s.
Raw original RED output was not independently reviewed by the final verifier;
the test-first sequence/counts above are the implementing writer's observed
report. No retrospective RED execution is claimed. New exact-head hosted CI
and independent human evidence acceptance remain delivery dependencies.
