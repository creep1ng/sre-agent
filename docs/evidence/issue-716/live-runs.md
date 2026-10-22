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

`run_db138d9d35867705` (screenshot `war-room-logs-evidence-local.png`):

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

## AWS OTel Demo (2026-10-22)

Same incident and spec against the AWS producer (`t3a.xlarge`, `paymentUnreachable` on), with
the governed MCP answering log queries in 0.2-2 s. The logs queries every run made:

| Run | Query | Docs | Services |
| --- | --- | --- | --- |
| run_6a07d594b4ab0b5e | `resource.service.name:"checkout"` | 86 | checkout |
| run_6a07d594b4ab0b5e | `resource.service.name:"payment"` | 74 | payment |
| run_ad87ccfaaab5714b | `resource.service.name:"checkout"` | 50 | checkout |
| run_ad87ccfaaab5714b | `resource.service.name:"payment"` | 50 | payment |
| run_7f6d7dde06f3e522 | `resource.service.name:"checkout"` | 100 | checkout |

None reached a hypothesis with `z-ai/glm-5.3-flash`: the model call that follows the evidence
produced 10-17 K output tokens and took 47-253 s, past the investigator's 45 s gateway timeout, so
each run ended `investigation_upstream_unavailable` (stage `gateway_transport`).

### Passing browser E2E

With the `triage-agent` route reconciled to `openai/gpt-4.1-mini` (private configuration, no code
change), `war-room-logs-evidence-real.spec.js` passed in 13.6 s: `playwright-report-aws.json`,
screenshot `war-room-logs-evidence-aws.png`, incident `inc-7266e8cca063f29f7cdbe7cc406e2197`,
run `run_bb6e4eb5ec0a6cbf`.

| Evidence | Tool | Query | Docs | Services |
| --- | --- | --- | --- | --- |
| ev_96d3a7e9226305d6 | query_elasticsearch | `resource.service.name:"checkout"` | 50 | checkout |
| ev_e265c88892397662 | query_prometheus | `sum(rate(checkout_payment_failures_total[5m]))` | - | - |
| ev_674b663a93ee31ca | query_elasticsearch | `resource.service.name:"checkout" AND severity.text:"error"` | 0 | - |

The first hypothesis (`hyp_7b73f5826319a1ae`) cites the 50 checkout documents. The current one
(`hyp_dbe1ea24c95c3ee1`) received them in its input, as the spec asserts, but cites the metric and
the empty error query instead.
