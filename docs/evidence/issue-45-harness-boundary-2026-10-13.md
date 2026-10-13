# Issue #45: real harness-network boundary

**Evidence kind: real external service.** This records the actual Compose
harness network on the dedicated OTel demo EC2, not a claim of formal total
isolation or an exact-current-main gateway rebuild. The tested
`compose.mcp.yaml` SHA-256 was
`ada259a8a801a2e828dc8b7575cfe357604080bb2acecf672c1d28126a15a8ef`.

## Reproduction and environment

With the pinned demo and gateway started on an isolated host at
`/opt/sre-agent`, run
`bash scripts/issue45_live_harness_boundary.sh` as the Docker operator.
The [exact runner](../../scripts/issue45_live_harness_boundary.sh) SHA-256
was `b418464d39cb9618b70346b8c2bfcb73e301bdd9ed0f24acec7b98b9e0588edc`.
It obtains target IPs and published-port state **outside** the harness,
passes only non-secret inventory values in, and uses the actual Compose
`mcp-consumer` network for bounded unauthenticated reachability checks.
SSM command `33338d59-b4d3-46a5-9078-ce8732d160ec` executed these bytes
successfully on EC2 `i-0b0ae459347701439` in `us-east-1`.

The local worktree Docker daemon could not create another network: all
predefined address pools were subnetted. No second stack was started, and
no local Compose runtime pass is claimed. The remote command is the real
container E2E evidence. A local `docker compose config --quiet` attempt was
also unavailable because this checkout has no private demo-state token file;
that file was not copied here.

## Observed result

```text
harness boundary: pass; failures=[]
public gateway /health/ready: HTTP 200
Grafana MCP published port 8000: absent
MCP service name: blocked
MCP direct IPs: blocked (2)
Grafana service name: blocked
Grafana direct IP: blocked
host-published Grafana proxy routes: blocked (4)
MCP/provider/audit secret variables in harness: absent
HTTP(S)/ALL_PROXY variables in harness: absent
```

No target URL, response body, token, header or private configuration was
emitted by the harness. The gateway remains reachable because only the API
joins `mcp-consumer`; the harness does not join the MCP or demo networks.
The probe covers the nine inventoried paths on this topology, not arbitrary
future ports, VPN routes or host changes. An earlier live RED on the
unisolated runtime bridge reached the host-published Grafana datasource API
with HTTP 200; this overlay removes that observed harness bypass.

## Read-only posture and residual risk

A separate metadata-only check (SSM
`ea3b3560-6e52-41fd-ac9b-8764400740c1`) found Grafana MCP running with
`--disable-write` and categories `prometheus,elasticsearch,datasource`.
The **host** still reached the published Grafana datasource API with HTTP 200.
That host-side proxy/Admin surface is an explicit residual risk: the harness
boundary does not justify a claim of total Grafana isolation.

CA4 is observed for the supplied real harness routes; CA5 read-only MCP
posture and the residual host bypass are documented. CA1–CA3 and CA6–CA8
require their separate evidence, and final acceptance still needs an
integrated current-main runtime retest and human review.
