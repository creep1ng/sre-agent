# Issue 45 P6: offline witness reconciliation

**Evidence kind: controlled CLI/E2E fixture.** The fixture tests offline parsing
and summary behavior only; it does not capture a real upstream counter or
establish CA2.

Current base: published P5 PR #432, `9cdf424573b35216702787af6e45be4172757b9b`.
Previous P6 checkpoint source SHA-256: `06260e9cb35327f234ac40c880f838fd9398f43831c588eae7711de82dbf97cb`.
Previous P6 checkpoint test SHA-256: `29013ec083adab404f7531039105477a0e82eb5d6d19f371e82f5b099013a138`.

Earlier P6 implementation and its evidence below were captured against P5 head
`0022a2a7373bba3309a0c82caf2e0e6ab7b9fe97`; they remain historical, not current-base proof.

## Reproduction

The controlled HTTP/CLI test uses the cached Node 22.14.0 image. It requires no
network, build, pull, credentials, `.env`, live API, database, or demo stack.

```sh
docker run --pull never --network none --memory=256m --memory-swap=256m --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```

## Historical observed behavior at base 0022a2a

- Test-first RED before source changes: 1/2 top-level tests passed, 1 failed.
  The new reconciliation case reached the CLI and received
  `probe_arguments_invalid` instead of the expected zero-delta result. Capture:
  `/tmp/issue45-p6-evidence/red.log`.
- GREEN after implementation: 2/2 passed, including rejection of duplicate
  denial/discovery UUIDs. Capture:
  `/tmp/issue45-p6-evidence/green-final.log`.
- A current P5 `gateway-query-smoke` pending report plus a matching
  `upstream-counter` fixture reconciles to a normalized pass with delta zero.
  Offline mode leaves the fixture gateway request count unchanged.
- Wrong schema/phase, extra report failures, non-null query error, invalid or
  mismatched UUID, generic or relabeled `audit_events_total`, unsafe/reversed/
  nonzero counters, malformed/missing/oversized JSON, and incomplete CLI
  arguments fail closed. Output is allowlisted; no `before`/`after`, raw fields,
  or fixture secrets are emitted.
- Existing P5 redirect tests remain intact: 15 gateway fixture requests and
  zero alternate-server calls.
- Both changed JavaScript files passed Node 22.14.0 `node --check`; `git diff
  --check` passed.

## Current P6 candidate on P5 head 9cdf424

- Restack is local only. Backup ref `codex/issue-45-05-witness-before-retryable-restack` preserves pre-restack P6 HEAD `bc11898b5b1a9b9437b0b1b477400e351eabdc5c`; original backup `codex/issue-45-05-witness-before-p5-id-restack` still preserves `6f6f9569419aaa8eb261bf32dbefcc6b0948b2c6`. The P6 commit was replayed onto P5 `9cdf424573b35216702787af6e45be4172757b9b` as `1803790`; task conflict was reconciled from the lossless parent tracker.
- Test-first RED on the restacked source: the offline reconciliation accepted the pending report but omitted `denied.retryable:false` from its normalized output (`undefined` instead of `false`). Exact cached Docker run: 1/2 top-level tests passed, 1 failed. Capture: `/tmp/issue45-p6-current-evidence/red.log`. The test asserts offline zero gateway calls.
- Minimal correction validates exactly `denied.retryable === false`, retains false in normalized output, and compares denial/discovery UUID identity case-insensitively. Witness request-ID correlation remains an exact string match, as required by the existing contract. No producer, request, route, counter, witness-source, or runtime behavior changed.
- The earlier 2/2 run (`green.log`) did not prove witness rejection: after the duplicate-report case, the pending file still contained invalid duplicate IDs, so those witness cases failed `probe_report_invalid` before reaching witness validation. Parent review found this fixture sequencing gap. The fixture now restores a valid pending report and asserts each expected witness failure.
- Test-first RED after that correction: uppercase witness UUID matching an alphabetic lowercase denied UUID was accepted (`status:pass`) instead of rejected as `upstream_witness_mismatch`; the exact cached networkless Docker suite was 1/2. Capture: `/tmp/issue45-p6-current-evidence/witness-red.log`. The source was then restored to exact request-ID matching.
- Current exact cached Node 22.14.0 networkless Docker GREEN: 2/2. Tests reach and assert the intended failures: generic/relabelled audit and unsafe/reversed counters => `upstream_witness_unavailable`; different/case-variant witness IDs => `upstream_witness_mismatch`; nonzero delta => `denied_upstream_delta_nonzero`. Valid false is retained, malformed retryable cases fail `probe_report_invalid`, and the synthetic zero-delta witness remains an offline pass with 0 gateway calls. Capture: `/tmp/issue45-p6-current-evidence/witness-green.log`.
- Both JavaScript `node --check` commands passed in the same cached networkless container; `git diff --check` passed. Existing 15 gateway fixture requests and zero alternate-server calls remain asserted. The measured current-base diff against P5 `9cdf424573b35216702787af6e45be4172757b9b` is 363 additions + 17 deletions = 380 lines.
- This is only controlled offline fixture evidence. It does not prove operator provenance or true upstream-counter semantics, capture a real counter, or close CA2 / any CA1–CA8 criterion. Parent independent verification, current PNG, mirror, commit/publication, hosted P6 CI, and human acceptance remain pending.

