# Issue #45: current-main gateway probe on the isolated OTel demo

**Evidence kind: real external service.** This is a live Grafana MCP/gateway
observation, not acceptance of all CA1–CA8 or a full rebuild of current `main`.
The gateway runtime on the disposable EC2 was originally based on `6eb5422`,
with the issue-45 harness-network overlay; only the current-main gateway probe
source plus the Prometheus query correction was installed for this replay.
The exact probe SHA-256 was
`242f5d9ac3e105158a89e803e349ae4e52e34986d2e2559791a6d48d8ae4771b`.
The runtime/version difference is a retest condition for final acceptance.

## Environment and reproduction

- Dedicated temporary EC2 `i-0b0ae459347701439`, account `108782077951`,
  `us-east-1`; no ingress security-group rules. It expires at
  `2026-10-13 05:18:30 UTC`.
- Pinned OpenTelemetry Demo `3.0.0` at
  `1755859a9de82c2e5e225be68abc401a5ebf2b4f`, Grafana MCP `1.3.0`,
  Docker Compose `2.39.4`; local non-production credentials stayed in the
  private `.env` and demo state, never in the report.
- Start from the isolated demo and gateway setup in
  [the operator runbook](../issue-45-grafana-mcp-operator-runbook.md). On that
  dedicated host, with the repository at `/opt/sre-agent`, run
  `bash scripts/issue45_live_denial_witness.sh` as an operator with Docker/netns
  access. The [script](../../scripts/issue45_live_denial_witness.sh) embeds the
  metadata-only packet counter, coordinates a fresh barrier around the
  restricted request, runs the existing Compose harness and offline
  reconciler, and never gives the harness an MCP/Docker route.
- The exact script file SHA-256 was
  `cacfaa10abb73f2c3facaf25340d482d13715bffc0593e69c7d6027cc715728a`.
  SSM command `d68fd6b5-d48e-4841-956c-0f282a5c87c6` executed those
  bytes successfully. No raw packets, token values, operational response
  bodies, or private logs were copied into this report.

## Observed output

```text
probe_exit=0 (pending report awaiting the independent witness)
restricted known-ID request_id=2557cbb0-478a-4d64-bcf9-1b8e7c98cd92
restricted known-ID: HTTP 403 resource_unavailable; retryable=false
API→MCP HTTP POST attempts during that request: 0 (0 filtered TCP packets)
API→MCP HTTP POST attempts during subsequent allowed calls: 2 (22 filtered TCP packets)
allowed metric: HTTP 200, vector count 1, webstore-metrics, instant@now
allowed log: HTTP 200, total/returned 1, webstore-logs, now-5m..now
restricted discovery: HTTP 403; no enumeration
metadata-only audit for the denied request: mcp.invoke:authorization:denied:403
offline reconciliation: status=pass; failures=[]; denied.upstream_delta=0
```

The counter filters the actual API and MCP bridge IPs and TCP destination port
8000, counts only distinct `POST /mcp HTTP/` request-line starts, and deduplicates
TCP retransmissions by source/destination ports and sequence. The denied and
allowed intervals use the **same probe** with a private barrier. The positive
allowed interval demonstrates that the capture is not blind. No JSON-RPC body
was inspected, so the two positive POST method identities are not asserted.
The matching request ID comes from the sanitized pending report and is required
by the offline reconciler; a 403 or an unrelated zero counter is insufficient.

## Failures and boundaries

- An earlier attempt used aggregate MCP netns RX bytes. They changed
  `106938→107004` (+66) during the denied interval despite the 403; this is
  background traffic, not evidence of a forwarded HTTP POST. That attempt
  **failed** the aggregate-zero assertion and was not reconciled as passing.
  The packet-filtered attempt above resolves the ambiguity.
- The local worktree `scripts/worktree-compose` E2E attempt could not allocate
  another Docker network because all predefined address pools were subnetted.
  No conflicting stack was started. A cached Node harness instead ran with
  `docker run --network none` and read-only test/script mounts: the test-first
  query expectation failed 1/3 on `expr: up`; after the one-line source fix,
  the exact controlled gateway CLI suite passed 3/3. This is separate from
  the live service observation.
- CA4–CA8 are **not** established by this probe. The earlier dated EC2 record
  has historical boundary, marker, timeout and two-cycle observations, but
  those were against the pre-main candidate and require current-main
  integration review before requesting full issue acceptance.
