# Real investigation run: hypothesis, then mitigation (tested SHA 4f55ca83527abd2647aa80736d4b31e4471a8a32)

Stack: `scripts/setup_sre.py` in AWS mode (`SRE_ENABLE_PAID_LLM=1`), OTel Demo on the
shared EC2 instance with `paymentUnreachable` injected by `scripts/otel_ec2.py fail`, Grafana
MCP through the governed gateway, alias `triage-agent` -> `deepseek/deepseek-v4.1-flash`
(provider `decart`) through OpenRouter. Incident declared by `demo-human` with the firing
alert rule in its summary; run started with `POST /v1/incidents/{id}/runs`
`{"workflow_version":"1.0.0","objective":"investigate"}`.

| Item | Value |
| --- | --- |
| Incident / run | `inc-9dff3669f1243a248053a7a776ffa6bf` / `run_3243ea9dd094399d` |
| Run after start (68.8 s) | `awaiting_human`, `mitigating`, `pending_command: approve_mitigation` |
| Transitions (SQL over `incident.run_events`) | `start_investigation` -> `continue_investigation` -> `propose_mitigation`; after approval `apply_mitigation` -> `verifying` |
| Dispatch receipts | intent `pending`, outcome `success` (`result_status: completed`), 11 request ids, 4 MCP request ids |
| LLM consumption (audit metadata) | 6 requests, 20 593 input / 8 272 output tokens, USD 0.003232 |

Agent outcome as persisted in the incident state (fields only, no prompt or raw output):

- Hypothesis `hyp_f3c22a144c9ea37e` (medium, 3 cited evidence items): "Checkout failures are
  caused by failing PaymentService/Charge calls made by checkout, producing PlaceOrder errors
  and frontend /api/checkout 500 responses."
- Mitigation `mit_893a534858c9fbae` (`pending`, `simulated`, risk medium, based on the
  hypothesis above), 3 steps; verification check: "Prometheus query sum by (service_name,
  span_name) (increase(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR",
  service_name=~"checkout|payment"}[2m])) shows no errors for PaymentService/Charge and
  CheckoutService/PlaceOrder; frontend-proxy access logs stop showing POST /api/checkout 500."
- Evidence: two `query_prometheus` (`webstore-metrics`, error calls by service and by
  service/span) and two `query_elasticsearch` (`webstore-logs`) calls, each with its MCP request id.

Before this change (`7da3bfd`) the dispatch ended at the first hypothesis: main's own
`test_http_investigate_uses_governed_llm_and_mcp_and_persists_the_result` asserts the run stays
`investigating`, and `propose_mitigation` needs an already recorded hypothesis, so no dispatch
could reach it. The two live runs on `7da3bfd` tonight did not get that far either: one model
asked for a human before using any tool, the other hit an MCP relay that had gone down.

Screenshots (Playwright against the composed web console, `demo-human`):
`war-room-mitigating.png`, `decisions-awaiting-approval.png`, `war-room-verifying.png`
(after `approve_mitigation`, the incident is `verifying`).
