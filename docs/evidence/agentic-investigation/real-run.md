# Real investigation run: hypothesis, then mitigation

Tested SHA `843b2b94dbb4f09abbb4b15086f0206498986185` (API image built from it), on
2026-10-19 04:25Z. Stack: `scripts/setup_sre.py` in AWS mode (`SRE_ENABLE_PAID_LLM=1`), OTel
Demo on the shared EC2 instance with `paymentUnreachable` injected by `scripts/otel_ec2.py fail`,
Grafana MCP through the governed gateway, alias `triage-agent` ->
`deepseek/deepseek-v4.1-flash` (provider `decart`) through OpenRouter. Incident declared by
`demo-human` with the firing alert rule in its summary; run started with
`POST /v1/incidents/{id}/runs` `{"workflow_version":"1.0.0","objective":"investigate"}`.

| Item | Value |
| --- | --- |
| Incident / run | `inc-c8bd440e58ceb7ed07b535d1fa9619cd` / `run_3fc9b2011cc35ef9` |
| Run returned by the start (67.4 s) | `awaiting_human`, `mitigating`, `pending_command: approve_mitigation` |
| Transitions (SQL over `incident.run_events`) | `start_investigation` -> `continue_investigation` -> `propose_mitigation` |
| Dispatch receipts | intent `pending`, outcome `success` (`result_status: completed`), 11 request ids, 4 MCP request ids |
| LLM consumption (audit metadata) | 6 requests, 33 847 input / 6 904 output tokens, USD 0.004215 |

Agent outcome as persisted in the incident state (fields only, no prompt or raw output):

- Hypothesis `hyp_0902a9d8acdc838d` (medium, 3 cited evidence items): "The checkout incident is
  caused by failures in checkout's calls to PaymentService/Charge, producing
  CheckoutService/PlaceOrder errors and frontend-proxy HTTP 500 responses."
- Mitigation `mit_f3483c9424681fcb` (`pending`, `simulated`, risk medium, based on the
  hypothesis above), 3 steps; verification check: error calls for `checkout` spans
  `oteldemo.PaymentService/Charge` and `oteldemo.CheckoutService/PlaceOrder` return to zero and
  frontend-proxy `/api/checkout` 500 responses stop.
- Evidence: `query_prometheus` (`webstore-metrics`) for error calls by service and then by
  checkout span, and `query_elasticsearch` (`webstore-logs`) for checkout and proxy logs, each
  with its MCP request id.

After `approve_mitigation` as `demo-human` the run went to `verifying`.

Before this change (`7da3bfd`) the dispatch ended at the first hypothesis: main's own
`test_http_investigate_uses_governed_llm_and_mcp_and_persists_the_result` asserts the run stays
`investigating`, and `propose_mitigation` needs an already recorded hypothesis, so no dispatch
could reach it. Two live runs on `7da3bfd` did not get that far either: one model asked for a
human before using any tool, the other hit an MCP relay that had gone down.

Screenshots (Playwright against the composed web console, `demo-human`):
`war-room-mitigating.png`, `decisions-awaiting-approval.png`.
