# Issue #567 — controlled external-effect evidence

## Scope and provenance

Primary evidence kind: **controlled integration**. [Design](../../design/issue-567-controlled-effects.md)
records the boundaries and pre-implementation failure modes. The actual application,
investigator HTTP client and PostgreSQL runtime are used. A separate controlled
gateway commits a real SQLite counter mutation; its model answer is deterministic.
No real provider, Grafana, mitigation, production or paid service was invoked.
Responses/discovery have contract-shaped wire metadata; absent consumption with
the schema's fixed `openrouter` source is fixture metadata, not provider/billing proof.

#580 is integrated at `139d1cf2cf21c410b579c5c696c4a83c51b56388`; #330 is closed.
Revalidated main base: `763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`.
Live #567 remains open, Projects #8 Todo, no Sprint 5 commitment. The user authorized
publishing the three PRs and sanitized artifacts on a dedicated evidence branch.
Merge and issue closure remain unauthorized; human acceptance is still pending.

## Environment

Use a clean checkout of the final candidate, Git, Docker/Compose and the preserved
Dockerfiles/uv.lock/package-lock.json. Docker version is recorded in the delivery;
after runtime continuation this host uses Docker client/server 29.9.0.
Use `.env.example` only; the checks profile reuses synthetic seed identities and
its dedicated trust-authenticated, tmpfs PostgreSQL 17.4 service. No `.env`, new
credential or normal persistent demo DB is used. The isolation guard must pass.

Prefer the Git/Docker-only host wrapper `scripts/reproduce_issue567_evidence.sh`,
passing an absolute persistent output directory outside the checkout. It derives
and verifies HEAD, base ancestry and clean source, preserves the owned container's
exit status, and records Git source identity before invoking containerized checks.
Every invocation requires a new empty output directory, checked after canonical
path resolution. An atomic attempt marker gives even the same SHA/project a unique
container name, recorded in identity.txt. Existing evidence is never overwritten.
It never trusts a manually entered tested SHA. If using the individual Docker
commands below, prepare the same environment with the checkout's verified full
HEAD/base and an empty writable `ISSUE567_OUTPUT` directory. Use a unique Compose project
name (below: e567-ca-01a1331e). The internal-network override uses a /28 because
this host's default pools are exhausted. If that subnet is occupied, select an
unused local subnet with `ISSUE567_SUBNET`; never prune unrelated networks.
Synthetic test fixture initialization resets only this project's disposable checks
DB; do not point TEST_DATABASE_URL at an existing/shared database.

## Reproduction commands

Run from the checkout root. All package tooling runs inside existing Compose services.

```sh
docker compose --env-file .env.example -f compose.yaml -f docs/evidence/issue-567/compose.yaml -p e567-ca-01a1331e --profile checks run --build --rm --user "$(id -u):$(id -g)" -e ISSUE567_OUTPUT=/proof -e ISSUE567_TESTED_SHA -e ISSUE567_BASE_SHA -v "$ISSUE567_OUTPUT:/proof" python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q -s -p no:cacheprovider tests/test_external_effects_e2e.py'
docker compose --env-file .env.example -f compose.yaml -f docs/evidence/issue-567/compose.yaml -p e567-ca-01a1331e --profile checks run --rm --no-deps --user "$(id -u):$(id -g)" -v "$ISSUE567_OUTPUT:/proof" python-checks python scripts/inspect_issue567_evidence.py /proof
docker compose --env-file .env.example -f compose.yaml -f docs/evidence/issue-567/compose.yaml -p e567-ca-01a1331e --profile checks run --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && ruff check --no-cache . && ruff format --check --no-cache . && python scripts/validate_run_api.py && pytest -q -p no:cacheprovider tests/test_incident*.py tests/test_investigator*.py tests/test_mcp*.py tests/test_import_boundaries.py tests/test_run_api_contract.py'
docker compose --env-file .env.example -f compose.yaml -f docs/evidence/issue-567/compose.yaml -p e567-ca-01a1331e --profile e2e run --build --rm --no-deps --user "$(id -u):$(id -g)" -v "$ISSUE567_OUTPUT:/proof" -v "$PWD/scripts/capture_issue567_evidence.cjs:/e2e/capture-issue567.cjs:ro" e2e node /e2e/capture-issue567.cjs /proof
```

