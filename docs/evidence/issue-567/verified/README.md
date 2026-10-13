# Issue #567 — immutable PR evidence

This directory records **full-stack verification**, not a live product UI or a
paid-provider run. The actual application/investigator uses real HTTP to a
controlled gateway in a separate process. Only that gateway writes its independent
SQLite operations ledger and counter; its model answer is deterministic/simulated.
The receiver performs no deduplication.

## Identity

- Full-stack tested SHA: `8b4316ca77637fcbed3750bfeb2121d294469b7b`.
- Main validation base: `763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`.
- Each scenario JSON repeats those full SHAs and actual environment versions.
- Source was clean at the wrapper's entry/exit. `identity.txt` records the owned
  detached container and its authoritative exit status.
- `source-tree.txt` and source/image hash records bind the proof to its code.
- Screenshot: `evidence.png`, a real native Chromium view of `runtime-sql.json`;
  no generated HTML, invented UI or substitute receipt screenshot.

## Acceptance matrix

| Criterion | Artifacts | Required observation |
| --- | --- | --- |
| 1. Confirmed external effect | success.json, success-receiver.sqlite, SQL export | Receiver counter 1, one applied operation, request/run/incident/task correlated with successful runtime receipt and one result event. |
| 2. Confirmed contractual failure | reject.json, reject-receiver.sqlite, SQL export | Sent operation explicitly rejected under controlled no-effect semantics, counter 0, confirmed_failure / governed_call_denied. |
| 3. Interrupted unknown | before_dispatch, before_effect, after_effect, before_commit JSON/SQLite and SQL export | Four real SIGKILL/restarts, pending survives reads/resume, exact replay records unknown without redispatch. Before-effect applies later while unknown remains; before-commit observes a real PostgreSQL INSERT lock wait and no partial result. |
| 4. Recovery/retry limits | All scenarios; concurrent, timeout, loss, 5xx | Read/resume/replay recover the same run with HTTP 200 and do not redispatch. Four concurrent replays still yield one operation. Timeout/lost response/5xx coexist with an effect and unknown. No external exactly-once claim. |

`pre_dispatch` separately demonstrates an unconfigured producer with zero sent
operations; it is not a failure of an already-sent operation. The controlled 403
rejection is not evidence that arbitrary real-provider 4xx/5xx means no effect.
The inspector read exported receiver SQLite and live PostgreSQL before later tests
reset the dedicated disposable DB. The SQL JSON is the observed export, not a
claim that the reused DB still contains those runs.

## Environment / reproduction

Host: Git and Docker only, with safe output/configuration preparation.
Docker client/server 29.9.0; Compose 5.6.0; PostgreSQL 17.4; Python/package versions
are recorded in every JSON. Existing pinned Dockerfiles and locked dependencies
were used. The capture uses Playwright 1.63.0. Only synthetic seed identities,
dedicated tmpfs checks DB and the internal Compose network were used.

Checkout the full tested SHA and use the Git/Docker-only
`scripts/reproduce_issue567_evidence.sh` with a **new empty absolute persistent
output directory outside the checkout**. The complete Docker commands are in
`docs/evidence/issue-567/README.md` at that SHA and in each PR body. Use
`.env.example`, never credentials; do not point TEST_DATABASE_URL at a shared DB.
The inspector must run before another suite resets fixtures. No global cleanup,
volume removal or production service is required.

## Source stack and freshness

| Unit | Head | Actual PR base | Added + deleted |
| --- | --- | --- | ---: |
| receiver/design | 7fd55afc34563059130c4a06ee3a5a96527cb026 | 763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9 | 232 |
| E2E scenarios | 3785623b6cc4d766ae34b2671356afc63aa21188 | 7fd55afc34563059130c4a06ee3a5a96527cb026 | 333 |
| evidence recipe | 8b4316ca77637fcbed3750bfeb2121d294469b7b | 3785623b6cc4d766ae34b2671356afc63aa21188 | 258 |

The receiver/design and E2E files are byte-identical at their constituent branch
heads and the full-stack tested head, as recorded in `scope-identity.txt`.
**Do not claim tests ran at the first or second branch head:** this evidence was
produced at the full-stack SHA. Each partial PR states that distinction and its
remaining scope. Scenario `base_sha` is the main validation base; a stacked PR's
Base SHA field instead identifies its actual predecessor.

Aggregate source: 823 lines. Keep the three units separate; no size exception or
single main-based 823-line acceptance PR is authorized. Merge order is receiver,
then E2E, then recipe. After each integration, the maintainer must recheck/retarget
the dependent PR's base, size and evidence freshness before proceeding.

This explicitly dedicated artifact branch is **not a fourth source PR** and is not
proposed for merge. It hosts the complete visible sanitized proof rather than
hiding files in the source diff. Immutable full-commit HTTPS links identify it.

## Review, security and limits

Source runtime, contracts, migrations, root Compose, Dockerfiles and dependencies
are unchanged. The latest source update only records publication authorization.
The initial failed environment attempts are not credited; temporary-file loss
required a persistent rerun. Hosted CI, unrelated full repository tests, real
provider/billing, product browser UI E2E and production remediation are not claimed.
See `verification.log`, `results.md` and `review.md` for observed verification.

Human acceptance remains pending. PR creation/publication does not close #567 or
CA6. No merge, issue closure, automatic retries, cancellation, reconciliation,
cross-system transaction or general exactly-once guarantee is performed/proven.

Sanitized: yes. Only synthetic correlation IDs, bounded statuses and counters,
safe query outputs, process IDs and verification/provenance records are included.
No keys, sensitive headers, prompts, model text or raw application logs.
Video: Deferred: media storage unavailable; screenshot evidence is mandatory.
