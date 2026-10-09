# Issue #330 current-main verification

**Candidate:** `feat/issue330-run-commands`, rebased onto current `main` `23e1a42dd1f3c0ad98b76ee6f5f25906570d50c2`. The rebase adds #568 CA1 proof and #541 evidence tooling; none of their changed paths overlap this candidate. This is an unpushed delivery candidate; GitHub Codex review, merge, and issue closure are still pending. The controlled packaged browser capture below was made immediately before that docs/tooling-only main advance, against application/build-input tree `371fefe2f9cdce578d1353e709cbaeb8da0846e5` (a Git tree object ID, not a commit SHA). The rebase changed no API, UI, schema, compose, or test files; the fresh current-main suite and UI review tests were rerun after rebase.

## Current-candidate evidence

| Criterion | Result and evidence boundary |
| --- | --- |
| CA1 — durable start/resume | Current main already contains #568’s controlled HTTP-created-run/process-restart proof in [`CA1-report.md`](ca1-http-restart/CA1-report.md), with its committed before/after captures and runtime records. The candidate suite also passes; the separate local HTTP/PostgreSQL record is [here](issue330-current-main-http-durability.log). These are not external-provider evidence. |
| CA2 — stale review/version and idempotency | The suite verifies stale reviewed v2 against changed v3 is rejected without mutation, a missing version is rejected, exact same-key retry returns historical result without reapplying, and changed payload conflicts. A historical retry does not authorize v3. |
| CA3 — owner isolation | Foreign run/read/command access is checked in the selected HTTP/PostgreSQL suite; the full selected suite passed. |
| CA4 — version-bound approval | Approval/reject/request-changes bind the authenticated reviewer to the incident/artifact revision. The UI sends the version fetched for the displayed review. A conflict requires a new explicit review; there is no automatic approval retry. |
| CA5 — investigation path | The supported HTTP investigation path and persistence/restart behavior pass against controlled local synthetic dependencies. This does **not** prove an external provider response on this current-main candidate. The previous T36 live success belongs to the earlier candidate and is not credited here. |
| CA6 — external-effect receipt/exactly-once | Not claimed; tracked separately in #567. No general exactly-once guarantee is made. |
| CA7 — governed authorization | The packaged local UI replay verifies the synthetic demo identity, a successful command, and a mismatched-identity denial. It is controlled integration evidence, not production IAM or live-provider proof. See [safe replay result](issue330-current-main-ui-replay.json) and [actual browser capture](issue330-current-main-ui.png). |

Two current-main P1 regressions were reproduced before correction and are repaired:

1. **MCP response contract drift:** success included `request_id` in the JSON body although the published result schema is strict and places correlation in `X-Request-ID`. The public body and FastAPI response models/examples now match the strict schema; correlation remains in the header. The generated-contract probe reported `OPENAPI_GREEN` (see [sanitized result](issue330-current-main-openapi.log)).
2. **Shipped review UI omitted the revision:** the fresh approval request lacked `expected_incident_version` and received 422 without a write. The three review actions now send the version fetched for the displayed review. The packaged replay records HTTP 202 for the valid synthetic reviewer and HTTP 403 for the mismatched principal; PostgreSQL readback recorded one decision for the valid scenario and zero for the mismatch.

The screenshot intentionally records the actual post-command page: its detail card still displays the fetched pre-command `mitigating · awaiting_human` snapshot while the backend receipt reports `approve_mitigation` accepted, transition `apply_mitigation`, and run `verifying`. This is a stale display snapshot (P2), not evidence that the backend command failed. The page does not claim mitigation has completed. No P2 UI redesign was included in this correction scope.

## Reproduction

Run from the repository root in an isolated Docker Compose environment. The Python checks use `.env.example` and the repository's DB-isolation guard:

```sh
docker compose --env-file .env.example -p issue330deliveryrebased23e --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && ruff check --no-cache . && ruff format --check --no-cache . && python scripts/validate_run_api.py && pytest -q -p no:cacheprovider tests/test_incident*.py tests/test_investigator*.py tests/test_mcp*.py tests/test_import_boundaries.py tests/test_run_api_contract.py'
```

Observed on the rebased main (`23e1a42dd1f3c0ad98b76ee6f5f25906570d50c2`): isolation guard passed; Ruff passed; formatting passed (`251 files already formatted`); API validator passed (`5 paths, 5 schemas, 6 positive and 8 negative examples`); pytest passed (`440 passed`, 2 third-party websockets deprecation warnings, 58.75s). The owned Compose project was removed after the run. A compact sanitized record is [available here](issue330-current-main-checks.log). A separate run of the existing browser-review mock seam passed 14 tests in 19.1s; it is not a production API test. The exact command and scope are recorded below.

The packaged UI case reused the existing [Issue 419 replay harness](../issue-419/replay/README.md) with a private synthetic env file and an ephemeral seed changing only the mitigation ID to the currently valid `mit_issue330_payment_flag`. It ran the packaged API/web stack and the existing Playwright replay; no external model/provider credential was configured or called. Playwright reported `1 passed (1.8s)`. The safe JSON records the pre-rebase application/build-input tree, HTTP outcomes, and synthetic identities; it contains no credential. The screenshot is an unaltered capture from that browser run. The only later main changes are CA1/evidence records and standalone verification scripts; no application, UI, schema, Compose or browser-test bytes changed. The owned Compose stack and temporary files were removed after readback.

