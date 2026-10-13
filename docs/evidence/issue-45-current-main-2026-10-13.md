# Issue #45: integrated current-main OTel demo verification

**Evidence kind: real external service.** Refs #45; this is a review candidate, not an assertion of human acceptance or permission to close the issue.

## Candidate and environment

Current `main` base `ef6b328fe75494a9b77d9ddd9a330cbaa22ac1b6`, plus exact PR heads [#593](https://github.com/creep1ng/sre-agent/pull/593)
`9f87a0c337e2f88b24ff848865ef06620acf90e6`, [#594](https://github.com/creep1ng/sre-agent/pull/594) `f3f9858b45ef01b2e5c9d3875436ce8d72ab0631`, and
[#597](https://github.com/creep1ng/sre-agent/pull/597) `754d4b88ba08062e3f94f630339a900c71498f74` (including #595). The unpushed, clean integrated tree was
`f7543994a027f5c6f6a1cc0dadc744075026a940`. Dedicated no-ingress temporary EC2 in `us-east-1`; pinned OTel Demo 3.0.0
(`1755859a9de82c2e5e225be68abc401a5ebf2b4f`), Grafana MCP 1.3.0, private non-production `.env` and generated MCP token. Nothing here uses a shared local
Compose network or publishes the MCP port.
API image `sha256:8f6685475399b16e8823f1336fd91715f4c191e42bbeec6c5a8cbb2693dfb8cd`; harness image
`sha256:0bc5efbb22abe65baa3a892c0f07b923a3c8bdc1841ef277006e2ffc0f2ee095`; Compose 2.39.4 (SSM `f25eef68-13f8-42d5-bfeb-9c7e6878c03a`).

## Actual observations

- **CA1–CA3:** public gateway metric/log HTTP 200, one result each; only `query_elasticsearch`/`query_prometheus` discovered. Restricted known-ID 403,
  matching audit, **zero** independently filtered API→MCP POSTs during its own request `496cea00-8edf-45b8-a766-da144e4613b4`, positive control **two**
  POSTs; offline witness `pass` (SSM `8477005c-eef0-4a2f-a324-32e53ff3e6b4`).
- **CA4:** real harness reached API 200; MCP/Grafana names and direct IPs, four host-proxy routes and published MCP port were unavailable; no provider
  token or proxy environment (SSM `c8428c8d-ed6b-477c-8781-c4a7c0f92720`).
- **CA5:** MCP `--disable-write`, categories prometheus/elasticsearch/datasource. Host Grafana datasource proxy still returned HTTP 200: **administrative
  surface/risk remains**, so total host isolation is **not** claimed (SSM `2fbcbe92-412e-4c06-86fc-70d3facd7705`).
- **CA6:** synthetic marker's validation 422 and upstream-error 502 public responses, API/MCP/Grafana/proxy logs, metadata-only audit and attached evidence
  had no marker. A real private incident snapshot/event contained it, while the populated public snapshot returned 200 without it. Private rows are
  expected, not public leakage (SSM `ae077734-edbb-4289-bbde-32ed361538fe`, `7aefe1bf-833f-4f60-ba10-4109608aa4cf`,
  `bbb4d6cc-010c-4431-af1d-3876a4272b02`).
- **CA7:** stopped MCP returned normalized 503 `upstream_unavailable`; paused MCP returned normalized 504 `upstream_timeout` after 30.15 s. No raw body or
  secret appeared; unmodified API→MCP packet counter saw **one HTTP POST** for timeout versus three for the positive control, not an uncontracted retry
  (SSM `2deae119-5461-401e-93ac-8d4de41d7dae`, `8ba8fe6d-9945-4314-93c1-a8329e969f84`).
- **CA8:** two real failure/reset cycles returned measured clean baselines: checkout error metrics 0→21.71→0 and 0→16.01→0, stalled orders 0→4→0 and 0→11→0, proxy 500s 0→4→0 and 0→11→0; completed orders and proxy 200s returned after both resets. The [six sanitized captures and verifier](./issue-45-current-main-cycles/) passed 2/2 chronological cycles in Compose and an independent networkless Docker replay (SSM `68b72afb-71ff-4e14-b2ff-8126d1cf8ae6`).

## Reproduce and limits

On a fresh dedicated pinned demo host/database with the candidate above, generated private `.env` and `DEMO_STATE_DIR`, build the gateway/harness:
```sh
docker compose --env-file .env -p issue45-gateway -f compose.yaml -f compose.mcp.yaml up -d --build --wait mcp-seed api
docker compose --env-file .env -p issue45-gateway -f compose.yaml -f compose.mcp.yaml build harness
```
Then
run `scripts/issue45_live_marker_probe.sh`, `scripts/issue45_live_snapshot_probe.sh`, the marker probe again, `scripts/issue45_live_unavailable_probe.sh`,
`scripts/issue45_live_timeout_counter.sh`, and finally `scripts/issue45_live_signal_cycles.sh`. The operator scripts keep private markers and packet bodies
off stdout and write bounded reports under `/opt/issue45-evidence`; use only this isolated project. Recheck the demo's automatic deadline and do not run
against another stack. The local worktree Compose attempt was blocked by exhausted Docker address pools; these are actual EC2 container/network
observations, not a local Compose pass.

Human review, merge order and post-merge exact-main replay remain required. A first offline Docker replay missed the harness schemas mount, a second missed its writable tmpfs, and the corrected networkless command passed; neither earlier container reached the verifier.
