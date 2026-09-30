# Issue #332 — Review and delivery ledger (current snapshot)

Snapshot prepared for the current source/evidence handoff on 2026-09-30. Review threads remain reviewer-owned; “outdated” is not “resolved,” and passing tests/CI are not human acceptance.

## Source candidates and automated checks

| PR | Source head → base | Diff | Current CI | State at latest parent refresh |
| --- | --- | --- | --- | --- |
| #382 Foundation | `ea74a6e8970ff6b3cbf7ebef885fc97c5816da89` → `5b6109bd2c8100455136cf12ce91c52830833c7f` | 999 additions + 25 deletions; 1,024 lines / 29 paths | [run 36711627164](https://github.com/creep1ng/sre-agent/actions/runs/36711627164), all 8 required jobs successful | Open, draft, mergeable; reviewer `papiarcacamilo` requested |
| #422 Retrieval | `c2f064f76e42e3257a21a261fe16b035d888fc7e` → `ea74a6e8970ff6b3cbf7ebef885fc97c5816da89` | 1,570 additions + 8 deletions; 1,578 lines / 13 paths | [run 36711631324](https://github.com/creep1ng/sre-agent/actions/runs/36711631324), all 8 required jobs successful | Open, draft, mergeable; reviewer `papiarcacamilo` requested |

The >400-line diffs use the parent-authorized scoped size exception from 2026-09-29. The branches are separate source PRs; current evidence is a separate evidence-only publication candidate, not extra source PR scope. Main and the pre-existing R6/f72f evidence snapshot remain unchanged. Parent-reported Project state: a GraphQL read on 2026-09-30 at approximately 11:34 UTC showed issue #332 open and Project 8 Todo. This state is attributed to the parent’s read, not independently verified by this evidence writer. The parent owns source publication, evidence publication, metadata operations and the eventual ordered integration; this ledger does not report an approval, merge, label, or issue closure.

## Inline review threads

| PR / thread | Finding | Current thread state | Current evidence / response |
| --- | --- | --- | --- |
| #382 / [4140754411](https://github.com/creep1ng/sre-agent/pull/382#discussion_r4140754411) | R5: exact replay must inspect committed child state rather than trusting the parent manifest | Unresolved, not outdated | Current F/M producer checks cover four actual committed child drift cases; original thread remains reviewer-owned. |
| #382 / [4141380474](https://github.com/creep1ng/sre-agent/pull/382#discussion_r4141380474) | R7: partial/missing document chunks must not become activation-ready | Unresolved, outdated (not resolved) | Current exact F and M producer proves partial document stays `indexing` and activation rejects. |
| #382 / [4141380485](https://github.com/creep1ng/sre-agent/pull/382#discussion_r4141380485) | R7: activation must reject changed or missing persisted children | Unresolved, outdated (not resolved) | Current exact F and M producer proves changed and deleted chunk rejection with lifecycle unchanged and no silent repair. |
| #422 / [4141390128](https://github.com/creep1ng/sre-agent/pull/422#discussion_r4141390128) | R8: locked authorization recheck must audit the actual denial cause | Unresolved, not outdated | Current M TestClient/PostgreSQL source-test assertions distinguish principal/resource/grant causes while retaining generic 403, zero extra content reads, metadata-only audit and restored allow. This is separate from TCP rows. |

The latest review timeline’s summarized bot reviews still refer to earlier 9fb/34ce heads; they are not current acceptance. No thread is recorded as resolved and no human acceptance has been reported. PR state remains draft pending parent’s final body/governance reconciliation and reviewer/human acceptance.

## Current proof and distinctions

- [Foundation report](foundation-report.md), [Retrieval report](retrieval-report.md), [portable reproduction](reproduction.md), [current F results](results/foundation-results.json), [current M results](results/retrieval-results.json), and [R8 cause assertion summary](r8-denial-cause.json).
- F producer: 16 observations. M producer: 38 observations, including 22 HTTP outcomes and 20 persisted audit rows. The 4 activation cases and 4 replay drift cases are separate owner/SQL observations, not HTTP counts or audit rows.
- The R8 cause summary is a source-test assertion summary, not a copied serialized database event. The source test exercises committed transitions with a TestClient immediately before locked recheck; do not describe it as a TCP interleaving.
- Local exact-source checks: independent verifier F full `1234 passed, 1 intentional live-provider skip`; M configured full/static suite run by the implementation writer `1260 passed, 1 intentional live-provider skip`; focused locked-cause suite run by writer `43 passed in 17.40s`, plus an independent M focused rerun `43 passed in 15.29s`. No independent M full-suite rerun is claimed. Exact-head hosted CI above is separate from these local runs.
- The actual Chromium captures are `foundation.png`, `retrieval.png`, and `retrieval-audit.png`. The latter separates 20 TCP audit rows from R8 TestClient assertions.
- No live provider, paid service, production system, Jev, cloud, OTel, SSH, concurrent writer, administrator-write prevention, broad platform hardening, human approval or merge is claimed.
