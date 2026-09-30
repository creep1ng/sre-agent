# Issue #332 — governed retrieval and immutable replay integrity

## Identity and scope

- Source M: `34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d` (tree `5255f6b27fc5eb2b8a77284c0d2b463ba191a537`), based on foundation F `9fb91f725e5c292346b930e3dae787cc05fe1a71`.
- Source diff against F: 1448 additions + 8 deletions = 1456 lines across 13 paths. Schema head: `20260929_16`.
- M is a no-conflict merge of prior retrieval and F; the R5 `owner.py`/persistence-test bytes are identical to F.
- The equal-manifest replay contract validates persisted owner children before reporting no-op; mismatch raises existing `BoKVersionCollision` and is never repaired by replay.

## Verified current-source evidence

- Independent local M focused suite: **91 passed**, exit 0; full configured suite: **1250 passed, 1 intentional live-provider skip**, exit 0. A further parent-owned current-head owner+HTTP spotcheck passed **27 tests in 6.60 seconds**, exit 0.
- Current-source TCP/API + PostgreSQL producer probe: **34 observed scenarios**, exit 0; database-isolation guard and schema migration exited 0. There are **22 HTTP outcomes** and **20 persisted audit rows**. The four new replay-integrity owner SQL cases are separate; they are not HTTP outcomes or audit rows.
- All four committed child-drift cases passed: chunk-content UPDATE, chunk DELETE, document-title UPDATE, and document `content_sha256` UPDATE. For each the manifest remained unchanged; exact replay raised `BoKVersionCollision`; drift survived replay; `finally` restoration succeeded; intact replay returned `False`.
- CA2–CA5 network examples include exact synthetic grants, two-principal allowed search/direct read and cross-identity denial, authentication/empty/missing/unready/storage outcomes, and committed grant/catalog/owner changes observed on subsequent requests. CA6 includes metadata-only audit projection with a credential/query/fragment scan. The separately run real-DB TestClient SQL observer tests—not this network probe—measure per-collection content-read counts.
- Local image IDs: API `sha256:72ab869a14e2114842d616e5b6094c148cd61ac9ce3e15515f45d039e53fd4ae`; checks `sha256:9df31fdea359faa96c17362936d97943cc234596c925e19621ffd87de75c7bc0`.
- Hosted CI on exact M source succeeded: [run 36673681362](https://github.com/creep1ng/sre-agent/actions/runs/36673681362), all 8 required jobs SUCCESS, watch exit 0. This does not constitute human acceptance.

Current recorded JSON: [`retrieval-results.json`](retrieval-results.json). Visually inspected real Chromium captures: [`retrieval.png`](retrieval.png), 1600 × 2400, SHA-256 `4aad36538780776d4df409ef095389408a353584d97edeb46b977bba85fef9b3`; and [`retrieval-audit.png`](retrieval-audit.png), 1600 × 1400, SHA-256 `0a338142b82555c18fc58cd2a3f9323a31b3aaf7529b4bba02b49468347fa69c`. They display actual recorded output, not a live product UI.

## Acceptance map

| Criterion | Current M evidence |
| --- | --- |
| CA1 | Current TCP/PostgreSQL producer plus [owner lifecycle and exact replay child-drift test](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_persistence.py#L93-L223); four committed mutations all collide without repair, restore, then intact replay is a no-op. |
| CA2 | Two-principal grant boundaries and [denied search/direct IDs without enumeration](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L313-L335); [unready, unauthenticated and wrong-version zero reads](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L614-L625). |
| CA3 | [Stable ranked order and deterministic tie-breaks](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L288-L310); [both demo collections, full provenance, direct result, exact miss and per-collection SQL counts](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L497-L575). |
| CA4 | Distinct empty/auth/denial/missing/unready/index/storage outcomes; [authorization storage faults return bounded 503 without content reads](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L629-L652); [audit-storage fault suppresses authorized content](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L681-L693). |
| CA5 | [Committed grant/catalog/owner state change blocks warm reads and restoration succeeds](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L579-L611). |
| CA6 | Network probe has 20 persisted metadata-only audit rows and no key/query/fragment leakage. [Real SQLAlchemy `before_cursor_execute` observer](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L475-L494) measures per-collection content reads; [audit identity/decision and private-data assertions](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L551-L575) and [audit-store failure containment](https://github.com/creep1ng/sre-agent/blob/34ce143d37ca2ee80c6adc4a6ee6d2d6c3c67c7d/tests/test_bok_http.py#L681-L693) are distinct TestClient source tests. |

The independent TestClient SQL listener is not measured by the TCP network probe. The four replay-integrity cases are owner SQL observations, not API content-read counts.

## Historical evidence, not current proof

[the immutable prior retrieval JSON](https://github.com/creep1ng/sre-agent/blob/7adfcaad8d2af313bd58983dd4bdd6df390e4426/docs/evidence/issue-332/retrieval-results.json), [retrieval PNG](https://github.com/creep1ng/sre-agent/blob/7adfcaad8d2af313bd58983dd4bdd6df390e4426/docs/evidence/issue-332/retrieval.png) and [audit PNG](https://github.com/creep1ng/sre-agent/blob/7adfcaad8d2af313bd58983dd4bdd6df390e4426/docs/evidence/issue-332/retrieval-audit.png) remain immutable at the old published commit and describe c37 `c37c3403c374350be676a56e9989132fdc200c8d` only. Its 30 observations / 22 HTTP / 20 audit rows are not M proof; current M independently records 34 observations / 22 HTTP / 20 audit rows. Old assets are excluded from the current manifest.

## Reproduction, safety and limitations

See [`reproduction.md`](reproduction.md). The local current run used the named project `issue332-retrieval-r6`, disposable tmpfs DB, and same one-at-a-time private overlay; API was stopped with intentional Ctrl-C (exit 130), scoped Compose `down` exited 0, and the project's containers/network were absent afterward. A project-named `postgres_data` volume metadata entry created by Compose was left untouched; cleanup did not use `-v`.

Synthetic corpus and in-memory API keys only; no provider call, Jev, cloud, OTel, SSH, production load, cross-worker race or privileged database-write prevention. This network probe is not the SQL listener/read-count harness.

## Delivery state

Evidence assets and exact-source CI results are ready for parent publication, with evidence commit/public HTTPS links pending parent binding. PRs remain DRAFT; `papiarcacamilo` was requested as reviewer but no approval is recorded. The #382 inline finding remains unresolved pending parent evidence publication/readback and response. No merge, issue closure, approval or label is claimed. Jev is deferred.
