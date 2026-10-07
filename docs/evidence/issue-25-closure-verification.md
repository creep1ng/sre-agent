# Issue 25 integrated closure-gap verification

## Candidate and scope
The tested joint candidate is `791ce48e0bcd9496caf29f33df527166902bfadc`.
Its runtime/helper/UI source is `25b48de45d0b25afb619a29e817ea51cfb5e9076`;
the descendant changes only the existing governed-route test inventory. Runtime,
helper, UI and Compose files are byte-identical between these SHAs. Captures
truthfully retain deployed build revision25b48, not an invented791ce revision.
This includes PR378 → PR379 → PR385 → PR386 → PR490 → PR491 → PR497–502,
PR514–517, three bounded post-review corrections (125/400/10 lines), and current
main `c2074fd8cb90840bc1a747dfe5ad1ad332d9ee03` (authenticated identity API).
Immutable contract2.7.0 and all earlier releases are preserved.
Evidence/tracking-only commits do not replace the tested identity. This is joint
candidate proof, not proof that an earlier parent independently implements children.
Runtime source manifest SHA-256:
`33640bab0e5b655d4e52481bd17b1ef339932f6b2d1f3e7fd2721a339f3e4463`.
The manifest hashes sorted paths relative to `src/`, NUL, file hash and newline;
the host, verified HTTP helper image and running API matched independently.
HTTP helper SHA-256: `ae55d8a4d6fa802ff3793697e567b7d2a4766e98595fce25d617bf44b60069b6`.
Terminal helper SHA-256: `483aceb37dfabc82d9e294f3c86641c1ade65cb20a86bf400d829acdbb135dd6`.
Browser artifacts record served UI SHA-256
`0ccffe4504867c90dc103ea4ed97a108be14446ebfe526131c10dd1c75a45e2b`.
The allow producer requires three independently computed populated HMAC refs in
actual SQL and HTTP; raw controlled incident/run/task IDs are not emitted.

Full checks used the verified25b48 image plus only
`tests/test_governed_authorization.py` from791ce mounted read-only. This exactly
matches the tested candidate's source/test tree; it is not a claim the image was
rebuilt after the fixture-only commit. The build recipe below rebuilds that tree.
An interrupted build initially left an8f51 helper image: independent hashes found
the mismatch, rejected that temporary HTTP capture, and regenerated it after a
successful source-verified build. No provenance fields were manually repaired.

Live Projects #8 lists #25 as Done; it was human-closed at2026-10-07T03:24:35Z,
but the runtime stack remains unmerged. Pagination is explicitly deferred to#470,
not delivered. User acceptance of PR518ee827/sourcea592 was conditional and does
not establish freshness acceptance for this new candidate.
Route: delegated direct; AGENTS failure-first policy, no verified strict-TDD toggle.
RDD: disabled/unmanaged. New exact-head review, CI and human freshness remain gates;
no protection bypass or issue closure is authorized by this technical verdict.

## Criteria and evidence
| Criterion | Observed proof / boundary |
| --- | --- |
| CA1 bounded filters | HTTP/SQL producer correspondence; forbidden parameters tested with valid decision filter. Truncation is explicitly partial. Stable pagination is deferred, not fulfilled. |
| CA2 safe detail | Actual persisted producer status/latency and SQL correlation; connected allow/deny navigation. SQL helper emits only request UUID and HMAC references, never raw IDs/content. |
| CA3 no content | Browser sensitive-marker checks before Apply while detail is open and after Apply; forbidden parameters + valid filter reject422. |
| CA4 no invented consumption | Existing metadata-only projection and browser checks; no tokens/cost computation added. |
| CA5 authorization/outage | HTTP401/403 no partial items; query-only fault after authenticated/authorized lookup persists503. Connected DB fault clears prior UI rows/details and displays503. |
| CA6 durable terminal/release gate | Actual per-request SQL deltas for read200/401/403/404/422/503. Append failure returns503 and zero rows; no-op/double-append mutations are rejected by the capture probe. |

