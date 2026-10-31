# Issue 880: demo model measurements (2026-10-31)

Each run is one real investigation through the governed gateway and OpenRouter, in the composed
stack of `compose.evidence-verdict-e2e.yaml` with `E2E_REAL_MODEL=1`: real API, PostgreSQL,
investigator and gateway; Grafana MCP scripted (Prometheus: checkout 12, frontend 24, payment 0
error calls; Elasticsearch: no documents). `scripts/model_candidate_e2e.py` starts the run as
demo-human and reads latency, tokens and billed cost (OpenRouter's `usage.cost`) from the gateway's
audit rows, and the credited model and provider from `GET /v1/usage/requests`. Raw records:
[measurements.json](measurements.json).

| Run | Model on provider | Gateway | Timeout | Calls (s) | Total | Tokens in/out | USD | Outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Haiku 5.5 on `anthropic` | main | 60 | 1, rejected | 3.8 s | not recorded | not recorded | `upstream_unavailable`, no turn |
| 2 | Haiku 5.5 on `anthropic`, one direct request | bypassed | n/a | 1.9 | 1.9 s | 17/4 | 0.0000037 | 200 after a 400, both Anthropic |
| 3 | Haiku 5.5 on `anthropic` | this branch | 60 | 2.3, 1.6, 2.4, 6.0, 5.1, 5.7 | 24.3 s | 12 646/3 774 | 0.0031516 | success, `mitigating` |
| 4 | GPT-6 Luna on `openai` | this branch | 60 | 2.7 | 4.5 s | 1 120/56 | 0.0001679 | 502 `upstream_invalid` |
| 5 | Haiku 5.5 on `anthropic` | this branch | 30 | 2.2, 1.9, 3.9, 5.8, 8.1, 4.6 | 27.4 s | 12 646/4 460 | 0.0034946 | success, `request_human` |

Models: `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna`. Run 1 and 4 receipts:
`investigation_upstream_unavailable`. Run 2 is a diagnostic request with the gateway's exact body
outside the stack: OpenRouter's attempt 1 answered 400 and attempt 2 answered 200, both from
Anthropic, which the gateway on main rejects (run 1). Run 3 proposed a cited hypothesis and a
mitigation; run 5 recorded two cited hypotheses, then asked for a human.

Five real runs; OpenRouter billed USD 0.0068 for runs 2 to 5. Run 1's cost is not recorded: that
version of the script read only the turns' calls, and the stack was removed before the failed
call's audit row was read. In runs 3 and 5 every output was one JSON object, every call was
credited to `anthropic` with the dated model `anthropic/claude-haiku-5.5-20261007`, and every tool
call passed the gateway's validation.

Not run: `z-ai/glm-5.3-flash` on `z-ai`. OpenRouter's catalog names that provider "Z.AI" (tag
`z-ai/fp8`), and the gateway requires the answering provider's name to equal the pinned slug
ignoring case, so every answer would be rejected. The current `z-ai/glm-5.3-flash` on `relace`
was not re-measured; #718 recorded calls of up to 80.6 s.

Public catalog (`/api/v1/models/<id>/endpoints`, 21:20Z, USD per million input/output tokens,
uptime over 1 day): Haiku 5.5 on Anthropic 0.10/0.50, 100 %; GPT-6 Luna on OpenAI 0.10/0.50,
100 %; GLM 5.3 Flash on Z.AI 0.15/0.50, 100 %, on Relace 0.0149/0.1543, 100 %.

Choice: `anthropic/claude-haiku-5.5` on `anthropic` with `OPENROUTER_TIMEOUT_SECONDS=30`. It was
the only candidate whose answers the gateway accepts once it allows a retry inside the pinned
provider. Its slowest call (8.1 s) is far below the investigator's 45 s wait per call at that
timeout, and an investigation costs about USD 0.0035 (value 7).
