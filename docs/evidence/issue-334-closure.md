# Issue 334 closure: policy provenance and UTC rollover

Route: delegated direct. Base: `4a4515b99b6f5931f43969f7147c6ec90519344f` (#468).
Evidence kind: controlled integration; real FastAPI HTTP and PostgreSQL, deterministic provider/catalog doubles, no external LLM or production credential.

## Confirmed semantics and audit contract

Already-admitted requests keep their effective policy version, output limit and UTC admission month through settlement; updates govern new admissions only (explicit user confirmation). Settlement updates the original reservation, never moves it to the completion month or current policy. Unknown outcomes retain exposure.

CA5 uses the existing optional `policy_decision.policy_ref` (ADR-005), not a new raw field: HMAC-SHA-256 of UTF-8 `sre-audit-v1\0policy\0consumption-limits:1:version:{N}` with the audit key. `N` is the version actually read during admission. The reference is opaque, not reversible or a human-readable version number; authorized consumers verify it against a known version and key. `grant_ref` still identifies authorization; `redaction.policy_version` is unrelated. Unresolved policies must not fabricate version-zero evidence.

The regression independently calculates the reference, sends HTTP success and limit rejection, checks actual SQL rows and recovers both via `AuditRepository.query_filtered`. It validates the published `allowDecision` shape. No payload or secret is included. No migration or published-schema edit is needed.

Public audit HTTP reads are specified but not implemented in this main; implementation is tracked by open #25. Repository recovery is **not** HTTP public-read evidence. The existing runtime's consumption-specific audit operations/reasons are absent from the published 2.5.0 enum; this pre-existing contract-publication gap is not disguised by validating only the applicable policy-reference shape. Full event conformance and public HTTP readback remain pending.

## Reproduce

Host: Git and Docker. Use versioned `.env.example` with local non-production inputs; do not print or attach credentials. The unique project below creates its own tmpfs PostgreSQL, never uses an existing workspace database. Dependencies come from `uv.lock` and repository digest-pinned Dockerfiles/PostgreSQL.

```sh
docker compose --project-name issue334-closure --env-file .env.example --profile checks run --build --rm python-checks
docker compose --project-name issue334-closure --env-file .env.example --profile checks run --rm python-checks pytest -q -s tests/test_issue_334_acceptance.py
docker compose --project-name issue334-closure --env-file .env.example --profile checks run --build --rm harness sh -c 'npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate && npm --prefix schemas/tooling run validate:releases && npm --prefix schemas/tooling run lint:openapi && npm --prefix schemas/tooling run conformance -- --consumer issue-10'
```

Safe cleanup: stop only this project's checks services; do not remove global volumes or other worktrees. Test fixtures recreate only the explicitly isolated test database; historical application rows are never reconciled or changed.

## Criterion map

| CA | Implementation | Test / evidence |
|---|---|---|
| CA1 | Protected versioned/idempotent policy PUT | `test_ca1_protected_versioned_write_governs_new_admissions_without_restart`; policy-write checks in full suite |
| CA2 | Incident admission lock and durable reservations, independent grants | `test_ca2_incident_scope_is_shared_across_runs_and_gran_is_mandatory` |
| CA3 | UTC admission period, workspace sum, linked audit fallback | `test_ca3_monthly_budget_covers_calls_without_incident_and_keeps_period`, new `test_ca8_utc_rollover_and_hot_policy_update_keep_inflight_admission`, CA10 |
| CA4 | Per-period/per-incident atomic admission and reservation | `test_ca4_concurrent_admissions_cannot_oversubscribe_one_incident` |
| CA5 | Responses carries effective version to audit policy ref | New `test_ca5_http_events_preserve_effective_consumption_policy_reference`, existing metadata-only denial test; HTTP 200/429, SQL + repository readback |
| CA6 | Original reservation settles exact usage; unknown retains exposure; correlated monetary rows deduplicate audit | Exact-settlement test plus all six #468 regression cases (incident/no-incident, settlement failure, audit failure, unpriced fallback); new crossing response stays in admission period |
| CA7 | Active limits without trustworthy bounds/catalog fail closed | `test_ca7_active_limits_fail_closed_without_trustworthy_price_or_bounds`; CA9 preserves #467 |
| CA8 | Equality/zero/unset/idempotency/concurrency plus controlled month edge and in-flight update | Existing `test_ca8_equality_zero_unset_and_hot_policy_change`; new rollover test controls both admission and audit clocks with events, no prolonged sleep |

CA9/CA10 are supplementary tests, not new issue criteria. Pure calculator/unit tests complement but do not substitute the real HTTP/PostgreSQL scenarios. Session/run and idempotency tests are included in full-suite verification.

## Verification record

Tested source SHA: `6e2d95b3eb2c6d09c683c9bd4b1552a00f4271ee`. Final evidence-only changes do not alter source, tests, schemas or dependencies; human freshness confirmation remains required.
Environment: Docker 29.8.1 / Compose 5.5.1, Python 3.12.14, pytest 8.3.5, PostgreSQL 17.4, Chromium 153.0.8010.12. Checks image `sha256:ad6c808c86284c454072cf1d12981bd337cc63f133bb35d09b1cea218dd30c41` was built from base with locked dependencies; local checks mount exact candidate source/tests read-only. Owner UID and `--no-cache` were used only for formatting. `uv.lock` SHA-256: `783c78b44e4ab07091d0ee1d44a693b77f1ec0fdc94f9aa3c0e212cd34dc878b`.
RED: CA5 failed on persisted null policy_ref; both final CA8 variants reached null-policy-reference schema failure after period/cost assertions passed. An authoring cap mismatch and reused fixture period were corrected before source changes; an initial formatter-cache permission failure was corrected without changing permissions or dependencies.
GREEN: 19 acceptance cases passed in 122.24s. CA5 HTTP 200/429 preserves refs for versions 1/2 in SQL and repository recovery. UTC crossing: January exact settled USD 0.1 (or retained unknown USD 0.3), February settled USD 0.4; original version 1, new version 2; old/new output caps 1/2; final 429 before provider. A USD 0.2 remainder cannot fund the USD 0.3 minimum bounded request, so rejection is not a claim of zero monetary remainder. Four #468 coexistence variants each produced 200/200/429; other #467/#468 checks also passed.
Actual [stdout](issue-334-closure.txt) and [Chromium screenshot](issue-334-closure.png), captured 2026-10-03T21:58:23.407Z. PNG SHA-256: `2196e88ff23807a387071acb89ff4008ab198377137a41b2eb762daa74924be8`. The capture shows actual selected test stdout, not a product UI or live-provider claim.
Local full Python: 1480 passed, 1 skipped, 3 failed (unchanged Issue 29 relay readiness timeout); targeted rerun: 2 passed, 1 failed. No root cause or local clean pass is claimed. Lint, format, lock, import boundaries, mypy, separate Alembic and declarative incident/authorization/run/query/CI validators passed.
Hosted [CI on cf6aa1e](https://github.com/creep1ng/sre-agent/actions/runs/37157139078): 1483 passed, 1 skipped; contracts, configuration lock, static web, Compose smoke, production browser and quality gate passed. These are hosted results, not a cure for the local relay failures.
The duplicate local contract pipeline was interrupted after 125 passing tests (2451.70s) and successful validate (2 schemas / 2 fixtures), during validate:releases; release validation completion, OpenAPI lint and issue-10 conformance were not observed. Hosted contracts passed, but no local pipeline completion is claimed. Draft governance and human acceptance remain pending.

## Acceptance and rollback

Recommend review of this bounded gap fix, **not automatic closure**. Human evidence acceptance, public audit readback (#25) and full published event conformance remain pending; unlinked historical rows retain #468's explicit limitation and must not be guessed away. A future contract publication is separate work, not an implicit destructive migration.

Revert this patch to remove new policy provenance; it does not revert #467/#468 or alter existing rows. Already-written opaque references remain valid under the published optional field.
Sanitized: yes.