`issue-25-audit-http.json`: controlled FastAPI/PostgreSQL + deterministic provider,
not a live provider outage. Producer statuses200/403/401/422/503 have counts1 each;
failed producer append503 has count0. `read_controls.sql_count` refers only to
`responses.create` rows for an unused selector, not to the new terminal read rows.
`issue-25-terminal.jsonl` records those terminal rows independently.
`issue-25-audit-browser.json` labels injected detail404/503 and truncation as mocks.
`issue-25-correlation.json` and `issue-25-query-failure.json` are connected UI proof.
The connected fault deliberately renames the audit table: both its SELECT and append
become unavailable while identity/grant tables remain intact. It is not a killed
database or query-only append-success proof; the HTTP boundary suite covers that.

## Verification
- Fresh-review UI failure-first: retained banner remained after a later successful
  detail; corrected scenario passes for both404 and503. Parent complete browser
  suite on the integrated API/UI:12 passed in18.3s.
- Prior all-null correlation assertion failed; refreshed helper requires populated
  incident/run/task HMAC refs and passed actual producer/SQL checks. Producer
  statuses200/403/401/422/503 persist one row; append-failure503 persists zero.
- Fresh full Python and prechecks: 1607 passed,1 skipped in310.49s;
  Ruff/format/lock/import boundaries/mypy and Alembic check passed. The skip is
  the opt-in live OpenRouter case..
- Fresh terminal boundary and SQL capture: 13 passed in7.93s; actual helper
  emitted11 JSONL records on the integrated image and isolated PostgreSQL..
  Typed mutation probes accept only exact1→0/1→2 row-count failures after valid
  HTTP envelopes and all SQL rows are checked; wrong statuses/malformed rows
  propagate. Authenticated403/404/503 identity/resource refs are asserted against
  independently computed seeded HMAC expectations, with no `else True` branches.
- Controller failure-first: the old unprotected sequence left the table renamed.
  Marker-write failure, done timeout and a reported browser failure all exit
  nonzero but restore the original table. Real connected fault200→503 clears
  one prior row/detail to0/0 with visible error. The raw helper precondition is
  archived unchanged as `issue-25-query-precondition.json`; restoration SQL is
  `issue-25-query-restoration.txt` (`t|t`). No manually invented JSON fields.
- Fresh connected allow/deny navigation remains200→403→200; metadata/detail
  captures, mock404/503/truncation and real fault are explicitly distinguished.
- Earlier a592 precheck stopped at RuffUP012 in the helper; mechanical encoding
  correction was made before restarting. No failed run is presented as a pass.
- Previous e1847 Python1567/1skip and browser11 results are historical only.
  Canonical UUID validation now rejects noncanonical forms outside the valid legacy language.
- Exact-credential/private-marker artifact scans passed; real screenshots are
  manually inspected. Hosted CI, human acceptance and merge remain separate gates;
  no live-provider, killed-DB or offline demonstration is inferred.

Post-review checks rejected a valid list envelope for detail reads and mutation
probes before classifying row counts. Runtime OpenAPI now describes the released
filters/path/bearer/success/error/governed scope. Digit-leading compact, braced and
URN UUID forms return422 with one validation terminal; valid legacy compact IDs
retain authorized404 lookup. The initial full run had1606pass/1skip/1fail because
the existing governed-operation inventory lacked the two newly documented routes;
its assertions were preserved and the inventory adapted before the full GREEN.
Old8f51/first25b48 build jobs were interrupted(exit130), not counted as passes.

## Environment and safe reproduction
Git/Docker host; Python3.12.14, PostgreSQL17.4 pinned digest and Playwright1.63.0
images/lockfiles from the tested source. Prepare ignored mode600 `.env.worktree`
from `.env.example`: DB `audit25_closure`, user `sre_agent`, URL host `db`, fresh
synthetic keys/HMAC, `lab/model` + `lab`, no external keys, contract2.7.0,
build revision25b48de45d0b25afb619a29e817ea51cfb5e9076 (the deployed runtime source). Never print/source/upload this file.
Use a fresh Compose project; choose an unused `ISSUE25_EVIDENCE_SUBNET` when needed.
Existing services only; combine the no-host-port overlay with the small IPAM overlay.
The terminal helper resets only disposable `python_checks`, never the evidence DB.

