# Issue332 review-resolution ledger

Latest parent live inventory: both #382 and #422 have **no conversation comments, formal reviews,
inline comments or review threads**, including resolved/outdated threads; pagination was exhausted.
Both remain draft and mergeable at the exact source heads/bases recorded in the reports. This is
not human approval. Refresh again immediately before publication; the parent owns GitHub mutations
and review requests.
The rows below are inherited recovery findings, not invented GitHub review threads.

The maintainer explicitly approved scoped size exceptions for the two coherent required units in
the parent conversation on 2026-09-29, with complete tests/docs and Jev deferred. That scoped
authorization is not a GitHub review approval, approval label or permission to merge.

| Finding / origin | Reviewed → current source | CA / unit | Status | Reproduction and resolution | Remaining owner |
| --- | --- | --- | --- | --- | --- |
| #382 conflicts with delivered-main migration / recovery inspection (no thread) | ed394a6185517c6ea0310fec214adeac07ddc676 →1b70672629d0c65b393fc6d31022f6a04207b615 | CA1 / foundation | Fixed and verified |4 passed, 66 errors with multiple heads; additive merge20260929_15;70 focused and1223 full passed; fresh migration clean | Human foundation review |
| Readiness and new fixture-reset omissions / recovery inspection (no thread) | Published foundation against main5b6109b →1b7067 | CA1 / foundation | Fixed and verified |1 failed, 28 passed, 41 errors; preserve new main usage/incident fixtures; independent full1223 passed, 1 skipped | Human foundation review |
| Unpublished retrieval migration overwrites newer usage vocabulary / recovery inspection (no thread) | Original recovered unpublished code →c37c3403c374350be676a56e9989132fdc200c8d | CA4 / retrieval | Fixed and verified | Multiple-head error, then usage failures; additive20260929_16 preserves usage.read both ways; populated upgrade/downgrade test and full lane pass | Human retrieval review |
| Authorization-store error escapes content guard / recovery inspection (no thread) | Original recovered retrieval →c37c340 | CA4 | Fixed and verified | Real credentials/grants outages produced500 before repair; test-first bounded503 handling; network credentials outage503 | Human retrieval review |
| Hardcoded prior read count and leaked dropped table / recovery inspection (no thread) | Original recovered tests →c37c340 | CA5–6 | Fixed and verified | Isolated0!=2 and later storage503 reproduced; own warm baseline/reversible faults; isolated/reordered7 passed | Human retrieval review |
| Missing distinct-principal, provenance, committed-authority and independent SQL evidence / recovery inspection (no thread) | Original incomplete proof →c37c340 | CA1–6 | Added and verified | Current real-DB HTTP suite;87 focused passed;30 network/storage observations; zero-read instrumentation explicitly [TestClient SQL-observer scope](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L475-L494) with [independent per-collection assertions](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L534-L549) | Human semantic acceptance |
| Missing real screenshot / historical governance failure | #382 ed394a6 →current evidence bundle | Evidence policy | Prepared; publication pending | Actual Chromium PNGs of recorded real producer/SQL output, reports and commands prepared; do not claim hosted artifact existence yet | Parent binds evidence commit and publishes |
| Hosted functional CI / parent live readback |1b7067 andc37c340 exact source | Both units | Successful, not acceptance | Runs36660022792 and36660634684; all eight mandatory jobs succeeded | Parent refreshes after evidence publication |
| Independent portable retrieval reproduction | c37c3403c374350be676a56e9989132fdc200c8d | CA1–6 network/storage subset | Reproduced; not acceptance | 30 observations / 22 HTTP outcomes / 20 audit rows; build, guarded migration and probe exit 0; normalized results match original; [distinct original/rebuilt image IDs and limits](retrieval-report.md#independent-portable-reproduction) | Parent publication, then human review |
| Governance metadata and human review | #382 / #422 | Delivery | Pending | Bind real HTTPS evidence links, update template bodies, request eligible human reviewer; no approval/merge claimed | Parent, then human reviewer |

## Evidence preparation failures (not source defects)

- Initial detached clone used restrictive file permissions; non-root migration/probe could not
  read the guard (exit2), API exited1. Restored normal tracked-file read permissions without
  source/Git-mode changes and rebuilt; foundation probe then passed, 8 observations.
- Initial retrieval probe inserted an invalid dotted synthetic grant ID through SQL; the producer
  rejected its DTO and the probe could not decode the500 response. Corrected only the evidence
  fixture IDs, recreated the same owned tmpfs project, and all30 observations passed. This is not
  suppressed product RED or a new runtime fix.
- Initial sandboxed Chromium launch exited133 on a local socket permission; authorized capture
  with a fresh profile and disabled background networking/DNS succeeded. No generated capture used.

## Current proof and unresolved scope

See [foundation report](foundation-report.md), [retrieval report](retrieval-report.md),
[reproduction](reproduction.md) and [provenance](provenance.json). No raw exception/configuration
logs are published. No live-provider/Jev request occurred. Optional Jev remains deferred.
Foundation covers only the owner part of CA1; required retrieval completes local functional
CA1–CA6 evidence. Network runtime proof is not represented as SQL-read instrumentation; the latter
is a separately executed real-PostgreSQL TestClient observation; see the
[immutable-source CA1–CA6 mapping](retrieval-report.md#acceptance-matrix). The independent portable
reproduction preserved the original scripts/results/HTML/PNGs/provenance and left no owned runtime
containers or network. Publication, final governance and human acceptance remain pending.

No thread was resolved, label applied, PR approved, issue closed or branch merged by this worker.
