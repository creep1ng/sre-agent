# A Grafana MCP tool error no longer ends the investigation

Live, on 2026-10-19 (AWS OTel Demo, Grafana MCP through the governed gateway, DeepSeek v4.1
Flash through OpenRouter), Grafana MCP intermittently answered valid queries with a tool error;
the gateway returns `502 upstream_invalid` (API log `reason=mcp_tool_error`). The same queries
answered 200 a minute later. Two of four runs were lost that way; SQL over the outcome receipts:

```text
run_3fc6956c17a21e5d|unknown|investigation_upstream_unavailable|||
run_a3d80480b10459ae|unknown|investigation_upstream_unavailable|502|3|2
```

(run, status, reason_code, diagnostic http_status, turn_count, collected_evidence_count).
`run_a3d80480b10459ae` failed on `resource.service.name:"frontend-proxy" AND body:*checkout*`,
the query the alert itself suggests.

With this change the investigator records the failed call (and its MCP request id) as a turn
and tells the model `<tool> answered with an error for those arguments`, so it can retry or
change the query within the same six-step budget. Transport failures and other gateway errors
still end the run. `test_a_tool_error_is_shown_to_the_model_and_the_run_goes_on` drives this
through the real API and gateway: the first MCP call answers `isError`, the model retries, and
the run reaches `mitigating` with both MCP request ids in its receipt.

Live run on this code (API image built from it), started from the war room:
`inc-e13af17ebe5bf75babfe6674bcdd9db2` / `run_27b087a2c2f431c0` reached `mitigating` in 53.6 s
(no tool error happened in that run), then `approve_mitigation`, `otel_ec2.py reset` and
`verification_passed` took it to `resolved` (`war-room-resolved-tool-error-fix.png`).