Witness metadata and shape do not prove that a source measures upstream
`tools/call` invocations or truly correlates to the denied request. No real
counter was captured. This result does not close CA2 or any CA1–CA8 criterion.
The current exact-source screenshot, parent independent verification, mirror,
publication, hosted P6 CI, and human acceptance remain parent-owned or pending.

## Parent committed current proof

Exact `afcc54680d50069acfaa0349bc08ba74232839c1` independently passed cached Docker syntax and HTTP/CLI2/2 with unchanged current hashes. [Actual P6 PNG](offline-witness.png),1600×3800,331930bytes,SHA-256 `88c5787b707f6bad23e27961e87410652b9a5bee75cb868ccc29aa27b91df1cd`, shows real committed test output and desmasked witness failure diagnostics. Host sandboxed Chromium153.0.8010.52 rendered local CSP/no-external-assets HTML; visually inspected/sanitized. No live counter/CA2 or PR424 container-preview proof. Publication/current hosted CI/human review pending.

## P6 bounded input-read correction (local candidate, 2026-09-30)

Base is published P5 PR #432 `9cdf424573b35216702787af6e45be4172757b9b`; PR #434 remains draft at its unchanged published head. The user accepted a size exception limited to this coherent PR #434 correction; no future exception, merge, acceptance, or CA closure is implied.

- Test-first RED used the cached Node 22.14.0 image with `--pull never --network none --memory=256m --memory-swap=256m` and the 512 MiB `/workspace` tmpfs. The permanent CLI test created a 1 GiB sparse report. Existing full-file reading returned no structured CLI result: child close status was `null` instead of required exit 1 with a bounded `probe_report_invalid` report. The test runner exited 1 (2/3 top-level tests passed). Capture: `/tmp/issue45-p6-current-evidence/io-red.log`, SHA-256 `c1daa64592cf86dc20b0ffe3e097fbe64c6a1ea122ab9149fc09cba44db22c30`.
- The loader now opens the file and reads through a fixed 16,385-byte buffer, stopping at EOF or limit+1, rejects oversized input before parsing, and closes the handle. It retains structured failure for malformed/missing inputs and performs no network work in reconciliation.
- GREEN on the same capped, networkless command: 3/3 top-level tests passed. The 1 GiB sparse report returned status `fail`, `probe_report_invalid`, and only 233 output bytes. Existing offline witness failure guards, retryable:false contract, P5 five-request sequence, 15 controlled requests, and zero alternate-server calls remained passing. Capture: `/tmp/issue45-p6-current-evidence/io-green.log`, SHA-256 `99e82f9d7e9c27ec74fe0918f644f259a5b582b6f29c268433cca5ac8e621e13`.

