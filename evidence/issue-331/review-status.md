# Review status snapshot (not approval)

At the latest parent-refreshed inventory on 2026-09-30: 16 reviews were `COMMENTED`; all 9 inline threads remain unresolved with zero replies; 6 are not outdated and 3 are outdated. Zero reviews are `APPROVED`. Outdated threads: #402 atomic update/audit, #406 dependency authentication context, #409 persistence-boundary coverage. Outdated status does not mean resolved or accepted. This is not a live refresh.

| PR | Thread reference | Finding area | Last observed state | Repair evidence location |
|---|---|---|---|---|
| #397 | [4111972652](https://github.com/creep1ng/sre-agent/pull/397#discussion_r4111972652) | CA4 version length | unresolved; not outdated; 0 replies | #397 version bound; report/screenshots |
| #402 | [4112477234](https://github.com/creep1ng/sre-agent/pull/402#discussion_r4112477234) | CA1/CA5 missing update return and audited 404 | unresolved; not outdated; 0 replies | #402 CAS/404 proof |
| #402 | [4112477239](https://github.com/creep1ng/sre-agent/pull/402#discussion_r4112477239) | CA1/CA5/CA6 lifecycle update+audit atomicity | unresolved; outdated; 0 replies | #402 injected rollback/retry proof |
| #404 | [4112721334](https://github.com/creep1ng/sre-agent/pull/404#discussion_r4112721334) | CA6 reject provider-use fields on non-LLM audit DTO | unresolved; not outdated; 0 replies | #404 focused DTO/repository tests; screenshot is not DTO proof |
| #405 | [4112775701](https://github.com/creep1ng/sre-agent/pull/405#discussion_r4112775701) | CA6 malformed-path correlated audit | unresolved; not outdated; 0 replies | Immediate child #433 only; #405 core does not claim this fix |
| #405 | [4112775705](https://github.com/creep1ng/sre-agent/pull/405#discussion_r4112775705) | CA2/CA6 closed success envelope | unresolved; not outdated; 0 replies | #405 actual response fields |
| #405 | [4112775708](https://github.com/creep1ng/sre-agent/pull/405#discussion_r4112775708) | CA2 Bearer challenge | unresolved; not outdated; 0 replies | #405 actual 401 challenge |
| #406 | [4112832408](https://github.com/creep1ng/sre-agent/pull/406#discussion_r4112832408) | CA2/CA3 once-per-request verifier and direct grants | unresolved; outdated; 0 replies | #406 actual verifier/SQL proof |
| #409 | [4112929442](https://github.com/creep1ng/sre-agent/pull/409#discussion_r4112929442) | CA2/CA6 content-read boundary/demo tests (P2) | unresolved; outdated; 0 replies | #409 SQL boundary plus preserved demo |

These are finding summaries only, not full private review inventory or a representation of reviewer intent beyond the cited topic. Current candidate correction status is in [`acceptance-report.md`](acceptance-report.md) and the per-slice reports. Human review remains pending.
