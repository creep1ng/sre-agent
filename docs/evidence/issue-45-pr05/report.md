# Issue 45 P6: offline witness reconciliation

**Evidence kind: controlled CLI/E2E fixture.** The fixture tests offline parsing
and summary behavior only; it does not capture a real upstream counter or
establish CA2.

Base: published P5 PR #432, `0022a2a7373bba3309a0c82caf2e0e6ab7b9fe97`.
Tested source SHA-256:
`009f3a5ee8ca7279f821609dfe9c9fcd97023ac5dbc9d68dc93e93634fc22030`.
Test SHA-256:
`17bf557230f57e23a338d7094cd78a8d66127a4a1595f7ae977e9c8e163f0ce0`.

## Reproduction

The controlled HTTP/CLI test uses the cached Node 22.14.0 image. It requires no
network, build, pull, credentials, `.env`, live API, database, or demo stack.

```sh
docker run --pull never --network none --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```

## Observed behavior

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

Witness metadata and shape do not prove that a source measures upstream
`tools/call` invocations or truly correlates to the denied request. No real
counter was captured. This result does not close CA2 or any CA1–CA8 criterion.
The current exact-source screenshot, parent independent verification, mirror,
publication, hosted P6 CI, and human acceptance remain parent-owned or pending.
