# Issue 25 integrated closure-gap verification

## Candidate and scope
The tested joint candidate is `5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288`.
Runtime/helper/UI source is the same exact tested commit `5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288`; captures truthfully declare that deployed build revision. This includes main
`4e3eb2b52e6979991c7f6d3f8a8b0bb8beb0b557` (identity, incident mitigation and review-command refresh lock).
This includes PR378 → PR379 → PR385 → PR386 → PR490 → PR491 → PR497–502,
PR514–517 and bounded post-review corrections (125/400/10/27/12/251/41/52 lines).
Immutable contract2.7.0 and all earlier releases are preserved. The default runtime
and safe example configuration activate2.7.0. Audit success payloads explicitly
advertise a runtime-local projection schema, not the narrower frozen2.7 metadata URN.
It derives all34 operations from the current DTO, retains accepted UUID/legacy IDs,
and excludes redacted content, redaction tool version and policy reference.
Evidence/tracking-only carriers are not independently tested joint source trees.
Use the deterministic Git setup below before Docker builds, including when starting
from a stacked evidence PR whose base does not contain the current-main union.
Runtime source manifest SHA-256:
`f8014b2e9529563a2e824528c96bd61eb0d511d34a757af298b12265a47f2bbb`.
The manifest hashes sorted paths relative to `src/`, NUL, file hash and newline;
the host, current mounted HTTP helper source and rebuilt running API matched.
HTTP helper SHA-256: `ae55d8a4d6fa802ff3793697e567b7d2a4766e98595fce25d617bf44b60069b6`.
Terminal helper SHA-256: `483aceb37dfabc82d9e294f3c86641c1ade65cb20a86bf400d829acdbb135dd6`.
Browser artifacts record served UI SHA-256
`0ccffe4504867c90dc103ea4ed97a108be14446ebfe526131c10dd1c75a45e2b`.
The allow producer requires three independently computed populated HMAC refs in
actual SQL and HTTP; raw controlled incident/run/task IDs are not emitted.

Full checks used the previously verified25b48 dependency image with current
`src/`, `tests/`, `public/`, `docs/` and `.env.example` mounted read-only;
Ruff cache used writable`/tmp`. Runtime/API/web were rebuilt from runtime source
`5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288`, identical to the tested source.
The HTTP/terminal helper processes also mounted current`src/` read-only. No image
label or environment revision alone is treated as proof of executable source.
The Docker reproduction below rebuilds the exact tested tree instead of reusing
that dependency image. This is not an own-head execution claim for earlier units.
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
  suite on the integrated API/UI:14 passed in18.3s.
- Prior all-null correlation assertion failed; refreshed helper requires populated
  incident/run/task HMAC refs and passed actual producer/SQL checks. Producer
  statuses200/403/401/422/503 persist one row; append-failure503 persists zero.
- Fresh full Python and prechecks: 1613 passed,1 skipped in315.38s;
  Ruff/format/lock/import boundaries/mypy and Alembic check passed. The skip is
  the opt-in live OpenRouter case..
- Fresh terminal boundary and SQL capture: 13 passed in10.29s; actual helper
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
  Canonical detail UUID validation rejects noncanonical forms outside the valid legacy language. The request UUID filter now rejects compact, braced and URN spellings before parsing, with one validation terminal row; canonical uppercase and authentication/grant ordering remain covered.
- Exact-credential/private-marker artifact scans passed; real screenshots are
  manually inspected. Hosted CI, human acceptance and merge remain separate gates;
  no live-provider, killed-DB or offline demonstration is inferred.

Native path uniqueness failed before the fix (1 failed in4.63s) and now passes;
actual running OpenAPI has exactly one canonical`id` path parameter. Default-contract
checks failed2/4 before activating2.7; scoped4GREEN8.64s preserves explicit overrides.
Real persisted out-of-snapshot operations failed3/13 before the local projection
schema. Parent scoped16GREEN12.75s includes runtime HTTP/OpenAPI/default metadata.
The actual current API's complete list envelope and detail validate against the
advertised local schemas; raw`issue-25-runtime-openapi.json` is unmodified HTTP output.
Historical full runtimee0 run had1609pass/1skip/1fail399.66s: usage publication
pinned2.6. The existing scenario's version/URN expectations were adapted to2.7
without weakening selector/security/schema/inventory assertions (2GREEN5.77s),
then the exact descendant full suite passed. No failed run is a fullGREEN.
Initial scoped root format stopped at cache permission before pytest; cache-only
`/tmp` correction passed. Worker first lint failed before formatting; not a pass.

