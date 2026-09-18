# Design: Investigator Harness

## Decision: `investigator/`, not `harness/`

ADR-007 names the package `src/sre_agent/investigator/`. "Harness" already means two other things here: the `harness/` placeholder for the contract and fixture boundary, and the Compose service that runs contract conformance. A third meaning under the same name would make reviews ambiguous.

## Decision: The harness cannot reach state, structurally

The loop is a stateless reducer: it returns a result and never writes it. An Import Linter contract forbids `sre_agent.investigator` from importing persistence, incident, gateway, control and application code, and from importing FastAPI, SQLAlchemy or psycopg. The harness talks to the gateway over HTTP only, with its own models of the part of the Responses contract it reads. CA1 then holds by construction, not by review.

## Decision: The context is a declared projection

The request carries the incident context, the objective, the authorized capabilities, `incident_id` and `run_id`. The context reads only the fields the harness uses (state, alert, hypotheses, evidence) and ignores the rest of an incident-state document. The incident-state schema stays the authority for the full document, and a new field does not reach a model until this contract declares it. The state must be one where the workflow allows an agentic step.

## Decision: `task_id` is derived per turn, not received

The issue lists `task_id` among the inputs "according to the execution contract". That contract (`agent/api/correlation-mapping.v1.yaml`) makes the envelope derive it from each `turn_id` by replacing `turn_` with `task_`. The harness creates one turn per step and derives its `task_id`; `turn_id` never reaches the gateway.

## Decision: One JSON action per model output

The model answers with one JSON object whose `action` is `use_tool`, `propose_hypothesis`, `propose_mitigation`, `request_human` or `conclude`, the shape already used in the run-context example. Unknown fields are rejected. One surrounding Markdown code fence is tolerated because models add it often; prose around the object, two objects or a missing field make the output invalid. A hypothesis must cite at least one evidence item.

## Decision: Statuses reuse `terminated_reason`

The result status uses the run-state `terminated_reason` values, so #35 applies it without translation. `max_steps`, `invalid_output`, `denied` and `upstream_unavailable` are the workflow's four escalation triggers; `needs_human` hands the decision to a person on request.

| Situation | Status | Outcome |
|---|---|---|
| Valid hypothesis, mitigation or conclusion | `completed` | That action |
| The model asks for a human | `needs_human` | `request_human` |
| Invalid output or unknown citation, twice in a row | `invalid_output` | None; no tool runs |
| Tool not authorized | `denied` | None; the provider is not called |
| Gateway 401 or 403 | `denied` | None; no retry |
| Network error, timeout or 5xx, twice | `upstream_unavailable` | None |
| Budget exhausted | `max_steps` | None |
| Any other gateway status | `needs_human` | None; `detail` names the status |

## Decision: Validate references before use

A tool is authorized when a capability has `resource_type: mcp_tool`, its `resource_id` equals the tool name and its action is empty or `invoke`. The gateway stays the enforcement point; this check keeps an unauthorized request from reaching the provider at all. A citation (`supporting_evidence`, `based_on_hypothesis`) must name an item of the received context or evidence collected earlier in the same run. An unknown citation is an invalid output and shares the single re-interpretation retry.

## Decision: Limits

The issue asks its assignee to set the step limit and the timeouts before implementation. They are set here and in `Limits`:

| Limit | Value | Reason |
|---|---|---|
| Steps per run | 6 | Two tool reads (metrics, logs), a proposal and a retry, with a margin of two |
| Re-interpretation retries | 1 | Fixed by CA2 |
| Gateway timeout | 45 s | The gateway waits up to 30 s for the provider by default; a shorter harness timeout would cut valid answers |
| Tool timeout | 10 s | Fixture reads are local; the MCP path gets its own review with #187 |
| Transient retries | 1 | One retry of the same turn, then `upstream_unavailable` |

A step is one turn: one model answer consumed, including the re-interpretation. A transient retry repeats the same turn with the same `task_id` and does not consume a step. The worst case is bounded by 6 × (2 × 45 s + 10 s). If `OPENROUTER_TIMEOUT_SECONDS` rises, the gateway timeout must rise with it.

## Decision: Fixture evidence is labeled

Until #187 exposes governed MCP invocation, the fixture provider serves evidence recorded from the #186 `paymentUnreachable` signals. Every fixture item carries `source: fixture`, so it is never presented as an MCP query. The gateway-backed provider implements the same port later.

## Decision: Configuration is three variables

`INVESTIGATOR_GATEWAY_URL`, `INVESTIGATOR_GATEWAY_API_KEY` and `INVESTIGATOR_MODEL_ALIAS`. The key is a gateway principal key, such as the seeded `incident-harness`; the harness reads no provider or MCP secret.
