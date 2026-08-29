# ADR-007: Minimal in-house investigator loop as the demonstration harness

- **Status:** Accepted
- **Contract version:** 1.2.0

## Context

HT-06 asked which harness lets an agentic client consume the gateway with only a base URL
and a gateway credential while leaving a path towards tools, MCP and Skills, without
building a generalist harness. The mandatory evaluation matrix includes LLM contract
compatibility, and that criterion is a gate: a candidate that cannot speak the frozen
contract cannot be integrated, so scoring its other capabilities describes an option that
is unusable.

The gate was measured rather than argued. `scripts/ht06_harness_poc.py` validates
requests against `schemas/releases/1.2.0/json-schema/http/responses-request.schema.json`
and fires the requests a candidate harness puts on the wire. Contract 1.2.0 accepts only
`model`, `input`, `incident_id`, `run_id` and `task_id`, declares
`additionalProperties: false`, types `input` as a single string, and admits only
`output_text` content. A request carrying `tools` returns 422. A request carrying a
message array returns 422. ADR-001 already lists tools and conversations as deferred, so
this is the contract behaving as designed.

Every mainstream candidate delegates the tool loop to the model endpoint through a
`tools` request property and a tool-call output type. Against contract 1.2.0 that path
returns 422, so the loop cannot be delegated to any of them.

## Decision

The demonstration harness is a bounded in-house investigator loop, delivered as
`src/sre_agent/investigator/`, consuming the gateway with a configurable base URL, a
gateway credential and a governed alias, and holding no provider secret.

The loop is a stateless reducer. Given an incident state and an objective it returns one
validated outcome: use a tool, propose a hypothesis, propose a mitigation, request a
human, or conclude. Tool selection is emitted as structured output and validated before
execution; a tool absent from the authorized capabilities and evidence citations absent
from the received state are both rejected. The loop is bounded by an explicit step budget
whose exhaustion escalates to a human. An authorization denial is recorded as a decision
rather than raised as an exception and never produces a state change.

Orchestration stays with the declarative workflow of HT-INC-01 and its runtime in
HT-INC-02. Authorization stays with the gateway. Durable state stays with the incident
plane. The harness returns artifacts and never writes them.

Tool invocation is reached through an `EvidenceProvider` port with a fixture
implementation and a gateway-backed implementation, so harness delivery does not depend
on the gateway's tool surface arriving first.

## Consequences

The tool loop, context assembly and output validation are owned by this repository and
remain inspectable, which is what the governance thesis of the project requires. No
second provider abstraction sits above the gateway, so every model call is one auditable
gateway request and the release criterion that all consumption flows through the gateway
cannot be bypassed by an integration. The loop is small because orchestration,
authorization and persistence live elsewhere.

Tool use requires a governed invocation surface that does not exist in contract 1.2.0.
Until it does, the fixture provider supplies recorded evidence, and those fixtures are
required inputs of HT-DEMO-01 and the deterministic tests of HT-QA-03 rather than
throwaway scaffolding. Prompted tool selection carries a parsing failure mode that
native tool calling does not; it is bounded by schema validation, a single retry, and
escalation on a second failure.

This decision is coupled to contract 1.2.0. If the contract later carries `tools` and a
tool-call output type, a framework becomes viable again and this ADR should be revisited
rather than silently retained.

## Alternatives

LangChain was rejected because its core value is provider abstraction and integration
breadth, which duplicates the gateway, obscures per-call evidence and creates a path to
reach a provider directly.

LangGraph was rejected despite being the strongest candidate on merit, because the
project already has an orchestrator. Release criteria require flow, state and decisions
in versioned YAML with a resumable snapshot; adopting LangGraph means maintaining a
second representation of one process or abandoning an approved criterion, and its
checkpointer would become a second source of truth for state.

PydanticAI and the OpenAI Agents SDK were rejected on the gate alone. Pi Agent, the
candidate preferred by the solution design, was rejected on the same gate; its internals
were not evaluated further because a spike must not become open-ended implementation
once its question is answered.

Building a generalist harness was rejected as explicitly out of scope. Deferring the
decision until the contract is extended was rejected because it would block HT-HAR-01
behind work owned by another person on a saturated critical path.

## Deferred

Sub-agents, handoffs, memory across incidents, streaming, automated evaluation of
hypothesis quality, real mitigation execution, and multi-provider fallback are deferred.
The governed tool invocation surface is deferred to the gateway and tracked separately.

## Supersedes

None.

## Links

- `docs/spikes/ht-06-harness-evaluation.md`
- `scripts/ht06_harness_poc.py`
- `schemas/releases/1.2.0/json-schema/http/responses-request.schema.json`
- `schemas/adrs/ADR-001-responses.md`