The first command exports one JSON report and receiver SQLite store per scenario.
Run the SQL inspection second, before any other suite resets the disposable DB.
It independently rereads the receiver files and live PostgreSQL receipts/result
counts, exporting runtime-sql.json. Keep output in persistent storage, not /tmp,
when the runtime may recreate its temporary filesystem on continuation.
Each records tested/base SHA, expected/observed outcome, HTTP read/resume/replay,
correlation, process restart and receiver state. The final command captures the
actual exported SQL JSON in a native Chromium tab, without generated HTML, a
synthetic UI or an invented capture; it is not a live view.
Never source a PR description as shell or execute arbitrary PR-supplied commands.
The test report's scenario can be selected with pytest `-k` inside the first command.

## Acceptance matrix and expected results

| Criterion | Reproducible scenario / artifact | Required observation |
| --- | --- | --- |
| Confirmed effect | success.json + success-receiver.sqlite | counter 1, one applied operation; receiver UUID in success receipt, same run/incident/task |
| Confirmed failure | reject.json + reject-receiver.sqlite | sent operation explicitly rejected by receiver, counter 0; correlated confirmed_failure / governed_call_denied |
| Interrupted unknown | before_dispatch, before_effect, after_effect, before_commit JSON/SQLite | SIGKILL, independent receiver retained, new runtime process; pending then unknown on exact replay; no partial result or redispatch |
| Recovery/retry limits | all JSON/SQLite; concurrent.json, timeout.json, loss.json, 5xx.json | read/resume recover without producer execution; exact replay leaves terminal outcome unchanged; no duplicate operation |

`before_effect` demonstrates delayed external application after restart/replay;
counter moves 0 to 1 while runtime stays unknown. `before_commit` observes an actual
PostgreSQL INSERT blocked after receipt of the receiver response, then kills the
runtime before commit. Timeout, lost response and 5xx may all coexist with an effect.
No transient retry is credited, and the receiver does not deduplicate operations.

`pre_dispatch` means an **unconfigured producer**, with zero receiver calls; it is
not a failure of a sent operation. The separate existing
`test_mcp_contract_rejection_before_dispatch_is_confirmed_failure` in the second
command checks real governed HTTP 422 rejection before upstream MCP invocation.
Its mock upstream call count is internal contract evidence only, not external-effect
proof. It is not substituted for the receiver-observed sent rejection above.

## Results, review and limitations

Final observed results, full candidate SHA, image provenance, logs and the real
screenshot are exported with the delivery records; do not infer acceptance from
this recipe alone. Initial attempts encountered exhausted Docker pools and loss of
the owned checks DB; those failed runs are not passing acceptance evidence.
Current-state checks and available independent review must be rerun on the final
candidate. Hosted CI and real-provider runs are not claimed.

Read-only GET/resume does not terminalize an orphaned intent: it stays pending until
an exact start replay records unknown. Runtime unknown is never overwritten using
the observer's receiver knowledge. This does not provide reconciliation, cancellation
of a sent operation, cross-system atomicity or general external exactly-once.

Sanitized: yes. Only synthetic IDs, bounded statuses and counter state are exported;
no headers, prompts, model text, personal data, secrets or raw application logs.
Video: Deferred: media storage unavailable; screenshot evidence is mandatory.
HTTPS screenshot/artifact publication is authorized on a dedicated repository
evidence branch, separate from the source stack. PRs must link the actual immutable
artifact commit and obtain human review; authorization alone is not publication.
Source is split into three local branches: `codex/issue-567-controlled-receiver`
against main, `codex/issue-567-external-evidence` against the receiver branch, and
`codex/issue-567-evidence-recipe` against the E2E branch. Each unit is below 400
added-plus-deleted lines against that explicit base. The aggregate series exceeds
400; do not publish it as one acceptance PR without explicit size approval.
PR creation is authorized; no size-exception approval exists. If the host wrapper is interrupted,
inspect/wait the container named in identity.txt; do not restart merely because
the terminal handle disappeared. Only scoped stopping/cleanup is permitted.
Cleanup, when desired, is limited to stopping this project's checks DB with Compose
`stop python-checks-db`; never use global pruning or `down -v` as reproduction steps.
