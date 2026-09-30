# Issue #332 — Retrieval M R11 acceptance report

**Candidate:** `7438b5a87dbf389fd1a936c899281520c1300295`
**Tree:** `572782bb0f9ec58d78a4156d22fbd9b66b83c456`
**Base:** F `e2b83d45f285c46a5a83c0234846dbfd122934df` (parents `3986bdca68fe81f84469aa7df91cd08e8a55338b` + `e2b83d45`), built on current main `2779b0b9af4476c1e1a0c0b99ab2379c8326a86e`
**PR:** #422, base `feat/bok-owner-corpus-332` until human merges #382, DRAFT
**Diff vs F:** 1,570 additions + 8 deletions = 1,578 lines / 13 paths
**Controlled result:** 40 observations, 22 HTTP outcomes, 20 persisted metadata-only BoK audit rows, all assertions passed; schema `20260929_16`; captured `2026-09-30T14:01:13Z`.

## Acceptance map

| Criterion | Current evidence |
| --- | --- |
| CA1 | Propagated F integrity plus [producer JSON](results/retrieval-results.json) and [capture](retrieval.png): immutable replay/collision, readiness gate, partial-document rejection, changed/deleted drift rejection with `finally` restore, arbitrary order, two demo collections active, success/rejected catalog-clock cases, four replay drifts. |
| CA2 | Exact grants before content reads: both demos allowed under correct principal, cross-identity search/direct 403, unauthenticated 401, tags/topics never grant. Independent SQL observer proof via source tests shows zero denied content reads. |
| CA3 | Deterministic ranked search/direct reads with full collection/document/version/fragment provenance; authorized miss empty; exact miss 404; repeated ranking with document/section/index tie-breaks. |
| CA4 | Distinct outcomes: authorized no-match 200 empty, denial 403, unready 503, exact miss 404, index/storage 503 with `storage_unavailable`, plus locked-cause actual denial via separate source-test [R8 summary](r8-denial-cause.json): 44 passed, principal/resource/grant causes verified, generic 403 preserved. |
| CA5 | Committed grant revocation, catalog deactivation, owner revocation each observed on next request with correct 403/503, then restored to 200; no identity cache; already-delivered content not retracted; no concurrency claim. |
| CA6 | Internal persisted BoK metadata only: 20 TCP audit rows with operation/status/decision, identity present, content absent, query/fragment/credential scan passed; separate per-collection SQL read-count observer via TestClient suite. Bound to internal audit, not external 2.5 `AuditEvent` schema conformance and no new audit HTTP route. |

Source checks for exact head: independent focused 142 passed (32.26s); configured full/static 1,298 passed, 1 intentional live-provider skip (86.01s), exit 0; R8 focused 44 passed (16.47s); schema harness 125/125, all immutable releases 1.0.0–2.5.0, both OpenAPI surfaces lint clean. Hosted workflow: [exact-head CI run 36722880991](https://github.com/creep1ng/sre-agent/actions/runs/36722880991), all 8 required jobs SUCCESS.

## Reproduction and safety

See [portable reproduction](reproduction.md). Sequential project `issue332-retrieval-r11` after verified F cleanup, same overlay/guard/tmpfs contract, synthetic keys in memory, reversible faults restored in `finally`. No providers, Jev, cloud, OTel, SSH, production, or foreign resources. Scoped down without `-v`; owned labels empty.

## Captures

`retrieval.png` is a real Chromium 153.0.8010.52 screenshot (1600×1650, 275,713 bytes) showing 16 representative scenarios with full 40-observation JSON accompanying. `retrieval-audit.png` (1600×1400, 227,917 bytes) shows 22 TCP HTTP outcomes, 20 persisted audit rows, and the separate R8 TestClient card. Both visually inspected for readability, correct SHAs, and disclosure footers. Privacy audited: synthetic corpus only, no credentials, headers, queries, fragments, or keys. No generated imagery.