```sh
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml up -d --build web
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks run --build --rm python-checks
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/audit-events.spec.js
docker run --rm --network audit25-closure_runtime --env-file .env.worktree audit25-closure-python-checks python scripts/verify_issue25_audit.py > docs/evidence/issue-25-audit-http.json
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks run --rm python-checks sh -c 'pytest -q tests/test_audit_read_terminal_boundary.py && python scripts/capture_issue25_audit_terminal.py'
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_audit.mjs:/e2e/capture.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_correlation.mjs:/e2e/capture.mjs:ro" -v "$PWD/public/admin/audit-events.js:/candidate/audit-events.js:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
```

## Detail error recovery screenshot
`issue-25-detail-recovery.png` is an actual Chromium screenshot at the end of the
existing mock journey: detailA404/503 survives list refresh, then detailB200 clears
the retained banner. It is not a connected API claim. The container derives only
screenshot/output settings from the committed production config; traces remain off
and the test/source files are unchanged. The focused journey passed in4.9s.

```sh
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e sh -c 'node --input-type=module -e '\''import config from "./playwright.production.config.js"; import {writeFileSync} from "node:fs"; config.use.screenshot="on"; config.outputDir="/tmp/detail-recovery"; config.testDir="/e2e/tests/browser"; writeFileSync("/tmp/issue25-evidence.config.mjs", "export default "+JSON.stringify(config));'\'' && npx playwright test --config=/tmp/issue25-evidence.config.mjs -g "clears a retained detail error when a later detail request succeeds" && find /tmp/detail-recovery -name test-finished-1.png -exec cp {} /evidence/issue-25-detail-recovery.png \;'
```

## Connected query-fault reproduction
Only run on this fresh synthetic stack. The browser runs in the existing Playwright
image. A separate controller in the existing Python checks image waits for the
connected browser's precondition, renames only `public.audit_events`, activates the
browser fault, and restores/verifies the table in `finally` after success, capture
failure, marker-write failure, or bounded timeout. It accepts only the isolated
database host `db` and database `audit25_closure`; it has no Docker socket or new
service. The browser's own query-failure wait is bounded at90seconds; controller
marker waits default to120seconds. Do not terminate the controller or stop the
Docker daemon while the fault is active; external process interruptions do not
guarantee cleanup. The marker-writing browser/controller containers use the host UID
and GID so the host can inspect and remove their files.

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e sh -c 'rm -f /evidence/query-fault-ready.json /evidence/query-fault-active /evidence/query-fault-done /evidence/issue-25-query-failure-failed.json'
docker run --rm --detach --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_query_failure.mjs:/e2e/capture.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/control_issue25_query_fault.py:/app/scripts/control_issue25_query_fault.py:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-python-checks:latest python /app/scripts/control_issue25_query_fault.py
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml exec -T db psql -U sre_agent -d audit25_closure -v ON_ERROR_STOP=1 -tAc "SELECT to_regclass('audit_events') IS NOT NULL, to_regclass('audit_events_issue25_fault') IS NULL" > docs/evidence/issue-25-query-restoration.txt
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e sh -c 'cp /evidence/query-fault-ready.json /evidence/issue-25-query-precondition.json && rm -f /evidence/query-fault-ready.json /evidence/query-fault-active /evidence/query-fault-done'
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks --profile e2e down
```

The controller exits nonzero for a failed browser capture or a timeout, but still
checks and restores the table after the rename; the saved SQL readback is `t|t`
only when the original table exists and the temporary fault name is absent.

## Technical acceptance
I explicitly accept the five requested closure corrections on exact joint candidate
`791ce48e0bcd9496caf29f33df527166902bfadc`, based on independent complete Docker
checks, actual populated HTTP/SQL correlation, terminal persistence/release-gate
invariants and inspected real browser captures. This supersedes provisional e1847/a592
local technical acceptance for the current delivery candidate, not its historic facts.
CA1 acceptance covers bounded filtering and truthful truncation; stable pagination
remains explicitly deferred to #470, not delivered. This is local technical
acceptance, not independent human acceptance, hosted CI or a merge approval.
Fresh GitHub Codex review and ordinary human freshness acceptance remain pending.
The user approved a size exception only for final atomic integration; each fresh
correction PR remains at most400 changed lines. No protection or review bypass.
Rollback: revert the bounded runtime/UI changes; immutable releases untouched.
Sanitized: yes. Captures contain synthetic metadata, no raw producer content or keys.