Post-review checks rejected a valid list envelope for detail reads and mutation
probes before classifying row counts. Runtime OpenAPI now describes the released
filters/path/bearer/success/error/governed scope. Digit-leading compact, braced and
URN UUID forms return422 with one validation terminal; valid legacy compact IDs
retain authorized404 lookup. The initial full run had1606pass/1skip/1fail because
the existing governed-operation inventory lacked the two newly documented routes;
its assertions were preserved and the inventory adapted before the full GREEN.
Old8f51/first25b48 build jobs were interrupted(exit130), not counted as passes.

## Environment and safe reproduction
Host Git preparation is mandatory before any Docker command below. These are
repository setup operations, not host test/tool execution. The immutable tested
commit is an ancestor of the published final integration branch; no PR head or
floating main is substituted. From the repository, fetch and select it explicitly:

```console
git fetch https://github.com/creep1ng/sre-agent.git codex/issue-25-final-integration
git worktree add --detach /tmp/issue25-proof-5ac4eae 5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288
cd /tmp/issue25-proof-5ac4eae
git rev-parse HEAD
```

Require exactly`5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288` before preparing ignored configuration.
Do not copy an environment file containing someone else's credentials.

Git/Docker host; Python3.12.14, PostgreSQL17.4 pinned digest and Playwright1.63.0
images/lockfiles from the tested source. Prepare ignored mode600 `.env.worktree`
from `.env.example`: DB `audit25_closure`, user `sre_agent`, URL host `db`, fresh
synthetic keys/HMAC, `lab/model` + `lab`, no external keys, contract2.7.0,
build revision5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288 (the exact tested and deployed source). Never print/source/upload this file.
Use a fresh Compose project; choose an unused `ISSUE25_EVIDENCE_SUBNET` when needed.
Existing services only; combine the no-host-port overlay with the small IPAM overlay.
The terminal helper resets only disposable `python_checks`, never the evidence DB.

```sh
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml up -d --build web
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks run --build --rm python-checks
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/audit-events.spec.js
docker run --rm --network audit25-closure_runtime --env-file .env.worktree audit25-closure-python-checks python scripts/verify_issue25_audit.py > docs/evidence/issue-25-audit-http.json
docker run --rm --network audit25-closure_runtime audit25-closure-python-checks python -c 'import httpx; r=httpx.get("http://api:8000/openapi.json"); r.raise_for_status(); print(r.text,end="")' > docs/evidence/issue-25-runtime-openapi.json
docker compose --env-file .env.worktree -p audit25-closure -f compose.yaml -f compose.e2e.yaml -f compose.issue25-evidence.yaml --profile checks run --rm python-checks sh -c 'pytest -q tests/test_audit_read_terminal_boundary.py && python scripts/capture_issue25_audit_terminal.py'
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_audit.mjs:/e2e/capture.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/scripts/capture_issue25_correlation.mjs:/e2e/capture.mjs:ro" -v "$PWD/public/admin/audit-events.js:/candidate/audit-events.js:ro" -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e node /e2e/capture.mjs
```

## Native schema behavior reproduction
The following runs the independently observed complete-envelope check against the
rebuilt API after the producer helper. It reads only the synthetic allow request;
credentials come from the ignored environment and are never printed.

```sh
docker run --rm -i --network audit25-closure_runtime --env-file .env.worktree -v "$PWD/docs/evidence:/evidence:ro" audit25-closure-python-checks python - <<'PY'
import json, os
import httpx
from jsonschema import Draft202012Validator, FormatChecker
with open('/evidence/issue-25-audit-http.json') as f:
    evidence=json.load(f)
request_id=next(case['request_id'] for case in evidence['cases'] if case['name']=='allow')
with httpx.Client(base_url='http://api:8000', headers={'Authorization':'Bearer '+os.environ['ADMIN_HUMAN_API_KEY']}) as client:
    document=client.get('/openapi.json').json()
    assert document['info']['x-sre-agent-build-revision']=='5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288'
    assert document['info']['x-sre-agent-contract-version']=='2.7.0'
    listing=document['paths']['/v1/audit-events']['get']
    detail=document['paths']['/v1/audit-events/{id}']['get']
    params=detail['parameters']; assert len(params)==1 and params[0]['name']=='id' and params[0]['in']=='path'
    list_schema=listing['responses']['200']['content']['application/json']['schema']
    detail_schema=detail['responses']['200']['content']['application/json']['schema']
    assert list_schema['properties']['items']['items']==detail_schema
    assert detail_schema['$id']=='urn:sre-agent:runtime-schema:audit-event-metadata'
    assert len(detail_schema['properties']['operation']['enum'])==34
    response=client.get('/v1/audit-events',params={'request_id':request_id})
    assert response.status_code==200
    payload=response.json(); Draft202012Validator(list_schema,format_checker=FormatChecker()).validate(payload)
    assert len(payload['items'])==1
    response=client.get('/v1/audit-events/'+payload['items'][0]['event_id'])
    assert response.status_code==200
    Draft202012Validator(detail_schema,format_checker=FormatChecker()).validate(response.json())
    assert response.json()==payload['items'][0]
print('Actual current API: contract2.7/source5ac4eae, unique path, 34-operation local schema; complete list and detail validate.')
PY
```

