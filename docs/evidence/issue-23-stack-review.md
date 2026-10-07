# Issue #23 triage stack review

Status: in progress; **issue #23 is not accepted**. This is a local review, not a published PR, merge authorization or human acceptance. RDD: disabled/unmanaged.

## Scope and identity

Review date: 2026-10-06 (America/Bogota). Authoritative issue: [#23](https://github.com/creep1ng/sre-agent/issues/23), OPEN, Project [midnight.agent #8](https://github.com/users/creep1ng/projects/8), Todo, Estimate 5. Latest user goal targets #23, replacing the initial #330 reference.

Fetched and inspected the exact linear, currently OPEN stack:

| PR | Current head (short display only) |
| --- | --- |
| #373 | 7990109 |
| #374 | a832ad1 |
| #380 | 33992ef |
| #389 | 8dc94a7 |
| #391 | 759fade |
| #392 | e0bb235 |
| #460 | ecad5e3 |
| #463 | 94dff87 |
| #464 | 40f181b |
| #466 | 724b868 |
| #485 | df17a07 |

Stack base: `63ebc6198a0ca5ce257f1826060bb6345d96b095`. Baseline tested head: `df17a07edb8259671763f1ba9e8cfa4e763365bf`. Original checkout: `fe6fca024fec4f89f7538dc5dc03159a99f12a2a`, preserved rather than silently rebasing this divergent stack. Local corrections use `codex/triage-23-stack-review`.

Live hosted checks were successful for all eleven PRs at inspection; this is separate from local behavior proof. The production Playwright config includes `triage.spec.js` but omits the added real recovery/persistence/403/session suites. PR #485 reproduction requires an unavailable `/tmp/seed-c3e.py`, so its commands alone are not repeatable from that commit.

## Baseline observed checks

- Python: **45 passed**, 18.32 seconds: existing store, command, declare, HTTP, contract and UI checks. No new unit tests were added after implementation.
- Browser: **30 passed**, 51.8 seconds, no skips: 17 real nginx/FastAPI/PostgreSQL persistence, recovery, 403 and session-isolation journeys; 13 route-mocked UI checks. Do not describe the latter as real service evidence.
- SQL readback: 13 durable triage rows with synthetic actor and timestamp; five declared incidents with `sev2`/`sev3`, **all five impact values JSON null**, and five rows in `incident.run_events`.
- Real, locally produced session-isolation and 403 screenshots were inspected; credentials were not printed or included in screenshots/traces.
- Initial ad-hoc SQL used the wrong `version` column and nonexistent `incident.events` table; those queries failed and were corrected to `expected_version` and `incident.run_events`. They are not product failures.

## Requirement audit (not acceptance)

| Criterion | Current evidence | Remaining work |
| --- | --- | --- |
| CA1 durable dismiss, actor/time/reload | Real dismiss/recovery journeys and SQL readback pass | Bind final correction candidate and durable reproduction |
| CA2 eligible target list and rejection by ID | Backend sequential rejection exists; no list handler or selection UI | Implement contracted listing; verify link-versus-close race and real selection |
| CA3 declare ID, severity/impact/event/reload | Real declaration/reload and SQL event/ID/severity proof | Impact is explicitly unresolved in contract and null in runtime; product decision required |
| CA4 no duplicate key effects; conflict refresh/context | Existing backend idempotency/CAS checks pass | UI only says “Refresh state”; its mock test manually changes the version, not an authoritative GET |
| CA5 403/missing policy/evaluation failure without false success | Real grantless 403 and absent persisted decision pass | Demonstrate missing-policy/evaluation-failure paths; do not invent an evaluator |
| CA6 manual versus external automatic distinction | No browser anomaly/threshold evaluator; actor displayed | No decision-origin projection or external automatic evidence; authoritative contract required |

## Corrected P1: link versus concurrent close

`TriageService._transition` read destination eligibility through a non-locking MVCC SELECT. A closer could commit a closed state while the linker still held an earlier eligible snapshot, then the linker persisted success. This violates CA2's revalidation guarantee. `FOR UPDATE` now holds the incident row through the same transaction as the triage write: a close that wins is observed and rejected with 409; a link that wins completes before the close.

Failure cases were written before production code. Parent independently repeated the final tests with baseline service bytes: **RED 2 failed / 3 passed**, 9.61 seconds. Corrected current candidate: **50 passed**, 14.04 seconds across all existing triage Python suites and the two concurrency cases. Worker targeted GREEN5passed after refactor; Ruff check/format and diff whitespace checks pass. The real database gate controls transaction ordering, not eligibility results. Early harness hangs were diagnosed and cleanup made bounded; those attempts are not RED evidence.

Verified source SHA-256: service `e8931db283e8fd93ddce119f93c72375f4a9dbbda67b58055105cdd75c80bab5`; test `a30050285d1f7816ea9bd644e69ec33c41a6d05000f9823b1c3110632e39e49d`. Parent logs: `/tmp/triage23-review/t23-1-parent-final-red.log` and `t23-1-parent-final-green.log`. This corrects the concurrent-ID acceptance defect, **not** the still-missing eligible-target list.

For standalone reproduction, prepare an owner-readable local `.env` from `.env.example`, supplying all required local non-production keys and routing values; do not print, attach or source it. This command uses the existing dedicated `python-checks-db`, not the runtime database. Select a unique Compose project; never globally tear down volumes:

```sh
docker compose -p triage23reviewchecks --profile checks run --build --rm python-checks pytest -p no:cacheprovider -q tests/test_triage_link.py
```

Expected: five passed, including both concurrent orderings and already-ineligible destination rejection. Observed equivalent pinned-image mounted-candidate execution: five passed, with independent full suite50passed above. The prepared `.env` and Docker/Git are host prerequisites; pytest and dependencies run only inside Docker. Rollback: revert the target-row lock correction; concurrent eligibility protection is then lost.

## Environment and evidence boundaries

Docker 29.8.2; isolated internal network `triage23-review-c25c`; tmpfs PostgreSQL 17.4 (pinned repository digest), no published database port. API and nginx web publish loopback only (28423/28424). No shared databases, existing stacks or ambient `.env` were used.

Cached checks image `sha256:698d015a7a95b2a20e342b96d1681fb604d8cf7dc497328530d2ba14438cd0ab` supplies dependencies, **not application source**: candidate mounted read-only at `/candidate`, `PYTHONPATH=/candidate/src`. Its lockfile and project metadata match candidate SHA-256 `783c78b44e4ab07091d0ee1d44a693b77f1ec0fdc94f9aa3c0e212cd34dc878b` and `aeabf158a6732df42a8dc71fb1aa30f62b89512b371f05aba8f6374dba7f0b33`. Browser image `sha256:3d6c1a422c8550ecbef61c78ab99b306e6e41380cfd853074ac8158194092f59` has Playwright 1.63.0. nginx is built from the candidate Dockerfile.

Private local recovery artifacts: `/tmp/triage23-review/baseline-python.log`, `baseline-browser.log`, `baseline-authoritative-corrected.sql.txt`, `browser-artifacts/evidence/`. Synthetic credentials reside only in an owner-readable private file and must not be attached. These temporary paths are **not** a durable published reproduction package. Repeatable repository commands and final candidate-bound media remain pending.

No push, publication, merge, issue closure, scope exception or human approval has occurred. All pending criteria above remain pending even though baseline tests pass. See [the task document](../../odd/tasks/triage-23-stack-review.md).