The packaged browser case can be replayed from a fresh checkout with a unique private env/output directory and Compose project. `prepare_env.py` creates synthetic credentials; the seed substitution is intentionally confined to a temporary file and fixes only the mitigation ID required by the current runtime:

```sh
set -eu
REPLAY_DIR="$(mktemp -d)"
chmod 700 "$REPLAY_DIR"
ENV_FILE="$REPLAY_DIR/compose.env"
OUTPUT_DIR="$REPLAY_DIR/output"
mkdir -m 777 "$OUTPUT_DIR"
PROJECT="issue330-replay-$(date +%s)"
BUILD_TREE=371fefe2f9cdce578d1353e709cbaeb8da0846e5
python3 docs/evidence/issue-419/replay/prepare_env.py --output "$ENV_FILE" --source-sha "$BUILD_TREE"
sed 's/mit-disable-payment-flag/mit_issue330_payment_flag/' docs/evidence/issue-419/replay/seed.py > "$REPLAY_DIR/seed.py"
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile e2e up --build -d web
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile checks run --build --rm --no-deps -v "$REPLAY_DIR/seed.py:/tmp/issue419-seed.py:ro" -v "$PWD/agent/fixtures/incidents/otel-payment-failure/initial-state.yaml:/fixtures/initial-state.yaml:ro" python-checks python /tmp/issue419-seed.py
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile checks run --build --rm --no-deps python-checks python scripts/provision_incident_workflow.py
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" --profile e2e run --build --rm --no-deps -v "$PWD/docs/evidence/issue-419/replay:/e2e/issue419-replay:ro" -v "$OUTPUT_DIR:/evidence" e2e npx playwright test --config=/e2e/issue419-replay/replay.config.js
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" exec -T db psql -U sre_agent -d sre_agent -F '|' -Atc "SELECT i.incident_id, i.version, r.run_id, r.state->>'status', r.state->>'current_state', count(d.decision_id) FROM incident.incidents i JOIN incident.runs r USING (incident_id) LEFT JOIN incident.decisions d USING (incident_id, run_id) WHERE i.incident_id IN ('inc-issue419-final-browser','inc-issue419-final-mismatch') GROUP BY i.incident_id,i.version,r.run_id,r.state->>'status',r.state->>'current_state' ORDER BY i.incident_id"
docker compose --env-file "$ENV_FILE" -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p "$PROJECT" down --volumes --remove-orphans
rm -rf -- "$REPLAY_DIR"
```

The generated env file is private and must never be printed or committed. This recipe makes no external provider call. The result JSON intentionally projects only selected request fields; source `public/incident-ui/review.js` shows the fetched version field, while the successful fresh command plus the API's required-version guard verifies the request was accepted by the versioned route.

The separate browser mock-seam tests for the review UI run in the existing E2E container; they complement (not replace) the packaged API replay:

```sh
docker compose --env-file .env.example -f compose.yaml -f docs/evidence/issue-419/replay/compose.overlay.yaml -p issue330reviewui23e --profile e2e run --build --rm --no-deps -v "$PWD:/workspace:ro" -v "$PWD/tests/browser:/e2e/tests/browser:ro" -v "$PWD/docs/evidence/issue-419/replay/review.config.js:/e2e/playwright-review.config.js:ro" e2e npx playwright test --config=/e2e/playwright-review.config.js tests/browser/review.spec.js
```

Observed after rebase: **14 passed (19.1s)**, including assertions that approve, reject, and request-changes payloads carry the fetched incident version. This uses a mocked HTTP seam; the compact result is [here](issue330-current-main-browser-tests.log). The packaged replay above exercises the real local API/web containers with synthetic credentials.

## Delivery boundary

This candidate incorporates current-main behavior while preserving #546's triage/alert integration; it is not the pre-#546 patch transplanted wholesale. T36 remains historical evidence for the earlier patch SHA and is not evidence that this integrated candidate was live-tested. The current local checks establish no P0/P1 within this bounded correction scope; independent final review and GitHub CI/Codex review are still pending. The one-PR size exception was explicitly authorized and is recorded in the task tracker; no protected label was added. The approval rule remains version-bound: a changed proposal requires a new human approval, and v2 approval never authorizes v3.

## GitHub Codex P1 correction

Codex reviewed the published initial candidate and found that malformed model output or unknown references could omit successful governed Responses request IDs from the durable receipt. The local HTTP/PostgreSQL proof first reproduced both gaps: two malformed replies correlated zero Responses audit rows; an invalid reference followed by a valid recovery correlated only the final row. Exact start replay already left persisted state unchanged.

The correction records each successful reply ID before parsing or validating references. The same end-to-end proof now correlates both HTTP 200 Responses audit rows from the persisted receipt in both failure and recovery paths, with unchanged exact replay and no MCP invocation. See [safe correction evidence](issue330-codex-p1-evidence.json). No raw model output is retained in this artifact.

The exact CI declarative/typechecking commands were also exercised locally. Duplicate skill-model/function declarations and duplicate annotations introduced during porting were removed without changing behavior. Shellcheck, Ruff/format, lock validation, import boundaries, targeted mypy (11 source files), incident contracts/authorization/run API/queries and CI hardening checks passed. The corrected scoped suite passed 442 cases with two upstream deprecation warnings. An initial local invocation used a nonexistent import-check script and a formatter invocation hit container ownership permissions; neither was counted as verification. The final invocation used the repository's actual `lint-imports` command and the workspace owner's UID for the check-only normalization boundary. CI and fresh Codex review on the pushed correction remain separate checks.