## Detail error recovery screenshot
`issue-25-detail-recovery.png` is an actual Chromium screenshot at the end of the
existing mock journey: detailA404/503 survives list refresh, then detailB200 clears
the retained banner. It is not a connected API claim. The container derives only
screenshot/output settings from the committed production config; traces remain off
and the test/source files are unchanged. The focused journey passed in3.1s.

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

## Latest request-filter and navigation review
PR518 exact7fc findings4209292491/4209292475 were reproduced before correction.
Authorized compact/braced/URN request filters returned200 before the syntax check
(3 failed,26 passed); scoped corrected HTTP/OpenAPI/terminal suite passed29 in17.78s.
Canonical uppercase UUIDs still match; authentication401 and authorization403
still precede query validation. Each invalid authorized filter persists exactly
one validation terminal row; no automatic FastAPI validation bypass was introduced.
Navigation failed first at the disabled Consumption Audit entry (1 failed,12 passed),
then at the disabled Model aliases combined entry (1 failed). Existing same-origin
Model aliases → Consumption → Audit events links now work. Browser journeys verify
fresh empty credentials and no marker in URLs/local/session storage; no new layout
or credential persistence. The fresh parent rebuilt-source run passed14 in18.3s.
An earlier parent run had13pass/1fail19.5s solely because its screenshot output mount
was not writable (EACCES); the same source rerun used a writable temporary capture
mount, and the resulting actual screenshot was copied locally. No failed run counts
as a pass. Full-check start manifest and committed source/test/public bytes matched;
ancestry-only carrier32ab657 introduces no runtime/test/config changes.

`issue-25-audit-navigation.png` is the actual idle page reached through the complete
navigation journey, not a generated capture. The screenshot alone does not prove
links or absence of credential persistence; the behavioral journey does.
Reproduce the screenshot with host UID, writable container output and traces off:

```sh
docker run --rm --user "$(id -u):$(id -g)" --network audit25-closure_runtime --env-file .env.worktree -e AUDIT_NAV_SCREENSHOT=/evidence/issue-25-audit-navigation.png -v "$PWD/docs/evidence:/evidence" audit25-closure-e2e sh -c 'node --input-type=module -e '\''import config from "./playwright.production.config.js"; import {writeFileSync} from "node:fs"; config.outputDir="/tmp/audit-navigation"; config.testDir="/e2e/tests/browser"; writeFileSync("/tmp/issue25-navigation.config.mjs", "export default "+JSON.stringify(config));'\'' && npx playwright test --config=/tmp/issue25-navigation.config.mjs -g "discovers Audit events through the existing control-plane navigation"'
```

## Technical acceptance
I explicitly accept the five requested closure corrections on exact joint source
`5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288`, including the later canonical request-filter and product-navigation fixes, based on the complete Docker checks, actual HTTP/SQL persistence,
source-matched inspected captures and native runtime OpenAPI/schema verification.
Earlier13fc/791/e1847/a592 acceptance is qualified by the subsequently corrected findings;
its historical checks are not inflated into current proof. The runtime-local schema
is an explicit implementation extension, not a claim that the frozen2.7 operation
enum covers every persisted event. No operations are hidden or rewritten.
CA1 covers bounded filtering and truthful truncation; stable pagination remains
explicitly deferred to#470. This is local technical acceptance, not independent
human acceptance, hosted CI or merge approval. Fresh exact-head GitHub Codex review,
all hosted checks and human freshness acceptance remain pending. User's previous
receipt covered onlyee827/sourcea592 with those conditions; it does not transfer.
Final atomic integration alone has the user-approved size exception; every fresh
correction remains at most400 changed lines. No protection or review bypass.
Rollback: revert bounded runtime/UI corrections; immutable releases untouched.
Sanitized: yes. Controlled metadata only, no raw producer content or credentials.
