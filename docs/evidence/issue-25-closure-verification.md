# Issue 25 integrated closure-gap verification

> **Latest tested/deployed source (2026-10-07):** `a9841a2e7101bcc125874a6a3e167174b996230d`,
> based on current main `9d6ed3da8f22132561635de9a429989d21773724`. At verification
> time, carrier `88604b8cd7b8758e86572116346ee6f4066d195e` was local ancestry-only
> and unpublished; it was not itself the tested/deployed source. The API build
> revision declares `a9841a2…`; independent
> host/API/helper source identity SHA-256 is
> `75afe467ad1de907877ef705fe2cfd1a2d7d3eab7123928fecd201936ba0f59d`; served
> `public/admin/audit-events.js` SHA-256 is
> `0ccffe4504867c90dc103ea4ed97a108be14446ebfe526131c10dd1c75a45e2b`.
> The preceding `731ec673…` verification is an interim candidate, superseded by
> this exact source. Earlier `5ac4eaeb…` paragraphs are retained historical evidence.
> The current proof and remaining delivery gates are recorded first here.

Select the exact source tree directly, not a PR head or floating branch:

```console
git worktree add --detach /tmp/issue25-proof-a984 a9841a2e7101bcc125874a6a3e167174b996230d
cd /tmp/issue25-proof-a984
test "$(git rev-parse HEAD)" = a9841a2e7101bcc125874a6a3e167174b996230d
```

## Current exact-candidate verification

- Full Python checks on the current source: **1664 passed, 1 opt-in live-OpenRouter
  skip** in 448.74s; prechecks and Alembic checks passed.
- T41 GET-body guard had failure-first Docker RED (**18 failed, 62 passed** in
  31.47s) then GREEN (**80 passed** in 30.37s); Ruff and format passed. It drains
  request-stream chunks without buffering, parsing or logging body data. Valid
  filters/IDs and authentication/authorization ordering remain covered; bodyless
  reads succeed, while authenticated/authorized nonempty bodies return governed
  422 with a subjectless validation terminal.
- Prior scoped audit HTTP/OpenAPI/terminal-boundary suite after T37/T38 and before
  T41: **32 passed** on the pre-T41 candidate (not current-source evidence for
  `a9841a2e7101bcc125874a6a3e167174b996230d`) in 18.34s. The pre-fix
  failure-first run had 4 failures and 28 passes in 51.58s:
  persisted uppercase UUID detail returned 404, and each of the three tested detail
  content parameters returned 200 instead of 422. A preauthored successful-detail
  helper incorrectly expected a response `request_id`; successful detail does not
  expose it. That existing scenario was corrected to compare SQL terminal-row IDs
  before/after and assert expected metadata. No new scenario was added after code.
- Audit browser suite against the rebuilt candidate: **14 passed** in 17.6s.
  This includes no-sensitive-content assertions before Apply and after Apply,
  retained 404/503 detail errors, truncation disclosure, and mocked read-error
  behavior (stale rows/details cleared and error visible). The connected fault is
  independently captured below.
- Original loopback static browser suite: **76 passed, 60 skipped** in about 2.1m.
  Nine current PNGs were manually inspected. Fourteen current text artifacts were
  scanned: private environment values and synthetic credential/marker strings were
  absent. A first default-container UID scan hit `PermissionError`; a host-UID rerun
  passed without changing the mode-600 environment file or weakening permissions.
- Fresh terminal audit checks: **13 passed** in 7.46s and the helper emitted 11
  actual SQL-backed JSONL rows. Separate current detail and time-filter captures
  produced five and twelve actual SQL-terminal rows respectively, one per request.
  `issue-25-body-boundary.jsonl` contains fourteen additional T41 actual rows:
  for list and detail, four nonempty body forms returned422 with one subjectless
  validation terminal each; anonymous body requests returned401, restricted ones
  returned403, and bodyless admin reads returned200. The body was not retained or
  echoed. A separate fresh detail-boundary helper produced five
  actual rows: uppercase persisted UUID detail 200 plus `content`, `raw_content`,
  `redacted_content`, and `include_content` each 422, exactly one terminal row per
  request. It verified no content and no subject evidence on validation terminals.
  An initial SQL-correlation key lookup failed; the reader was corrected and the
  five-row capture rerun successfully. The corrected proof is
  `issue-25-detail-boundary.jsonl`.