The exact memory-capped test command was:

```sh
docker run --pull never --network none --memory=256m --memory-swap=256m --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```
- The runbook now identifies offline P6 reconciliation as implemented while stating it neither captures counters nor validates witness provenance/semantics. No producer, runtime, dependency, Compose, route, query, or counter semantics changed.
- Current source SHA-256: `8a9d926288b416157e041e3a84c4e075a65bec799dcd5af227af1fe5f9e61583`; current test SHA-256: `c5e016a9f6445176ff0aa44d39bcac4347ff114da18e71ed027e0de57a161961`. Exact cached-container source/test syntax and `git diff --check` pass. Final verification log: `/tmp/issue45-p6-current-evidence/final-verification.log`, SHA-256 `d74f5a9ae8e052db5848b4eb074c914dd5710ce3d269080656bca4f728fab3fa`. Current base text delta is 456 additions + 20 deletions = 476; the existing PNG is binary and adds no text lines. The user's accepted size exception is limited to this correction.
- Log-path collision: the earlier raw P6 retryable-schema files at `/tmp/issue45-p6-current-evidence/red.log` and `green.log` were overwritten by the new runs before this collision was noticed. They are not reconstructed or represented by the new captures; the earlier written checkpoint remains historical text, but its raw retryable RED/GREEN files are unavailable in this workspace. Current correction captures are separately named `io-red.log` and `io-green.log`.
- Parent-owned independent verification, current genuine screenshot, full task mirror, commit/publication/current hosted CI and human review remain pending. No real counter/provenance or CA1–CA8 acceptance is claimed.

## Parent committed bounded-read proof

Tested `d4146e58b21fbbafd70c3d36f28ec884e2924e82` on base `9cdf424573b35216702787af6e45be4172757b9b`: parent independently reran both Node syntax checks and the full cached, networkless, 256MiB-capped Docker CLI suite; 3/3 passed with no skips. Source8a9d9262 and testc5e016a9 hashes above were unchanged. The 1GiB sparse report failed safely in 233 bytes; offline reconciliation and zero alternate-server assertions remained intact.

[Actual committed bounded-read PNG](offline-witness-bounded.png), 1600×2000, 340903 bytes, SHA-256 `e22fab60b1bd66d2c835f1d97c9292adcfa7dcea01d49858322ca0d7e57f67af`, shows the real committed Docker output. Host sandboxed Chromium153.0.8010.52 rendered local CSP/no-external-assets HTML with a new isolated profile; visually inspected and sanitized. The prior PNG is retained as historical evidence. No real counter, live environment or PR424 container-preview proof is claimed. Current publication/hosted CI and human review remain pending.

## P6 rollback review correction

Review4144076795 was source-confirmed: the rollback section still named P5. Exact tested `15eec333cfdb6e0ab5a7e926f5f4b7d7c8fa33ae` corrects it to remove P6 reconciliation/bounded-reader/offline tests/P6 documentation together while preserving P5 known-ID denial, retryable:false, UUID distinctness and P3/P4 history. Parent exact capped networkless Docker syntax/CLI3/3 passed with unchanged source/test hashes. Runbook SHA-256 `d9e661d8877d344dbdcc58885420eca2e77db71924d63b9418d5957de2d7cd91`.

[Actual rollback candidate PNG](offline-witness-rollback.png),1600×2300/383752bytes/SHA-256 `0a028cc649cd56c0cc2f97021d924fb2f510af819233b38c9c9c120a495eebe2`, shows real committed CLI output (primary) plus current checked-in rollback excerpt (secondary); sandboxed host Chromium153.0.8010.52/local CSP/isolated profile, visually inspected/sanitized. Prior PNGs retained. Prior exact db4 CI36707970552 passed all8; new candidate publication/current CI/human review remain pending. No live counter, environment or real CA closure.
