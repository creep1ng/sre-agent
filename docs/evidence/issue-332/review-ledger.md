# Issue #332 review-resolution ledger — R6 draft

> Private R6 ledger for parent publication/readback. Parent live refresh reports both PRs DRAFT. PR #382 has one unresolved, not-outdated bot review thread; PR #422 has no full reviews or threads. Reviewer `papiarcacamilo` was requested; no approval.

Current finding: [PR #382 review comment 4140754411](https://github.com/creep1ng/sre-agent/pull/382#discussion_r4140754411), review `5361406803`, original reviewed commit `1b70672629d0c65b393fc6d31022f6a04207b615`, current frozen F `9fb91f725e5c292346b930e3dae787cc05fe1a71`, thread `PRRT_kwDOTwEEZc6nYg5C`. The REST comment commit_id now follows F; retain the originalCommit/full-review identity as the finding’s reviewed source. It remains unresolved: F and M source correction/producers are verified, but parent must publish/readback evidence and post the response before any closure claim.


The maintainer explicitly approved scoped size exceptions for the two coherent required units in
the parent conversation on 2026-09-29, with complete tests/docs and Jev deferred. That scoped
authorization is not a GitHub review approval, approval label or permission to merge.

| Finding / origin | Reviewed → current source | CA / unit | Status | Reproduction and resolution | Remaining owner |
| --- | --- | --- | --- | --- | --- |
| Bot finding: equal manifest replay skips persisted-child verification | Original reviewed `1b70672629d0c65b393fc6d31022f6a04207b615` → frozen F `9fb91f725e5c292346b930e3dae787cc05fe1a71`; M `34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d` inherits the same owner/test bytes | CA1 / owner replay | Source correction, test proof and exact-F/M portable producer evidence verified; thread still unresolved pending publication/response | Real PostgreSQL RED: 4 committed chunk/document drift cases failed to raise collision (`4 failed, 70 passed`). Bounded fix/test source bytes shared by F/M; current independent source verification: F full1227+1 skip; M focused91, full1250+1 skip, exit0. Current F 12-observation and M 34-observation producer JSON/captures are prepared; parent evidence commit/publication remains pending. | Parent publishes actual R6 evidence, then replies/resolves only after readback; human reviewer owns acceptance |
| Current source CI | F `9fb91f725e5c292346b930e3dae787cc05fe1a71`; M `34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d` | Both | Successful | F [36673827658](https://github.com/creep1ng/sre-agent/actions/runs/36673827658) and M [36673681362](https://github.com/creep1ng/sre-agent/actions/runs/36673681362); all 8 required jobs SUCCESS, each watch exit 0 | Parent maintains live PR metadata; success is not acceptance |
| #382 conflicts with delivered-main migration / recovery inspection (no thread) | ed394a6185517c6ea0310fec214adeac07ddc676 →1b70672629d0c65b393fc6d31022f6a04207b615 | CA1 / foundation | Fixed and verified |4 passed, 66 errors with multiple heads; additive merge20260929_15;70 focused and1223 full passed; fresh migration clean | Human foundation review |
| Readiness and new fixture-reset omissions / recovery inspection (no thread) | Published foundation against main5b6109b →1b7067 | CA1 / foundation | Fixed and verified |1 failed, 28 passed, 41 errors; preserve new main usage/incident fixtures; independent full1223 passed, 1 skipped | Human foundation review |
| Unpublished retrieval migration overwrites newer usage vocabulary / recovery inspection (no thread) | Original recovered unpublished code →c37c3403c374350be676a56e9989132fdc200c8d | CA4 / retrieval | Fixed and verified | Multiple-head error, then usage failures; additive20260929_16 preserves usage.read both ways; populated upgrade/downgrade test and full lane pass | Human retrieval review |
| Authorization-store error escapes content guard / recovery inspection (no thread) | Original recovered retrieval →c37c340 | CA4 | Fixed and verified | Real credentials/grants outages produced500 before repair; test-first bounded503 handling; network credentials outage503 | Human retrieval review |
| Hardcoded prior read count and leaked dropped table / recovery inspection (no thread) | Original recovered tests →c37c340 | CA5–6 | Fixed and verified | Isolated0!=2 and later storage503 reproduced; own warm baseline/reversible faults; isolated/reordered7 passed | Human retrieval review |
| Missing distinct-principal, provenance, committed-authority and independent SQL evidence / recovery inspection (no thread) | Original incomplete proof →c37c340 | CA1–6 | Added and verified | Current real-DB HTTP suite;87 focused passed;30 network/storage observations; zero-read instrumentation explicitly [TestClient SQL-observer scope](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L475-L494) with [independent per-collection assertions](https://github.com/creep1ng/sre-agent/blob/c37c3403c374350be676a56e9989132fdc200c8d/tests/test_bok_http.py#L534-L549) | Human semantic acceptance |
| Current screenshots / historical governance failure | #382 ed394a6 → frozen F/M evidence | Evidence policy | Current actual captures prepared; publication pending | F, M and audit Chromium PNGs rendered from current JSON, visually inspected, bytes/hashes in manifest; parent binds commit before HTTPS claims | Parent publishes/readbacks |
| Historical hosted CI |1b7067 andc37c340 exact source | Both units | Historical success, not current source | Runs36660022792 and36660634684 refer to old heads only | Excluded from current claim |
| Historical portable retrieval reproduction | c37c3403c374350be676a56e9989132fdc200c8d | CA1–6 network/storage subset | Historical only | 30 observations / 22 HTTP / 20 audit rows apply only to c37. Current exact M separately records 34 observations / 22 HTTP / 20 audit rows plus four replay SQL cases | Excluded from current claim |
| Governance metadata and human review | #382 / #422 | Delivery | Pending | Bind real HTTPS evidence links, update template bodies, request eligible human reviewer; no approval/merge claimed | Parent, then human reviewer |

## Historical recovery findings at older candidates

The following rows and preparation failures describe prior recovery heads and remain history; they are not current R6 producer proof.

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

## Current exact-head proof and unresolved scope

- F: full local source suite 1227 passed + 1 intentional provider skip; producer exit 0 with 12 observations. Four child drift cases all collided without repair, restored and then intact replay no-op succeeded. Exact-head hosted CI 36673827658 all 8 jobs succeeded.
- M: focused 91 passed; full 1250 passed + 1 intentional provider skip; parent current owner+HTTP spotcheck 27 passed in 6.60s. Producer exit 0 with 34 observations, 22 HTTP outcomes, 20 persisted audit rows; the four owner replay cases are distinct. Exact-head hosted CI 36673681362 all 8 jobs succeeded.
- Current captures were rendered from saved exact-head JSON, reopened and visually checked. Current image IDs/hashes are in [provenance](provenance.json) and the manifest.
- Both PRs remain DRAFT; `papiarcacamilo` requested as reviewer, not approved. The #382 thread is unresolved/not outdated. Parent publication/readback and response remain pending; humans own acceptance/integration. Issue stays open.

See [foundation report](foundation-report.md), [retrieval report](retrieval-report.md),
[reproduction](reproduction.md) and [provenance](provenance.json). No raw exception/configuration
logs are published. No live-provider/Jev request occurred. Optional Jev remains deferred.
Foundation covers only the owner part of CA1; required retrieval completes local functional
CA1–CA6 evidence. Network runtime proof is not represented as SQL-read instrumentation; the latter
is a separately executed real-PostgreSQL TestClient observation; see the
[immutable-source CA1–CA6 mapping](retrieval-report.md#acceptance-map). The independent current-source producer runs used isolated named tmpfs projects; scoped cleanup left containers and networks absent. `down` omitted `-v`, so project-named volume metadata was intentionally retained. Parent publication and human acceptance remain pending.

No thread was resolved, label applied, PR approved, issue closed or branch merged by this worker.
