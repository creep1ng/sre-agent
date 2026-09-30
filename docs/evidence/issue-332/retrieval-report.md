# Issue332 required retrieval: real network and storage proof

**30 actual owner/SQL/network observations passed.** Both synthetic collections return scoped
lexical matches and direct chunks under different principals. Cross-identity/direct denials,
committed authority changes and real storage outages remain distinguishable from no-match.
Primary evidence kind: **controlled integration**; real FastAPI TCP plus PostgreSQL, augmented
by explicitly separate source-level TestClient SQL-observer acceptance proof.

## Acceptance matrix

| Criterion | Network/storage observation | Separate immutable-source acceptance / limitation |
| --- | --- | --- |
| CA1 | Replay/collision/empty activation plus both demo searches 200 | [Owner lifecycle](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_persistence.py#L63-L106) and [both collections searched](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L497-L534); no generic ingestion platform |
| CA2 | Exact grants; same query under other identity 403; direct IDs 403 | [Denied collection reads unchanged](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L534-L549) and [unready/unauthenticated/wrong-version zero reads](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L614-L625); SQL listener is separate from network probe |
| CA3 | Complete collection/version/document/section/index/title/source/content; direct 200 and authorized miss 404 | [Rank and stable ID tie-breaks](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L288-L310); [full search/direct provenance and authorized miss](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L509-L534) |
| CA4 | Empty 200 distinct from 401/403/404/index 503; content and credentials store failures 503 | [Authorization-store outages](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L628-L652) and [audit-storage outage suppresses content](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L681-L693) |
| CA5 | Grant/catalog changes 403; owner revocation 503; restoration 200 on next request | [Committed authority transitions](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L578-L611) and [same-query cross-identity denial](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L536-L549); no content-cache platform added |
| CA6 | Persisted operation, decision, subject-presence and content_state absent; queried phrase/fragment/key scans pass | [Per-collection SQL counts](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L517-L549) and [exact HMAC identity, operation/decision and query/fragment-free audit](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L551-L575); independent TestClient scope |

The full results include 22 HTTP observations and 20 persisted BoK audit rows; the health read and
unauthenticated request do not claim a BoK subject/decision. Authorization-store failure records
no completed subject or policy decision rather than inventing one. Sanitized audit capture:
[real PNG](retrieval-audit.png), [recorded JSON](retrieval-results.json).

The [independent SQL observer](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L475-L494) listens to actual
SQLAlchemy `before_cursor_execute` events for document/chunk SELECTs and attributes them to
collection/version bindings, independently of the service’s own counters. The linked assertions
verify allowed reads and unchanged/zero denied or unready reads against real PostgreSQL through
TestClient. The separate network producer probe does not instrument those SELECT counts.

## Independent portable reproduction

A separate verifier rebuilt this exact source and reran the portable probe against its own
FastAPI process and disposable PostgreSQL database: **30 observations, 22 HTTP outcomes and
20 persisted BoK audit rows passed; probe exit 0**. Build, guarded migration, foreground API
shutdown and scoped cleanup also exited 0. Results matched the original recorded JSON after
omitting only capture time and request IDs. All 68 runtime source/migration Python file hashes
matched the frozen checkout. The verifier observed 2167 source files and all 22 preparation
files unchanged during its run, before this reports/manifest-only polish.

| Image | Original capture build | Independent reproduction rebuild |
| --- | --- | --- |
| Runtime API | `sha256:4f33ab086d14da15df18098adc53ed2cb59398f0573954c1b0c0111d327cea38` | `sha256:9e01298484256ec314f9e2871d5d7dcd90cb7445fc85b8a9256f465cfa63edd0` |
| Checks | `sha256:4aa6186e275b6cb7d0345edbf97dc73d7e5575f39101d3be2813f49cf2cc89e6` | `sha256:ffa436d890a1a52dfd8e76fbb7ced7c4d355b9c565cadf72f9a20721e2ce3ce4` |

Rebuilt image IDs are distinct, not replacements for the original [capture provenance](provenance.json).
Recorded results, HTML, PNGs and executed scripts remain unchanged. This independent run did not
rerun foundation, the full source suite or hosted CI; those results remain separately attributed.
It adds reproducibility evidence, not human acceptance or publication/governance completion.

## Temporal contract and limitations

A new request observes authority changes committed before its authorization/content transaction.
Shared row locks hold the selected active facts through the content query. Revocation does not
retract previously delivered content. This evidence exercises sequential committed transitions,
not a concurrency stress guarantee, external corpus, or production load benchmark. Optional Jev,
vector retrieval and downstream runtime integration are outside this unit.

## Source verification and delivery scope

Writer focused87 passed, 15.31s; parent spot87 passed, 32.53s. Independent exact-source full/static
verification:1246 passed,1 skipped, 99.90s,2167 hashes/modes unchanged and28 preservation comparisons.
Fresh schema upgraded twice with no model drift. The live-provider test was skipped and not run.
Source diff versus foundation: 1448 additions + 8 deletions = 1456, 13 paths. The maintainer
explicitly approved scoped size exceptions for the two coherent required units in the parent
conversation on 2026-09-29, retaining complete tests/docs and deferring Jev. This is not a GitHub
review approval. Count evidence additions at publication.
Published migrations are byte-immutable; new20260929_16 follows20260929_15 and retains usage.read
on upgrade and downgrade, with refusal to discard persisted BoK audit evidence.

## Risks, rollback and next owner

Only use the destructive fault probe on the named owned tmpfs checks database. Every injected
rename/status change is restored in finally; no persistent demo database is used. Revert retrieval
routes/service/index/audit extension without deleting corpus data; honor audit downgrade refusal.
Parent owns artifact publication, final governance check and independent human-review request.
Chain: **#382 foundation → 📍 #422 required retrieval → human integration**. PR422 temporarily
bases on the immediate parent to keep1456-line review focused; retarget main only after a human
merges #382. This remains stacked-to-main, not a feature tracker or merge authorization.

## Identity and environment

- Tested source: `c37c3403c374350be676a56e9989132fdc200c8d`; source base: `1b70672629d0c65b393fc6d31022f6a04207b615`.
- Schema: `20260929_16`; Python3.12.14; Docker29.8.1; Compose5.5.1; runtime UID65532.
- Runtime image: `sha256:4f33ab086d14da15df18098adc53ed2cb59398f0573954c1b0c0111d327cea38`.
- Checks image: `sha256:4aa6186e275b6cb7d0345edbf97dc73d7e5575f39101d3be2813f49cf2cc89e6`.
- PostgreSQL: `postgres:17.4-alpine@sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5`; private project network, tmpfs database, no DB host port.
- Lock SHA-256: `783c78b44e4ab07091d0ee1d44a693b77f1ec0fdc94f9aa3c0e212cd34dc878b`. Source was read-only during evidence work.
- Synthetic built-in corpus only; generated ephemeral credentials stayed in process memory.
  No provider/OTel/SSH/cloud traffic, secret-bearing configuration or ambient identity was used.

## Reproduce and inspect

[Container commands](reproduction.md), [portable probe](producer-probe.py),
[full recorded results](retrieval-results.json), [sanitized probe summary](retrieval-probe.txt),
[local checks excerpt](retrieval-checks.txt), [provenance](provenance.json),
[review-resolution ledger](review-ledger.md). Actual final build, guarded migration and network
probe commands exited0. Foreground API exited0 after an explicit scoped stop; owned tmpfs
project removed without `-v`. No runtime handle remains active.

## Capture

[Real browser PNG](retrieval.png) shows recorded actual network/SQL data, not a live application UI.
The capture was visually inspected for readability and sensitive content. Credentials/headers,
personal paths, raw configuration and confidential corpus content are excluded.

## Hosted CI and acceptance boundary

The parent independently confirmed all eight mandatory jobs succeeded on this exact source:
[CI run36660634684](https://github.com/creep1ng/sre-agent/actions/runs/36660634684).
Jobs: configuration-lock, checks-image, static-web, unit, contracts, compose-smoke,
production-browser and Quality gate. This is hosted functional proof, not semantic acceptance.
Governance metadata/evidence publication and independent human review remain pending.
No approval label, merge, issue closure or release is authorized by these artifacts.

## Security and video

Sanitized: yes

Deferred: media storage unavailable; screenshot evidence is mandatory.
