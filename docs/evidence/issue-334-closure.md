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

Pending execution and exact tested SHA. RED on unmodified base: CA5 failed because persisted policy_ref was null; preliminary monthly scenario passed. Fresh final results, environment, screenshot and candidate identity will be recorded after checks.

## Acceptance and rollback

Recommend review of this bounded gap fix, **not automatic closure**. Human evidence acceptance, public audit readback (#25) and full published event conformance remain pending; unlinked historical rows retain #468's explicit limitation and must not be guessed away. A future contract publication is separate work, not an implicit destructive migration.

Revert this patch to remove new policy provenance; it does not revert #467/#468 or alter existing rows. Already-written opaque references remain valid under the published optional field.
Sanitized: yes.
