# Issue #716: logs evidence in live investigations

Local OpenTelemetry Demo 3.0.0 with `paymentUnreachable` on, Grafana MCP, the governed API and the
paid investigator model, 2026-10-21/22. The incident was declared with an operator summary
("Customers report checkout payments failing") that names no log field.

## Before: the field the model guessed

Before the change the model wrote `service.name:checkout AND level:ERROR` in two runs
(`run_f917262d08be2984`, `run_e8834e0aef978d5b`). Counts in the same OpenSearch index:

| Query | Documents |
| --- | --- |
| `service.name:checkout` | 0 |
| `resource.service.name:checkout` | 66 |
| `resource.service.name:product-reviews` (unquoted, service absent) | 625, all `product-catalog` |
| `resource.service.name:"product-reviews"` | 0 |

Every `checkout` and `payment` log of the failure is `INFO`, so a level filter finds nothing.

## After: completed runs

Columns: evidence, tool, query, documents, services in the documents, cited by the hypothesis.

`run_db138d9d35867705` (screenshot `war-room-logs-evidence.png`):

| Evidence | Tool | Query | Docs | Services | Cited |
| --- | --- | --- | --- | --- | --- |
| ev_0732b87ff77a60f3 | query_elasticsearch | `resource.service.name:"checkout"` | 50 | checkout | yes |
| ev_d6e7d15710f4dd58 | query_elasticsearch | `resource.service.name:"checkout" AND (body:*fail* OR body:*error* OR body:*exception*)` | 0 | - | yes |
| ev_c959240ef4334957 | query_prometheus | `sum(rate(calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m]))` | - | - | yes |
| ev_b9a0424a072afc07 | query_elasticsearch | `resource.service.name:"payment"` | 50 | payment | yes |

`run_250db3da5739c133`:

| Evidence | Tool | Query | Docs | Services | Cited |
| --- | --- | --- | --- | --- | --- |
| ev_8c35d0402e7daf5d | query_elasticsearch | `resource.service.name:"checkout"` | 50 | checkout | yes |
| ev_153682d43bdba834 | query_elasticsearch | `resource.service.name:"checkout" AND (severity.text:ERROR OR body:fail* OR body:error* OR body:declin* OR body:unable*)` | 0 | - | yes |
| ev_ea3d4a3be8049d9e | query_prometheus | `sum by (status_code) (rate(calls_total{service_name="checkout"}[15m]))` | - | - | no |
| ev_d7c0ea72ecf9d8d1 | query_elasticsearch | `resource.service.name:"payment"` | 50 | payment | yes |

Four other runs on the same host ended `investigation_upstream_unavailable`: a governed MCP call
took longer than the investigator's 10 s tool timeout (2-20 s measured under memory pressure).
