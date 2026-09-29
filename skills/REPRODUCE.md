# Reproduce the Skills stack acceptance audit

These probes execute the actual candidate FastAPI application with real, isolated PostgreSQL.
They use controlled synthetic data, not a live model or external service. Screenshots render
the recorded response/SQL metadata; they are not screenshots of a production UI.

## Prepare a candidate and evidence checkout

Use Git to obtain `creep1ng/sre-agent` and detach at the exact head below. Keep the published
evidence directory from the audit branch in a separate checkout/directory; it supplies
`probe.py`, `inside-focused.py` and `audit_capture.py`. No private cached image is needed:
the first Docker command builds the checks image from the candidate Dockerfile and lockfile.

| PR | Exact candidate head | Focused `AUDIT_TESTS` |
| --- | --- | --- |
| 387 | 71068cd6e78d6c3bd3bd8c85baa8452e5934fe5b | tests/test_control_plane.py tests/test_migrations.py tests/test_persistence_repositories.py |
| 388 | 3f7fae89089d9861ee3a17be465dd63be7f41881 | tests/test_control_acceptance.py::test_skill_version_read_is_limited_to_catalog_admin tests/test_demo_seeds.py |
| 397 | add6400f2383fea30f0c0cb9c19c49d29323f710 | tests/test_skill_publication.py |
| 403 | c41aeaebe90e7d91d23892076b1b85c06db5c465 | tests/test_health.py tests/test_migrations.py |
| 402 | ed0622cade395d538efc04d8f23c4b13e04e4c46 | tests/test_skill_activation.py tests/test_health.py |
| 404 | 523f80cdf2a99f5fefea5a288e20c7bb04ea3fb2 | tests/test_health.py tests/test_audit.py tests/test_migrations.py |
| 405 | 6d94a92cdbc92f85ceb265df0bc2b5b2d553d12f | tests/test_skill_resolution.py tests/test_governed_authorization.py |
| 406 | 9729393213ec2c77412f014ab044d78e00767de5 | tests/test_skill_resolution.py |
| 407 | 86857537b2dff25874e93794ec5c89cd98238933 | tests/test_skill_lifecycle_proof.py |
| 409 | c0d48c5c31d518d198a5ccdcd61b25f8990b06ac | tests/test_skill_publication.py tests/test_skill_activation.py tests/test_skill_resolution.py tests/test_skill_lifecycle_proof.py tests/test_skill_demo.py |

From the candidate root, prepare these non-secret shell variables: `AUDIT_PR` (PR number),
`AUDIT_HEAD` (matching exact table SHA), `AUDIT_TESTS` (table value), `AUDIT_PROJECT` (a new
unique lowercase Docker project/container prefix), `EVIDENCE_DIR` (absolute path to this
evidence directory), and `OUTPUT_DIR` (a new, writable absolute directory). Confirm the
checkout SHA with Git. No `.env` is read; Compose interpolation uses tracked `.env.example`.

Host prerequisites are Git, Docker/Compose, and safe directory/variable setup. Builds may
need network access to the public pinned Python image and Python/OS package registries.
The candidate Dockerfile pins Python by digest, uses uv 0.8.14 and the committed `uv.lock`;
OS packages installed during the checks stage are not fully reproducible by immutable digest.
The audit used Docker 29.8.1, Python 3.12.14 and PostgreSQL 17.4. Tests/probes themselves use
no network outside their private network namespace.

## Container-only reproduction

Use a new `AUDIT_PROJECT` for each PR and each independent full-suite run. These commands
must never target a shared or existing database. The wait loop in `inside-focused.py` waits
for PostgreSQL readiness before running the selected tests.

```sh
docker compose --env-file .env.example --profile checks -p "$AUDIT_PROJECT" build python-checks
docker run --pull missing -d --name "${AUDIT_PROJECT}-db" --network none --tmpfs /var/lib/postgresql/data -e POSTGRES_DB=python_checks -e POSTGRES_USER=python_checks -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17.4-alpine@sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5
docker run --user "$(id -u):$(id -g)" --pull never --rm --network "container:${AUDIT_PROJECT}-db" -v "$PWD:/repo:ro" -v "$EVIDENCE_DIR:/evidence:ro" -v "$OUTPUT_DIR:/results" -w /repo -e PYTHONPATH=/repo/src:/evidence -e TEST_DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks -e DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks -e PYTEST_ADDOPTS='-p no:cacheprovider -p audit_capture' -e EVIDENCE_OUT=/results -e AUDIT_PR="$AUDIT_PR" -e AUDIT_HEAD="$AUDIT_HEAD" -e AUDIT_TESTS="$AUDIT_TESTS" "${AUDIT_PROJECT}-python-checks:latest" python /evidence/inside-focused.py
docker run --user "$(id -u):$(id -g)" --pull never --rm --network "container:${AUDIT_PROJECT}-db" -v "$PWD:/repo:ro" -v "$EVIDENCE_DIR:/evidence:ro" -v "$OUTPUT_DIR:/results" -w /repo -e PYTHONPATH=/repo/src -e TEST_DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks -e DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks -e EVIDENCE_OUT=/results -e AUDIT_PR="$AUDIT_PR" -e AUDIT_HEAD="$AUDIT_HEAD" "${AUDIT_PROJECT}-python-checks:latest" python /evidence/probe.py
```

Skip the last command for PR 407: its dedicated lifecycle test supplies the behavioral proof.
`probe.py` deliberately resets the isolated database schema. Never run it against a reused
demo/shared database. Do not run a subsequent full suite in that reset schema: create a fresh
PostgreSQL container so stock public-schema privileges are preserved. An empty `AUDIT_TESTS`
value runs the full suite through `inside-focused.py`; remove the capture plugin from
`PYTEST_ADDOPTS` if only test output is needed.

Only remove the single named `${AUDIT_PROJECT}-db` container when finished. Its data lives in
tmpfs. Do not use a global volume teardown, prune or shared-database cleanup.

## Expected observations and caveats

- 397: 37-character version yields HTTP 500 instead of 422.
- 402: unpublished version status yields 500 instead of 404. **Simulated audit outage**:
  only `PostgresAuditStore.append` is made to raise; the real SQL lifecycle mutation still
  persists inactive despite HTTP 503 and zero terminal audit. Retry returns 409.
- 404: a Skill audit DTO carrying OpenRouter input token evidence validates and persists.
  This is DTO/repository proof, not a claim that the normal gateway emits such usage.
- 405: a success response fails its own declared model; malformed path returns 422 with no
  request ID or corresponding audit; missing credentials produce 401 without Bearer challenge.
- 406: 16 directly granted dependencies cause 17 real scrypt verifications. A wrapper counts
  while forwarding every real verification; no authentication is bypassed. Timing is local
  observation, not a new acceptance latency limit.
- 409: inherits all of the above; the two original demo Skills otherwise follow the normal
  publish/activate/grant/deny/resolve scenario.

The capture plugin observes only selected response metadata, never request headers, keys,
instructions or full payloads. The synthetic fixture credentials inside `probe.py` are
public test values, not an existing session or production credential.

Reports separate focused local checks from hosted CI and independent human acceptance.
Full-suite success does not cancel deterministic negative-scenario findings.
