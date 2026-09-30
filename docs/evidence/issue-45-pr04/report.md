# Issue 45 P5: controlled known-ID-first denial

**Evidence kind: controlled HTTP/CLI integration.** This fixture validates the
restricted request ordering and bounded summary; it is not live gateway/MCP
evidence, an upstream-call witness, or CA2 acceptance.

Base: published P4 PR #431, `c840ed76f8e16f123e1d33127ff7798e5de49597`.
Tested worktree source SHA-256:
`e3091d60d67f66c641ff9a510db27f20159d59690fc82641e2293c132b4a76de`.
Test SHA-256:
`5170d4394280ecc5eb895faef215e9104672c72c4bd1ae901839ceb6a2cfa616`.
The report and documentation do not alter either tested file.

## Reproduction

The fixture uses the cached Node 22.14.0 image and does not require network,
build, pull, credentials, `.env`, live API, database, or demo stack. The spawned
CLI and loopback HTTP fixtures run inside the same isolated container.

```sh
docker run --pull never --network none --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```

## Observed behavior

- Test-first RED, before source edits: 0/2 passed. The report lacked the
  restricted-denial summary, and the redirect test observed 12 instead of the
  new expected 15 total gateway requests across three scenarios. Capture:
  `/tmp/issue45-p5-evidence/red.log`.
- GREEN after implementation: 2/2 passed. Final naming-adjusted candidate also
  passed 2/2. Capture: `/tmp/issue45-p5-evidence/green-final.log`.
- The first controlled request is a restricted-role POST to
  `/v1/mcp/tools/query_prometheus` with the fixed Prometheus `up` payload.
  The unchanged four P4 requests follow. The fixture checks distinct safe UUIDs
  for denial and restricted discovery.
- The safe `denied` summary contains status, allowlisted
  `resource_unavailable`, a validated UUID, and `upstream_delta: null`. Invalid
  status, code, missing UUID, or invalid UUID fails closed. Secrets and fixture
  response markers are excluded from CLI output.
- A valid controlled run remains `pending` for absent upstream witness. The
  suite's redirect scenarios made 15 expected gateway requests total and zero
  alternate-server requests.

This controlled denial does not prove zero upstream invocations, implement
offline reconciliation, or close CA2 or any other CA1–CA8 criterion. P5
screenshot, final commit binding, parent independent verification, hosted P5
CI, and human acceptance are parent-owned or pending. P4's hosted CI run
`36680206014` passed all eight jobs per the parent checkpoint; it is not P5 CI.

## Parent committed proof and actual screenshot

Parent independently reran committed `638942a4aa6278ae4c32bb61e72d214aaffe5e28`:
both JavaScript syntax checks and2/2 HTTP/CLI tests passed with unchanged hashes.
[Actual controlled PNG](known-id.png),1600×3400,205437bytes, SHA-256
`ff510c21f80a58a4e57db727d3bf58d3c9144d2e1a7092d7b947b00280b21edb`,
shows observed safe denial/query output and exercised first-request assertions.
Existing sandboxed HOSTChromium153.0.8010.52 rendered offline HTML with CSP,
no external assets and a private profile. Parent visually inspected/sanitized it;
this is not a live UI, actual upstream-zero witness or PR424 preview proof.
Earlier no-PNG/uncommitted notes are capture-time history. Hosted CI and human
acceptance remain pending; subsequent media/report-only edits preserve hashes.
