# Issue #334 — CA1–CA8 end-to-end evidence

Covers the integrated chain on this commit: audited policy write, endpoint/incident
and monthly affordability, reservation persistence, atomic admission with output
cap, exact settlement, uncertain retention, legacy #333 usage reconciliation,
fail-closed pricing and concurrency. Real FastAPI routes and PostgreSQL; the
provider and catalog are deterministic doubles, no live upstream call.

## Reproduce

Host provides Git, Docker and a synthetic `.env` derived from `.env.example`
(no provider keys, `RUN_OPENROUTER_LIVE_SMOKE=0`).

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree \
  -f compose.yaml -f /tmp/issue334-ca-evidence-20260930/compose-network.override.yaml \
  --profile checks run --build --rm python-checks
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree \
  -f compose.yaml -f /tmp/issue334-ca-evidence-20260930/compose-network.override.yaml \
  --profile checks run --rm python-checks sh -c \
  'python scripts/assert_test_database_isolated.py && pytest -q tests/test_issue_334_acceptance.py'
```

The network override only pins a free `/28`; on another host drop it and let the
default Docker allocator choose.

## Criterion map

| CA | Test | Observed behavior |
|---|---|---|
| CA1 | `test_ca1_protected_versioned_write_governs_new_admissions_without_restart` | Versioned audited `PUT` applies to later admissions in the same process; cap equals the endpoint ceiling; restricted principal still gets 403 before the cap changes |
| CA2 | `test_ca2_incident_scope_is_shared_across_runs_and_gran_is_mandatory` | In-flight reservation on one incident denies a different run of the same incident while an unrelated incident still admits; grant still enforced |
| CA3 | `test_ca3_monthly_budget_covers_calls_without_incident_and_keeps_period` | Calls without `incident_id` consume the monthly budget; reservation keeps the UTC admission month |
| CA4 | `test_ca4_concurrent_admissions_cannot_oversubscribe_one_incident` | Two concurrent admissions produce exactly one 200 and one 429, with a single provider call and one reservation |
| CA5 | `test_ca5_denial_precedes_provider_and_records_metadata_only` | 429 with zero provider requests, no reservation, and no prompt or output text in the stored audit event |
| CA6 | `test_ca6_exact_settlement_is_exact_and_uncertain_usage_stays_reserved` | Complete+exact usage settles tokens and exact USD; a timeout with unknown usage keeps the reservation in the admission period |
| CA7 | `test_ca7_active_limits_fail_closed_without_trustworthy_price_or_bounds` | Unknown request price and expired freshness both fail closed before provider contact |
| CA8 | `test_ca8_equality_zero_unset_and_hot_policy_change` | Exact threshold admits at the full endpoint cap; zero denies as an active limit; unset disables only that dimension after a hot policy write |

## Limits

Containerized local verification only. No hosted CI, no human approval, no live
provider or catalog request. Synthetic credentials and deterministic doubles.
Sanitized: yes.

For the current closure gaps, confirmed in-flight semantics and additional #467/#468 regressions, see [issue-334-closure.md](issue-334-closure.md). The original matrix below is historical evidence, not a claim that rollover or public audit HTTP readback was demonstrated.
