# Issue #330 CA1 — HTTP run survives API restart

## Result and evidence status

The historical local run is reported as a **passed controlled integration**:
an authenticated TCP HTTP request created a triage run, and the run remained
readable after restarting the API process while retaining the PostgreSQL
container and named volume. Replay and resume returned the same run without
adding durable run records. This is not human acceptance, issue closure,
production validation, or a claim of external exactly-once behavior.

**Evidence inventory:** the PR includes the original
[before](verified/ca1-before.json) and [after](verified/ca1-after.json) captures,
[container identities before](verified/containers-before.jsonl) and
[after](verified/containers-after.jsonl),
[runtime source hashes](verified/runtime-source-hashes.txt),
[runtime versions](verified/runtime-versions.txt),
[final checks](verified/final-checks.log),
[HTTP state screenshot](verified/http-state-after.png),
[HTTP events screenshot](verified/http-events-after.png), and
[schema-tooling progress](schema-tooling-progress.log).
These are the inspectable records for the historical journey. The separate
source manifest and implementation patch, full journey log, checks-database
storage record, Docker restart-event capture, browser capture script, and full
Python-suite logs were local-only and are not included in the PR. No such
missing artifact is linked or represented as committed evidence.

Historical run: `run_084284a4f8a41001`, tested HEAD
`c7d297cbb11059b1b958e2dece8d54d9db016e1c`, branch at test
`codex/triage-23-integrated`; execution 2026-10-07 America/Bogota (UTC
artifact date 2026-10-08). The PR branch is now
`codex/ca1-http-restart-proof`; its later reproduction tooling/report changes
do not change the historical tested SHA.

## Historical journey (reported)

| Check | Reported observation |
|---|---|
| Before creation | Synthetic incident had no runs: HTTP detail `runs=[]`; SQL run/event/snapshot/transition-commit counts were zero. |
| Create | Authenticated TCP `POST /v1/incidents/inc-ca1-http-restart/runs`, body `{"workflow_version":"1.0.0","objective":"triage"}`; schema-valid HTTP 201 and one run. |
| Initial reads | State `triage`, status `running`, cursor `seq:0`; SQL version 1; one event, snapshot and transition commit correlated to the run/key. |
| Restart | API PID changed from `289577` to `307918`; StartedAt changed from `2026-10-08T00:14:30.112656943Z` to `2026-10-08T00:15:24.348037006Z`. |
| Database continuity | DB PID `278089`, StartedAt `2026-10-08T00:13:56.705306352Z`, container and named volume were reported unchanged. |
| After restart | State/events and SQL records were reported equal to baseline before replay/resume. Replay and resume returned the same run; counts remained one run/event/snapshot/commit. Anonymous reads returned 401; restricted credential reads returned 403. |

Historical runtime identities: API/DB container IDs, process evidence, mounts
and their image digests are in the committed container records. The checks-image
digest below is transcribed from the local report; its image manifest is not
included. Runtime software versions are in the committed versions file.

- API container `f4d0b11566cb0b8bb9ad92b25a05a585b2672faaf5d1adf3864c4b4c71f50d27`
- DB container `d57b51cf279c0ab2e342d3159549d858cc71bf8fc8660d31d94a5351ec41c23d`
- Volume `ca1-01a118c1-verified_postgres_data`, mounted at
  `/var/lib/postgresql/data`
- API image `ca1-01a118c1-verified-api@sha256:63f46bfa4f927e4efba920fa468602a0cc163c1dc859d79bf41a6a84342bded4`
- Checks image `ca1-01a118c1-verified-python-checks@sha256:848c45bbb52f9728761794428ab653b8b488b46932498ac6c008e7e056ff093e`
- PostgreSQL image `postgres:17.4-alpine@sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5`

The reported harness used real FastAPI/uvicorn, bearer authentication,
PostgreSQL and a named volume. It provisioned synthetic local principals,
credentials, grants, and incident through existing services; the evaluated run
was created via HTTP, not inserted through SQL. SQL observations were read-only.
The public state schema has no `version` field; version was read from SQL.
Provider/mitigation invocation, production, CA6/#567 and broader exactly-once
claims were out of scope.

## Historical checks and hosted CI

The historical local report stated that the full Python suite passed twice
(1,774 passed / 1 skipped each time; 715.02s and 663.70s). The associated
full-suite logs are not included, so these remain **reported historical local
results, not independently inspectable from this PR**. The committed
`verified/final-checks.log` records the available final checks; see it directly
for its exact scope and result. The reported skipped test was the external
OpenRouter live smoke test. The included runtime source hashes and browser
screenshots are inspectable; the separate source manifest, Docker event capture
and browser capture script are not included.

Separately, hosted CI for the original PR head passed all eight jobs, including
contracts, unit and browser checks: [GitHub Actions run 37876155174](https://github.com/creep1ng/sre-agent/actions/runs/37876155174).
That hosted run is not evidence that the local CA1 Docker journey was run by CI.

## Reproduction on this PR branch

From the root of a checked-out PR branch `codex/ca1-http-restart-proof`, use a
host with Git, Python 3 and Docker Compose. First inspect Docker networks
read-only and select an unused private IPv4 `/28`, a `ca1-` project name,
distinct unused API/database ports, and private/evidence directories outside
the repository. Example:

```sh
python3 scripts/prepare_ca1_config.py \
  --project ca1-local-repro --private-dir /tmp/ca1-local-repro-private \
  --evidence-dir /tmp/ca1-local-repro-evidence --subnet 10.253.143.0/28 \
  --api-port 58144 --db-port 58145
CA1_ENV_FILE=/tmp/ca1-local-repro-private/local.env \
CA1_OVERRIDE=/tmp/ca1-local-repro-private/compose.proof.yaml \
CA1_EVIDENCE_DIR=/tmp/ca1-local-repro-evidence \
CA1_PROJECT=ca1-local-repro scripts/prove-ca1-compose
```

The generator refuses unsafe/duplicate inputs and overwrites, creates the
private env file exclusively with mode `0600`, and does not print secrets. It
validates required Compose settings, a tmpfs-only checks database and evidence
mount. Its default build revision comes from the checkout's Git HEAD; an
explicit hexadecimal revision can be supplied with `--build-revision`. Use a
fresh isolated project/subnet/ports for each run. The runner builds the API and
checks images, executes prepare/before, restarts only the API, waits for
readiness, then executes after. It uses the checks database for destructive
tests; it does not run pytest against the persistent demo database. Keep the
project volume and do not use `down -v`, prune, or restart another project.

This procedure is a new reproduction, not a recovery of the absent historical
archive. Its outcome must be recorded separately; it cannot retroactively
change the historical tested SHA or results above.
