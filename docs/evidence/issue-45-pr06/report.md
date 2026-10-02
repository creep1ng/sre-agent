# Issue 45 P7-D: supplied service/IP boundary checks

**Evidence kind:** controlled HTTP/CLI fixtures. **Route:** delegated direct.
Current base: documentation prerequisite PR #435 `08bf3fb60649ba73a70a1480c00fa81b6409a38c`; owned service/IP candidate is locally committed and unpublished.

This slice probes only supplied service-name and direct-IP targets using
unauthenticated GET `/healthz`, manual redirects and cancelled response bodies.
Summaries allowlist target kind, status and HTTP status. Any HTTP response fails
(exit 1); missing, invalid or blocked inventory is `unverified` (exit 2), never
an isolation pass. Coverage is `supplied-targets-only`; `full_boundary` stays
`pending`. Published-origin parsing/probing is retained for P7-E, not included
here. No real harness topology, proxy/admin, binding, token-absence or CA4/CA5
proof is claimed; CA1–CA8 and human acceptance remain open.

Test-first RED on untouched base source completed: 0/4 passed. All four HTTP/CLI
cases observed legacy exit 0 instead of required reachable exit 1 or unverified
exit 2. Capture `/tmp/issue45-p7-service-ip-evidence/service-ip-red.log`,
SHA-256 `65446b80f451a506c4e234a1bd8f00bdfa4e5a7af1a456fc20907669a6e9ddfa`.
The helper timeout was 20 seconds; an earlier 5-second timeout from prior
exploration was inconclusive because it raced the legacy per-target timeout.

GREEN on cached Node 22.14.0 image: P7-D tests 4/4 and existing gateway tests
3/3; both changed JavaScript files and both gateway files passed `node --check`.
Network was disabled; memory and swap were each capped at 256 MiB. Fixtures
verified HTTP 503 and redirect 302 are reachable failures, redirect is not
followed, blocked/missing/invalid targets are unverified, invalid inventories
cause zero contact, no Authorization header is sent, and body/port/alternate URL
markers are not printed. A first GREEN attempt exposed a faulty test setup in
which `{}` was overridden by valid defaults; that run is preserved separately
as `service-ip-green.log`. The corrected test and final run are in
`service-ip-green-retry.log` (SHA-256
`d88096ec0e7c021959c5d5bc111062b2663755f6df5c09eac0b692ddab128e09`).

Reproduce with the cached image (no build or pull):

```sh
docker run --pull never --network none --memory=256m --memory-swap=256m --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  sh -c 'node --check /source/scripts/demo_mcp_probe.mjs && node --check /source/tests/test_demo_mcp_probe.mjs && node --test /source/tests/test_demo_mcp_probe.mjs && node --check /source/scripts/demo_mcp_gateway_probe.mjs && node --check /source/tests/test_demo_mcp_gateway_probe.mjs && node --test /source/tests/test_demo_mcp_gateway_probe.mjs'
```

Source SHA-256: `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283`;
test SHA-256: `205885029a70adda1e9cd424f87efe446db473790d7334e93ff077b3bf7514c6`.
Before restoring the preserved full-P7 sections, text delta against
`529b2105a5f2ee841c804713b5e32b605edb965a` was 363 additions + 19 deletions
= 382. At the pre-restack checkpoint, the restored full history measured
393 additions + 19 deletions = 412, twelve above the repository hard gate before
accounting for screenshot representation; no screenshot is included.
Parent independently passed the current P7-D and gateway tests 7/7, four syntax
checks, no skips (`/tmp/issue45-p7-service-ip-parent-evidence/raw-green.log`).
P6 hosted CI `36712710854` is terminal all-eight success; P7 is not published
and has no hosted CI yet. Parent owns current screenshot, full mirror,
commit/publication and P7 CI. No human acceptance or real boundary evidence is
claimed; CA1–CA8 remain open.

## Tracker-inclusive current candidate

Full candidate backup `a81c10980fbae43cde58df53d16665b1e8629efa` remains preserved. Clean owned restack onto PR43508bf produced tested `66ff3d87f5deeb1eba9c86c5800f4cd2f836b647`,359 additions+20 deletions=379 before fresh proof/media. Source/test hashes above are unchanged. Parent independently observed exact66ff cached networkless256MiB Docker syntax4files and7/7 HTTP/CLI (4 service/IP+3 gateway), no skips; capture `/tmp/issue45-p7-service-ip-parent-evidence/restacked-green.log`. Hosted P7 CI and human acceptance remain pending; no real CA closed.

