# Proposal: Investigator Harness

## Intent

Issue #185 needs a harness that receives an incident's context and objective, runs a bounded investigation through the gateway and returns a validated result that the incident runtime can apply. ADR-007 selected a minimal in-house loop because the Responses contract accepts only `model`, `input`, `incident_id`, `run_id` and `task_id` (unchanged through 2.2.0), which rules out framework tool loops. This change delivers that loop. #35 wires it into the incident flow and #38 verifies the connection.

## Scope

### In Scope

- Input and output contract of the harness, including the correlation of every turn.
- A bounded loop: step budget, one re-interpretation retry, one transient retry and timeouts.
- Validation of tool requests against authorized capabilities, and of citations against the received context.
- A gateway client configured only by base URL, gateway API key and model alias.
- An `EvidenceProvider` port with a fixture implementation whose evidence is labeled as such.
- A deterministic demo server with the issue's scenarios, and one real LLM call through the gateway.

### Out of Scope

- State machine, persistence, run API and permissions (#26, #146, #145).
- Wiring the harness into the incident flow (#35).
- Governed MCP invocation (#187); the gateway-backed evidence provider waits for it.
- Generalist harness, sub-agents, memory across incidents, streaming, native tool calling and real remediation.

## Capabilities

### New Capabilities

- `investigator-harness`: a bounded, stateless investigation loop that consumes the gateway and returns a validated result.

### Modified Capabilities

None.

## Approach

A stateless reducer in `src/sre_agent/investigator/`, as ADR-007 decides. Each turn sends one string to `POST /v1/responses` and expects one JSON action back. A tool action is checked against the authorized capabilities and served by the evidence provider; any other action ends the run. The harness returns the outcome, the evidence it collected and its turns. The incident runtime decides what to apply.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `openspec/changes/issue-185-investigator-harness/` | Added, PR 1 | Proposal, design, tasks, capability delta |
| `src/sre_agent/investigator/contract.py` | Added, PR 2 | Request, actions, result, limits, correlation |
| `.importlinter`, mypy scope | Modified, PR 2 | The package cannot reach persistence, incident or gateway code; strict typing |
| `contract.py` parsing, `prompt.py` | Added, PR 3 | Output interpretation, reference checks, turn input |
| `src/sre_agent/investigator/` ports, loop | Added, PR 4 | Bounded loop |
| `src/sre_agent/investigator/` client, provider | Added, PR 5 | Gateway client, fixture provider |
| `scripts/investigator_demo.py`, `docs/investigator.md` | Added, PR 6 | Deterministic scenarios and operator guide |
| Live call evidence | Added, PR 7 | One run through the real gateway |

## Rollback

Remove the package, its tests and this change folder. No data, schema or migration is involved.
