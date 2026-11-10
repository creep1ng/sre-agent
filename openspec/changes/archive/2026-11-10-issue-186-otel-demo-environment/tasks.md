# Tasks: OpenTelemetry Demo Environment (Issue #186)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 700-800 total across the change |
| 400-line budget risk | High if delivered as one PR |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 planning + manifest/lock/env; PR 2 operations + operator guide; PR 3 Grafana MCP + signal guide |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No.
Chained PRs recommended: Yes.
Chain strategy: stacked-to-main.
400-line budget risk: High.

Each PR stays below 400 lines including planning overhead (PR 1 ~330, PR 2 ~280, PR 3 ~250). Artifacts are not compressed to fit.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| Planning | Proposal, design, tasks, exploration, capability delta | PR 1 | repository checks | none | Remove change folder |
| Pin | Manifest, digest lock, env overrides | PR 1 | manual `config` inspection | Docker Compose | Remove `demo/` |
| Lifecycle | `up`, `down`, residue detection | PR 2 | `scripts/demo.sh up` then `down` | Docker Compose | Remove script |
| Failure cycle | `fail`, `verify`, `reset`, baseline restore | PR 2 | two `fail -> verify -> reset` cycles | Docker Compose, flagd | Revert script |
| Operator guide | Documented operations and prerequisites | PR 2 | link and lint checks | none | Remove doc |
| MCP boundary | Grafana MCP, read-only, network boundary, MCP availability in `verify` | PR 3a | isolation probe | Docker Compose | Remove overlay |
| Signal guide | Prometheus metrics and OpenSearch logs with queries and window | PR 3b | manual two-cycle sanitized output | Docker Compose | Remove doc |

## Acceptance mapping

| Criterion | Covered by | PR |
|---|---|---|
| CA1 clean start and availability report | Pin, Lifecycle | 1 and 2 |
| CA2 failure injection keeping synthetic traffic | Failure cycle | 2 |
| CA3 explicit revert without foreign deletion | Failure cycle | 2 |
| CA4 two reproducible cycles | Failure cycle | 2 |
| CA5 MCP isolation | MCP boundary | 3a |
| CA6 metrics and logs guide | Signal guide | 3b |

## Definition of Ready

| Item | Status |
|---|---|
| Candidate version and sufficient host resources | Met: validated on a real host, recorded in `exploration.md` |
| Demo-exclusive volumes and data identified as restorable | Met: dedicated Compose project approved by the issue author |
| Documented failure scenario and expected signal format | Partial: flag agreed; signal format tracked by #149, non-blocking |
