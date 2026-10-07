# Issue 45: gateway-origin path validation

**Evidence kind: controlled integration.** A loopback HTTP/CLI fixture confirms
that origin URLs route normally and unsupported base paths fail closed. This does
not demonstrate live gateway behavior or close any CA1–CA8 criterion.

Base: `9eb3eb3dd3d55facfcd28d35490f85fedb95ac10`. Review finding:
[PR #425 comment](https://github.com/creep1ng/sre-agent/pull/425#discussion_r4140855307).
Parent binds the candidate SHA after finalization. The tests reused the cached
Node 22.14 harness image
`sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d`;
no build or pull occurred.

## Reproduction

No `.env`, token, API, database, demo or external network is needed. The test's
HTTP server and spawned CLI run in the same isolated container; source inputs
are mounted read-only.

```sh
docker run --pull never --network none --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```

## Observed results

- **RED before source change:** 0/2 passed. `${url}/mcp-gateway` returned CLI
  status 0, although expected configuration rejection was status 1; the test
  stopped at that assertion. The fixture records that unsupported URLs make no
  gateway requests after the fix.
- **GREEN after source change:** 2/2 passed. `${url}` and `${url}/` each perform
  exactly two discovery GETs. `${url}/mcp-gateway` and `${url}/mcp-gateway/`
  fail as `probe_configuration_missing` before any request. Existing malformed
  discovery, restricted non-enumeration, token/privacy and redirect
  coverage remains green; alternate-server requests remain zero.
- Minimal source change requires `url.pathname === "/"` before returning
  `url.origin`; query/hash and embedded credentials remain rejected.

Source SHA-256: `3ff73bd2dcd297cb6951fa18aa61b92c765305ddeb339c6a14a13d66a6799fa4`
Test SHA-256: `ff8bf3e4fe02ee31c1e7d1df471a1431d7507a42240637dc899bbd2a8f6b447e`

`node --check` for source and test plus `git diff --check` passed. Private TAP
outputs: `/tmp/issue45-gateway-root-evidence/url-red.log` and `url-green.log`.
At the initial code freeze no screenshot had been captured; hosted CI and publication were pending.

Parent independently reran the exact source/test hashes above: 2/2 passed,
with hashes unchanged. This is local controlled proof; hosted CI/publication were pending at that checkpoint.

## Current screenshot and scope

[Actual controlled evidence](gateway-root.png): PNG1600×3400,185878bytes, SHA-256
`56bc41f324877a53ab9dc1ecc1bb3a4fb7a279003550f0d314c3969115133587`.
Existing sandboxed host Chromium captured the actual parent Docker TAP output,
tested assertions and source/test hash footer from offline HTML with CSP blocking
external assets. The image was visually inspected and contains only controlled
fixture output; no live tokens, personal data or confidential payloads.
This is a screenshot of the controlled HTTP/CLI evidence reproduced above, not
proof that containerized Chromium or the separate PR424 Markdown preview works.
Source/test bytes remain those independently tested at local commit `f23e9a01f01b0ef85c3a7a43a134e413af0a87dc`;
the later metadata/media commit does not change executable behavior. Human review
and candidate-bound hosted CI remain pending. Revert this corrective unit to
restore its parent; unsupported gateway path prefixes are intentionally rejected.

## Review evidence correction

The suite does not exercise the 35-second AbortSignal expiration. Its child-process
kill guard and upstream-unavailable fixture are not timeout-budget evidence; the
unsupported timeout-coverage wording above was removed. Source budget remains
35 seconds, but real budget-expiration proof is pending.
