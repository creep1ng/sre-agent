# Issue 45 P4: controlled gateway query evidence

**Primary evidence kind: controlled integration.** Loopback HTTP fixtures exercised
the CLI and gateway-shaped requests; this is not a live Grafana/MCP integration,
CA1 acceptance, or an independently observed upstream invocation.

Base: `9eb3eb3dd3d55facfcd28d35490f85fedb95ac10`. Parent will bind the tested
candidate SHA after finalization. Pinned harness image:
`sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d`
(Node v22.14.0, existing cache; no build or pull).

Source SHA-256: `d6ca8ffd15ce609f3cc8a6f56f907cfba0076df2c76cdd7151fcb88f0cd35a0a`.
Test SHA-256: `ae917a52057545eb823ca25d354b39284da2418c2ca79725dd9d9ac71bdfb0d7`.

## Reproduction

No live credentials, `.env`, API, database, demo, or provider are needed. The
container is isolated with `--network none`; Node's fixture server and spawned
CLI share the same container loopback. The project inputs and tests are read-only.

```sh
docker run --pull never --network none --rm \
  --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 \
  -v "$PWD/tests:/source/tests:ro" -v "$PWD/scripts:/source/scripts:ro" \
  -v "$PWD/schemas:/source/schemas:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  node --test /source/tests/test_demo_mcp_gateway_probe.mjs
```

## Observed results

- Pre-source observed RED: 0/2 passed; the report-phase assertion saw
  `gateway-discovery` instead of `gateway-query-smoke`, and the redirect fixture
  saw 6 rather than 12 expected gateway requests. This was observed before the
  first source edit. A later baseline replay against the original probe also
  failed 0/2; its private capture is not presented as contemporaneous evidence.
- GREEN after source: 2/2 passed under the reviewed networkless Compose overlay;
  the exact `docker run` reproduction above also passed 2/2.
- Valid fixture requests were one filtered discovery GET, exact Prometheus and
  Lucene log POST payloads, then one restricted-discovery GET. Report summaries
  included only configured source/window/status/error/count fields. A successful
  fixture run is `pending` because no upstream witness is present.
- Empty metric and log results and a 504 `upstream_timeout` produced bounded
  failures. Redirect fixture attempts left the alternate server at 0 requests;
  each of three CLI invocations made four expected gateway calls (12 total).
- Synthetic tokens, response markers and raw operational bodies were absent from
  serialized CLI output. Invalid configuration made no gateway requests.

The initial Compose attempt could not allocate a runtime network (Docker reported
that all predefined address pools were subnetted). The reviewed private overlay
used `network_mode: none` and did not alter Docker pools; the public reproduction
uses the equivalent explicit `docker run --network none` boundary.

No screenshot was produced: the parent-reported isolated, sandboxed Playwright
capture container failed at OCI startup before Node/rendering, so no PNG exists.
Required screenshot, exact tested source/test
hash binding, independent review, hosted CI and human acceptance remain pending.
CA1–CA8 remain open: fixtures prove request/summary behavior only, not real query
results, full redaction, isolation, upstream counters, or signal cycles.

Parent reran the current source/test hashes above: 2/2 passed with hashes unchanged.
Earlier independent 2/2 used the same source and a pre-formatting test hash; it is
historical rather than exact-current-test proof. This candidate remains local and
partial until screenshot, hosted CI, public binding and human review exist.

Final labels now describe gateway smoke queries, not invocation-free discovery.
The parent reran 2/2 after this label-only correction; source logic was unchanged.

## Restacked onto gateway-origin correction

Current base: `f23e9a01f01b0ef85c3a7a43a134e413af0a87dc` (parent's P3 root-path
fix). Final restacked source SHA-256:
`e75fcf678255cd031d05b98691ffc82f12aeeb646e0939546ae969bfb8bfca36`.
Final test SHA-256:
`73f08fe9a43d480ca61674b1bc8deed096490c85d8926a1bf9d6df8197c922e9`.
This final candidate retains root-origin validation; no P4 source behavior was
changed during the restack.

The first post-rebase suite run failed at the inherited root-slash assertion
(expected CLI exit 0, actual 1). This was an integration validation failure in
the merged test fixture: its preceding empty-log scenario left `logReply` at
zero results before testing the valid root-slash URL. The fixture is now
restored to a positive log result before the root-slash check; no production
source change was made for this failure.

The exact networkless Docker reproduction above then passed 2/2 on the combined
P4/root candidate. Root origin and `/` perform the P4 four-request sequence
(discovery GET, two fixed query POSTs, restricted discovery GET); non-root paths
remain invalid with zero requests. Existing P4 malformed-discovery, empty/error,
redirect, safe-summary and no-leak cases pass with the root-path correction.
Parent's candidate commit/publication, screenshot, hosted CI and human review
remain pending; the original base/hash/checkpoint above describe the earlier
P4-only candidate and are retained as history.


## Final local restack after PR #430 report correction

Current P4 base: `bb384f08ed65b6429b2d5d4175c035a541f4686e`, the report-only
follow-up to published PR #430 head `73cd29e58288329a7b2b0fd9eaa816ecace26438`.
The earlier `f23e9a01`/source/test block above records the prior local checkpoint;
no source or test bytes changed during either restack. Current source/test
SHA-256 remain
`e75fcf678255cd031d05b98691ffc82f12aeeb646e0939546ae969bfb8bfca36` /
`73f08fe9a43d480ca61674b1bc8deed096490c85d8926a1bf9d6df8197c922e9`.

The exact cached Node 22.14.0 command above passed 2/2 after the final rebase.
Observed fixture output remained `status=pending` due to the absent upstream
witness; there were 12 expected gateway requests and 0 alternate-server calls.
Both changed JavaScript files passed `node --check`, and the final parent-relative
`git diff --check` passed. The 504 fixture tests bounded upstream-timeout error
normalization, not actual expiration of the 35-second client request budget.
This remains controlled integration only: no live gateway/MCP result, screenshot,
real counter, or CA1–CA8 acceptance is claimed. PR #430's latest hosted CI was
pending at this checkpoint; P4 screenshot, publication, and review remain
parent-owned.
