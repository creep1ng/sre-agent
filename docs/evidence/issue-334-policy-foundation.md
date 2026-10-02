# Policy persistence foundation — issue #334

This prerequisite creates an unset singleton policy and admits metadata-only
`consumption_limits.get` audit records. It exposes no policy HTTP route or new
grant. CA1 remains partial; enforcement and CA2–CA8 are not implemented here.
Route: direct recovery. Chain: main → **foundation (this slice)** → audited GET
→ policy writes → provider catalog → admission/settlement.

## Reproduce

Prepare ignored `.env` from `.env.example` using synthetic local values, no
provider credential and live smoke disabled. Generate `.env.worktree` with
`scripts/bootstrap-worktree.py`; use its unique isolated tmpfs checks database.

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_migrations.py'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks exec -T python-checks-db psql -U python_checks -d python_checks -c 'SELECT policy_id, version, incident_token_limit, monthly_usd_limit FROM consumption_limit_policies;' -c "SELECT operation, content_state, count(*) FROM audit_events WHERE operation IN ('consumption_limits.get','usage.read','catalog.create','catalog.list','catalog.read') GROUP BY operation, content_state ORDER BY operation;"
```

Run the migration module immediately before the SQL demonstration to recreate
its controlled fixture. Expected and observed: one unset version0 policy; BIGINT
values and exact 12-place USD survive storage; invalid singleton/negative values
are rejected; the new and prior audit operations persist. Downgrade refuses
while new-operation evidence exists. Existing #130 exact-cost history survives.

## Evidence and compatibility

Evidence kind: **controlled integration**. The [screenshot](issue-334-policy-foundation.png)
is an unmodified Chromium rendering of actual PostgreSQL query output, not a
mock API. Tests first reproduced DTO and SQL rejection, then passed after the
additive vocabulary change. The full runner checks formatting, lint, lockfile,
imports, types, tests and Alembic drift. PR metadata supplies exact tested/base
SHAs, results and image identities; image digests and dependency locks are unchanged.

Only the unmerged policy migration changes; published #130/#333 migrations and
contract snapshots are untouched. Catalog and usage audit vocabulary is retained.
Rollback requires removing this policy foundation together, and cannot discard
new audit evidence. Later PR publication waits for predecessor integration;
local descendant recovery does not. Human acceptance remains pending.
Sanitized: yes. No credentials, prompts, outputs or live-provider calls.
Deferred: media storage unavailable; screenshot evidence is mandatory.