- Connected query-fault proof is HTTP 200 → 503; previous UI rows/details are removed,
  the error remains visible, and the disposable table was restored (`t|t`). It
  clears one previous row/detail (1/1→0/0). Navigation and later-detail recovery
  journeys passed once each (4.9s and 5.1s). The
  latest source/helper/runtime hashes agree; no stale image or parent screenshot is
  attributed to this candidate.
- Fifteen current text artifacts passed private-value and synthetic-marker scans;
  all nine current screenshots were manually inspected. The old hosted static job
  112951192298 failed while installing Chromium dependencies from an apt mirror
  and timed out at 10m15 **before tests ran**. Its quality gate failed and its
  Compose/production-browser jobs were skipped; this is an infrastructure failure,
  not a product test failure, and is not reported as an all-green hosted run.

### RFC3339 review continuation and reproducible current proof

T40 follows exact1be80 Codex finding4210324797. Python's ISO parser accepts basic
and week dates and other spellings beyond [RFC3339 §5.6](https://www.rfc-editor.org/rfc/rfc3339#section-5.6).
The preauthored HTTP/SQL suite covers24 malformed from/to combinations with a valid
`decision` filter and4 legal UTC/offset/fraction/lowercase t/z forms. Final pre-source
RED:9 failed/51 passed24.02s; corrected suite60 passed27.35s after the86-line fix,
Ruff/format passed. An earlier pre-source helper overgeneralized no-subject validation
rules to authorized404 (10 failures); it was corrected before the implementation.
Syntax is checked before calendar conversion, preserving auth/grant ordering and
one no-content/no-subject validation terminal for invalid authorized requests.
The existing Python datetime leap-second limitation is unchanged, not newly supported.
Current-source proof:12 JSONL records in `issue-25-time-boundary.jsonl`,
8 malformed HTTP422 and4 legal HTTP200, each with exactly one safe terminal row.
Initial detail-delta capture overlapped connected browser read writers and correctly
failed its exact-one assertion; the temporary partial output was rejected and all
five detail/12 time cases rerun sequentially. Serialize these SQL-delta probes and
connected captures; no artifacts were manually repaired. Navigation1/5.0s and
mock detail recovery1/5.6s captures were refreshed after the restored real fault.

Run this exact sanitized time-filter probe against the isolated running stack:

```sh
docker run --rm -i --network audit25-closure_runtime --env-file .env.worktree \
  -v "$PWD/src:/app/src:ro" audit25-closure-python-checks python - \
  > docs/evidence/issue-25-time-boundary.jsonl <<'PY'
import json, os
from urllib.parse import urlsplit
import httpx, psycopg
from sre_agent.settings import Settings
settings=Settings.from_environment({k:v for k,v in os.environ.items() if not k.startswith('OPENROUTER')})
target=urlsplit(settings.database_url)
assert target.hostname=='db' and target.path=='/audit25_closure'
query="SELECT event_id::text, to_jsonb(a) FROM audit_events a WHERE operation='audit.project' AND action='read_metadata'"
cases=[(field+'_'+str(i),{'decision':'deny',field:value},422,'validation') for field in ('from','to') for i,value in enumerate(('20260920T000000Z','2026-W38-7T00:00:00Z','2026-09-20T00:00:00+00:60','2026-09-20T00:00:00,1Z'))]
cases += [(name,{'decision':'deny','from':start,'to':end},200,'authorization') for name,start,end in (('utc','2026-09-20T00:00:00Z','2026-09-21T00:00:00Z'),('offset','2026-09-20T00:00:00-04:00','2026-09-21T00:00:00+02:00'),('fraction','2026-09-20T00:00:00.123Z','2026-09-21T00:00:00.123456Z'),('lowercase','2026-09-20t00:00:00z','2026-09-21t00:00:00z'))]
with psycopg.connect(settings.database_url) as db, httpx.Client(base_url='http://api:8000',headers={'Authorization':'Bearer '+os.environ['ADMIN_HUMAN_API_KEY']}) as client:
    assert client.get('/openapi.json').json()['info']['x-sre-agent-build-revision']=='a9841a2e7101bcc125874a6a3e167174b996230d'
    for name,params,expected,stage in cases:
        before={key for key,_ in db.execute(query).fetchall()}
        response=client.get('/v1/audit-events',params=params)
        assert response.status_code==expected
        records=dict(db.execute(query).fetchall()); added=set(records)-before
        assert len(added)==1
        row=records[next(iter(added))]
        assert row['response_status']==expected and row['stage']==stage
        assert row['content_state']=='absent' and row['redacted_content'] is None
        subject_present=any(row.get(k) is not None for k in ('identity','resource','policy_decision'))
        assert subject_present==(expected==200)
        if expected==200:
            assert isinstance(response.json()['items'],list)
        else:
            assert response.json()['error']['code']=='validation_error' and 'items' not in response.json()
        print(json.dumps({'case':name,'filters':params,'http_status':response.status_code,'new_terminal_rows':len(added),'terminal_event_id':row['event_id'],'terminal_request_id':row['correlation']['request_id'],'terminal_status':row['response_status'],'terminal_stage':row['stage'],'terminal_outcome':row['outcome'],'content_state':row['content_state'],'subject_present':subject_present},sort_keys=True))
PY
```

### Reproduce the final detail-terminal capture

On the isolated synthetic Compose stack described below, after the producer HTTP
helper has written `issue-25-audit-http.json`, run the following exact helper
through Docker stdin in the existing Python checks image. It refuses any database other than `db` /
`audit25_closure`, asserts API build revision `a9841a2…`, compares SQL terminal
row IDs before and after every request, and prints only sanitized response and
terminal metadata:

```sh
docker run --rm -i --network audit25-closure_runtime --env-file .env.worktree \
  -v "$PWD/docs/evidence:/evidence:ro" audit25-closure-python-checks python - \
  > docs/evidence/issue-25-detail-boundary.jsonl <<'PY'
import json, os
from pathlib import Path
from urllib.parse import urlsplit
import httpx, psycopg
from sre_agent.settings import Settings
settings=Settings.from_environment({k:v for k,v in os.environ.items() if not k.startswith('OPENROUTER')})
target=urlsplit(settings.database_url)
assert target.hostname=='db' and target.path=='/audit25_closure'
producer=json.loads(Path('/evidence/issue-25-audit-http.json').read_text())
event_id=next(c['sql']['event_id'] for c in producer['cases'] if c['name']=='allow')
assert event_id.upper()!=event_id
query="SELECT event_id::text, to_jsonb(a) FROM audit_events a WHERE operation='audit.project' AND action='read_metadata'"
with psycopg.connect(settings.database_url) as db, httpx.Client(base_url='http://api:8000',headers={'Authorization':'Bearer '+os.environ['ADMIN_HUMAN_API_KEY']}) as client:
    assert client.get('/openapi.json').json()['info']['x-sre-agent-build-revision']=='a9841a2e7101bcc125874a6a3e167174b996230d'
    for name,path,params,expected,stage in [('uppercase_uuid_detail',event_id.upper(),{},200,'authorization')]+[(key,event_id,{key:'true'},422,'validation') for key in ('content','raw_content','redacted_content','include_content')]:
        before={key for key,_ in db.execute(query).fetchall()}
        response=client.get('/v1/audit-events/'+path,params=params)
        assert response.status_code==expected
        records=dict(db.execute(query).fetchall())
        added=set(records)-before
        assert len(added)==1
        row=records[next(iter(added))]
        assert row['response_status']==expected and row['stage']==stage
        assert row['content_state']=='absent' and row['redacted_content'] is None
        subject_present=any(row.get(k) is not None for k in ('identity','resource','policy_decision'))
        assert subject_present == (expected==200)
        body=response.json()
        if expected==200:
            assert body['event_id']==event_id and 'redacted_content' not in body
        else:
            assert body['error']['code']=='validation_error'
            assert 'items' not in body and 'event_id' not in body
        print(json.dumps({'case':name,'http_status':response.status_code,'returned_event_id':body.get('event_id'),'new_terminal_rows':len(added),'terminal_event_id':row['event_id'],'terminal_request_id':row['correlation']['request_id'],'terminal_status':row['response_status'],'terminal_stage':row['stage'],'terminal_outcome':row['outcome'],'content_state':row['content_state'],'subject_present':subject_present},sort_keys=True))
PY
```

### Reproduce the actual GET-body/terminal capture

This exact stdin helper was run against API build `a9841a2e…` after the producer
capture. It exercises list and detail with four nonempty bodies (raw JSON, `{}`,
JSON `null`, and non-JSON bytes), then anonymous, restricted, and bodyless-admin
requests. It compares SQL audit-event IDs before/after each request and requires
exactly one safe terminal row. The evidence directory is mounted read-only inside
the container; stdout is redirected to the host evidence file. Body data is never
logged or persisted in the evidence.

```sh
docker run --rm -i --network audit25-closure_runtime --env-file .env.worktree \
  -v "$PWD/src:/app/src:ro" -v "$PWD/docs/evidence:/evidence:ro" \
  audit25-closure-python-checks python - \
  > docs/evidence/issue-25-body-boundary.jsonl <<'PY'
import json, os
from pathlib import Path
from urllib.parse import urlsplit
import httpx, psycopg
from sre_agent.settings import Settings
settings=Settings.from_environment({k:v for k,v in os.environ.items() if not k.startswith('OPENROUTER')})
target=urlsplit(settings.database_url)
assert target.hostname=='db' and target.path=='/audit25_closure'
producer=json.loads(Path('/evidence/issue-25-audit-http.json').read_text())
event_id=next(c['sql']['event_id'] for c in producer['cases'] if c['name']=='allow')
query="SELECT event_id::text, to_jsonb(a) FROM audit_events a WHERE operation='audit.project' AND action='read_metadata'"
with psycopg.connect(settings.database_url) as db, httpx.Client(base_url='http://api:8000') as client:
    assert client.get('/openapi.json').json()['info']['x-sre-agent-build-revision']=='a9841a2e7101bcc125874a6a3e167174b996230d'
    for target_name,path in [('list','/v1/audit-events?decision=deny'),('detail','/v1/audit-events/'+event_id)]:
        admin={'Authorization':'Bearer '+os.environ['ADMIN_HUMAN_API_KEY']}
        restricted={'Authorization':'Bearer '+os.environ['RESTRICTED_HARNESS_API_KEY']}
        cases=[(name,body,admin,422,'validation') for name,body in [('raw_json',b'{"raw_content":true}'),('empty_object',b'{}'),('null_json',b'null'),('non_json',b'body')]]
        cases += [('anonymous',b'{"raw_content":true}',{},401,'authentication'),('restricted',b'{"raw_content":true}',restricted,403,'authorization'),('bodyless',b'',admin,200,'authorization')]
        for name,body,headers,expected,stage in cases:
            before={key for key,_ in db.execute(query).fetchall()}
            response=client.request('GET',path,content=body,headers={**headers,'Content-Type':'application/octet-stream' if name=='non_json' else 'application/json'})
            assert response.status_code==expected
            records=dict(db.execute(query).fetchall()); added=set(records)-before
            assert len(added)==1
            row=records[next(iter(added))]
            assert row['response_status']==expected and row['stage']==stage
            assert row['content_state']=='absent' and row['redacted_content'] is None
            subject_present=any(row.get(k) is not None for k in ('identity','resource','policy_decision'))
            assert subject_present==(expected in (200,403))
            if expected==422:
                assert response.json()['error']['code']=='validation_error' and 'items' not in response.json() and 'event_id' not in response.json()
            print(json.dumps({'case':target_name+'_'+name,'http_status':response.status_code,'new_terminal_rows':len(added),'terminal_event_id':row['event_id'],'terminal_request_id':row['correlation']['request_id'],'terminal_status':row['response_status'],'terminal_stage':row['stage'],'terminal_outcome':row['outcome'],'content_state':row['content_state'],'subject_present':subject_present},sort_keys=True))
PY
```

### Reproduce CI-equivalent static-browser coverage

This is not the API/browser integration suite: it serves the committed static
`public/` files over loopback from the existing Python checks image, mounts current
browser tests/config read-only, and places Playwright in the same network namespace
as the server so the origin is `http://127.0.0.1:4173`. It does not disable CSP,
change browser security settings, stub `crypto.randomUUID`, or publish host ports.
Run after the isolated Compose network exists:

```sh
docker run --rm -d --name issue25-static-http --network audit25-closure_runtime \
  -v "$PWD/index.html:/site/index.html:ro" -v "$PWD/palette.css:/site/palette.css:ro" \
  -v "$PWD/public:/site/public:ro" -v "$PWD/styles:/site/styles:ro" \
  -v "$PWD/scripts/showcase.js:/site/scripts/showcase.js:ro" --workdir /site \
  audit25-closure-python-checks python -m http.server 4173 --bind 0.0.0.0
docker run --rm --network container:issue25-static-http \
  -e PLAYWRIGHT_PRODUCTION_TOPOLOGY=0 \
  -v "$PWD/tests/browser:/e2e/tests/browser:ro" \
  -v "$PWD/playwright.config.js:/e2e/playwright.config.js:ro" \
  audit25-closure-e2e sh -c 'node --input-type=module -e '\''import config from "./playwright.config.js"; import {writeFileSync} from "node:fs"; delete config.webServer; config.use.screenshot="off"; config.use.trace="off"; config.outputDir="/tmp/static-results"; config.testDir="/e2e/tests/browser"; config.reporter=[["line"]]; writeFileSync("/tmp/static.config.mjs", "export default "+JSON.stringify(config));'\''; npx playwright test --config=/tmp/static.config.mjs'
docker stop issue25-static-http
```

Earlier NGINX-based selection (71 passed/60 skipped/3 failed) and non-loopback
HTTP selection (73 passed/60 skipped/1 failed) were not CI-equivalent: the former
changed CSP and the latter was a non-secure browser origin without
`crypto.randomUUID`. They are disclosed, not counted as successful verification or
fixed by weakening tests. The loopback topology above reproduces the observed CI-equivalent run. Stop the
scoped server even if Playwright fails; the observed parent run used an EXIT cleanup trap.

Exact previous carrier1be80 review5446408317 found the RFC3339 filter gap;
its hosted checks subsequently all passed, but that does not erase the finding.
T40 corrects the gap in this new source. Previous8c/source5ac human acceptance
remains conditional and qualified; it does not transfer to this new candidate.
Fresh exact-final-head review/ALL checks and independent human freshness are gates.

## Historical prior candidate and scope (not latest evidence)
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
| CA3 no content | Browser sensitive-marker checks before Apply while detail is open and after Apply; forbidden parameters + valid filter reject422. T41 nonempty GET bodies on list/detail reject422 with subjectless validation terminals, while bodyless reads and auth/grant ordering are preserved. |
| CA4 no invented consumption | Existing metadata-only projection and browser checks; no tokens/cost computation added. |
| CA5 authorization/outage | HTTP401/403 no partial items; query-only fault after authenticated/authorized lookup persists503. Connected DB fault clears prior UI rows/details and displays503. |
| CA6 durable terminal/release gate | Actual per-request SQL deltas for read200/401/403/404/422/503, including 14 T41 list/detail request-body boundary records. Append failure returns503 and zero rows; no-op/double-append mutations are rejected by the capture probe. |

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

## Earlier verification history (superseded by the exact source above)
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
repository setup operations, not host test/tool execution. At the time this
evidence was captured, the exact tested source commit was local while the carrier
was unpublished. After publication, acquire it from the integration branch and
select the exact tested source rather than running the carrier/branch head:

```console
git fetch https://github.com/creep1ng/sre-agent.git codex/issue-25-final-integration
git worktree add --detach /tmp/issue25-proof-a984 a9841a2e7101bcc125874a6a3e167174b996230d
cd /tmp/issue25-proof-a984
git rev-parse HEAD
```

Require exactly `a9841a2e7101bcc125874a6a3e167174b996230d` before preparing ignored configuration.
Do not copy an environment file containing someone else's credentials.

Git/Docker host; Python3.12.14, PostgreSQL17.4 pinned digest and Playwright1.63.0
images/lockfiles from the tested source. Prepare ignored mode600 `.env.worktree`
from `.env.example`: DB `audit25_closure`, user `sre_agent`, URL host `db`, fresh
synthetic keys/HMAC, `lab/model` + `lab`, no external keys, contract2.7.0,
build revision `a9841a2e7101bcc125874a6a3e167174b996230d` (the exact tested and deployed source). Never print/source/upload this file.
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
    assert document['info']['x-sre-agent-build-revision']=='a9841a2e7101bcc125874a6a3e167174b996230d'
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
print('Actual current API: contract2.7/sourcea9841a2, unique path, 34-operation local schema; complete list and detail validate.')
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

## Earlier request-filter/navigation review (historical; refreshed results are above)
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
or credential persistence. The earlier parent rebuilt-source run passed14 in18.3s;
current navigation and detail-recovery checks are recorded above.
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

## Technical acceptance and remaining delivery gates
The technical verdict accepts criteria on exact source
`a9841a2e7101bcc125874a6a3e167174b996230d`, including T37/T38/T40/T41, based on
the current full Python/prechecks, browser, static, terminal SQL, connected
query-fault and source-matched evidence listed above. This is local technical
acceptance only: the source is not the current remote PR518 head, and there is no
fresh exact-head Codex review, fresh all-hosted-checks PASS, or independent human
freshness receipt. PR518 finding4210579828 (ignored nonempty GET bodies) was fixed
and verified locally by T41; it still requires a new review of the published exact
head. Those gates remain required before integration; no prior conditional receipt
transfers.

The earlier local technical acceptance covered previous exact joint source
`5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288`. Earlier13fc/791/e1847/a592 acceptance
is qualified by subsequently corrected findings; historical checks are not
inflated into current proof. The runtime-local schema is an explicit
implementation extension, not a claim that the frozen2.7 operation enum covers
every persisted event. No operations are hidden or rewritten.
CA1 covers bounded filtering and truthful truncation; stable pagination remains
explicitly deferred to#470. The current technical acceptance is not independent
human acceptance, hosted CI or merge approval. User's previous receipt covered
only8c06/source5ac with those conditions; new detail findings and the hosted static failure qualify it, and it does not transfer.
Final atomic integration alone has the user-approved size exception; every fresh
correction remains at most400 changed lines. No protection or review bypass.
Rollback: revert bounded runtime/UI corrections; immutable releases untouched.
Sanitized: yes. Controlled metadata only, no raw producer content or credentials.