Actual [service/IP PNG](service-ip.png),1600×2100/252193bytes/SHA`2f42b09e81780d16ff9e8565d34720c31f0fbd8099d2d2122bededc12ba16a7f`, shows the committed66ff Docker output excerpt and safe assertions. Visually inspected/sanitized, sandboxed hostChromium153/localCSP/noexternalassets. Later changes only correct historical base/count wording and attach this proof; runtime source/tests are unchanged. Not a live topology or total-isolation capture.

## PR #437 symlink-invocation correction (local candidate)

Review finding 4144842486 identified that the prior `pathToFileURL(process.argv[1])` entrypoint comparison skipped `main()` through a symlink, returning exit 0 without a report. The first-failing actual CLI test creates a temporary symlink only under the container's writable `/workspace`, invokes Node with that link, and expects the missing-inventory structured `unverified` report and exit 2. On the unchanged source it observed 4/5 pass: the new case failed `0 !== 2` (exit 1), while all four existing service/IP HTTP/CLI cases passed. Raw capture: `/tmp/issue45-p7-symlink-evidence/red.log`, SHA-256 `f01ff9e805e3f206b2151bea370b62ae6e08325eee7e568c01e2439584209ede`.

The minimal entrypoint correction compares the script's `fileURLToPath(import.meta.url)` to `realpathSync(process.argv[1])`; it changes only CLI main detection. The exact cached Node v22.14.0 Docker run, with network disabled, 256 MiB memory and swap limits, scripts/tests/schemas mounted read-only, passed all five service/IP CLI cases plus the existing gateway suite (8/8, no skips). The symlink case emitted `status=unverified`, exit 2, with no target contact. Capture: `/tmp/issue45-p7-symlink-evidence/green.log`, SHA-256 `5e7b06fd41a878416fb2f437e6134adfddf25c4c885a198ff9dc94b899e8371e`. Four `node --check` invocations for the service/IP and gateway scripts/tests also passed in the same pinned networkless image (`syntax.log`, exit 0).

Current source SHA-256 `90ca3f79153c070ba000996241e7ce43030a2052f8a6b73dbb342b18e7a67879`; current service/IP test SHA-256 `cc42eafa276225d4a26e112aed527bbdcb3c5d804797b7266eefadb7ef49923f`. This local correction does not fix P7-E published-origin coverage; those tests remain frozen in a separate candidate. This is not proof of a real topology, binding, proxy/admin, token-absence, or full boundary; CA1–CA8 and human acceptance remain open. Parent owns independent recheck, full mirror, actual screenshot, size-gate decision, commit/publication and hosted CI.

## PR #437 symlink correction — owned-branch verification (new capture)

The 4-file fix above was propagated unchanged to the owned branch `codex/issue-45-06-service-ip` (base `08bf3fb60649ba73a70a1480c00fa81b6409a38c`) and re-verified with fresh captures in the same pinned image `sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d` (Node v22.14.0, `--pull never --network none`, 256 MiB memory/swap, read-only scripts/tests/schemas mounts). The new test creates its symlink in the container's writable temp directory via `mkdtemp`, not under `/workspace`.

RED re-confirmed on exact base source SHA-256 `8d639e4c36cfc0fed5017cd692e2236b54a27fc487d442a8f67afe377bee3283` with new test SHA-256 `cc42eafa276225d4a26e112aed527bbdcb3c5d804797b7266eefadb7ef49923f`: 4/5 pass, symlink case fails `0 !== 2` (exit 1). Capture `/tmp/issue45-p7-symlink-owned-evidence/red-owned.log`, SHA-256 `aec702ea22d66d6923e62d1026663377d7c255d709b5163eed34095460ee1e3e`.

GREEN on fixed source SHA-256 `90ca3f79153c070ba000996241e7ce43030a2052f8a6b73dbb342b18e7a67879` with the same test: 5/5 service/IP (symlink case `status=unverified`, exit 2, no target contacted) plus 3/3 gateway, 8/8 total, no skips, exit 0; four `node --check` passes in the same run. Capture `/tmp/issue45-p7-symlink-owned-evidence/green-owned.log`, SHA-256 `ba1ef0e46eb9c83e44cee73eec4ce8687e9b0df6abc1ab6bd3dde2411ad84bd9`. Both logs scanned for secrets/headers/personal data: none found.

The committed `service-ip.png` above remains the real rendered Docker-output artifact; its shown assertions are byte-identical in the new capture (the fix changes only entrypoint detection, no report strings). The symlinked invocation itself is evidenced by the TAP log read-back, not by new pixels. Post-commit tree verification (clean status, recomputed source/test SHAs identical) binds these captures to the published head. P7-E stays frozen separately; CA1–CA8 and human acceptance remain open.
