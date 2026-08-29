# HT-06 — Harness evaluation

- **Issue:** [#12](https://github.com/creep1ng/sre-agent/issues/12)
- **Type:** Spike
- **Timebox:** one effective working day
- **Owner:** @papiarcacamilo
- **Outcome:** [ADR-007](../../schemas/adrs/ADR-007-harness.md)
- **Reproducible evidence:** `python scripts/ht06_harness_poc.py`

## Question

> Which harness lets an agentic client consume the gateway using only a base URL and a
> gateway credential, and leaves a reasonable path towards tools/MCP and Skills without
> us building a generalist harness?

## Method

Candidates were scored against the mandatory matrix declared in the issue. One criterion
was promoted to a **gate**: *LLM contract compatibility*. A candidate that cannot speak
the frozen contract cannot be integrated at all, so the remaining criteria would be
scored on an option that is unusable.

The gate was measured empirically rather than argued. `scripts/ht06_harness_poc.py`
starts a mock gateway that validates every request against the contract actually frozen
in `schemas/releases/1.2.0/json-schema/http/responses-request.schema.json`, then fires
the four requests a candidate harness realistically puts on the wire.

## Gate finding

Contract 1.2.0 declares `additionalProperties: false` and accepts exactly `model`,
`input`, `incident_id`, `run_id`, `task_id`. `input` is typed as a single string. The
response admits only `output[].type = "message"` with `output_text` content.

Observed behaviour:

| Probe | What sends it | Observed |
|---|---|---|
| Minimal request | Any minimal client | `200` |
| Request carrying `tools` | Every framework, once one tool is registered | `422 invalid_request` |
| Request carrying a message array | Every conversational framework | `422 invalid_request` |
| Unauthorized alias | Denial path | `403 resource_unavailable` |

The contract has no `tools` request property and no `function_call` output type, so the
model cannot be offered a tool and cannot express the intent to call one. This is not an
implementation gap: ADR-001 lists tools and conversations under **Deferred** on purpose.

**Consequence:** the agent tool loop cannot be delegated to a framework while contract
1.2.0 stands. It must live inside the harness. Any framework's tool abstraction is dead
weight here, not leverage.

### Runtime corroboration

The gate was first measured against the frozen schema. The gateway runtime landed
afterwards and independently confirms it. `src/sre_agent/gateway/responses.py` declares:

```python
class ResponsesRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")]
    input: Annotated[str, Field(min_length=1, max_length=65_536)]
    incident_id: ... | None = None
    run_id: ... | None = None
    task_id: ... | None = None
```

`extra="forbid"` rejects any unknown property, and validation runs before
authentication, so a request carrying `tools` fails with 422 without reaching a
credential. Schema and runtime agree; the finding is not an artefact of the mock.

## Comparison matrix

Scoring: **P** pass, **F** fail, **P\*** pass but the capability is unusable against the
frozen contract, **?** not verified within the timebox.

| Criterion | Pi Agent | PydanticAI V2 | OpenAI Agents SDK | Minimal in-house loop |
|---|---|---|---|---|
| **GATE — LLM contract** | **F** | **F** | **F** | **P** |
| Configurable base URL | P | P | P | P |
| Own gateway credential, no provider secret | P | P | P | P |
| Tool calling | P\* | P\* | P\* | P — implemented as validated structured output |
| MCP | ? | P\* | P\* | P — through the gateway's MCP surface once it exists |
| Skills / versioned instructions | ? | P | P | P — prompt modules per objective |
| State and hooks, `run_id`/`task_id` correlation | ? | P | P | P — the contract already carries all three fields |
| Licence and maintenance | ? | P | P | Not applicable |
| Integration complexity | High — assumes native tool calling | Medium | Medium | Low — the loop is roughly 500 lines |

Two honesty notes. First, Pi Agent's individual capabilities were not verified in depth:
once a candidate fails the gate, spending the timebox on its internals is exactly the
"open-ended implementation" the spike template forbids. Second, the `F` on the gate is
not a defect of any candidate. All three are competent tools failing a constraint
imposed by our own contract.

## Why the fallback is in scope

The solution design states that the harness should preferably reuse a modular
alternative such as pi-agent, and that the project will not compete with existing
harnesses within ten weeks. It admits, in the same sentence, a **modular *or minimal*
harness**.

A bounded incident-investigation loop is the minimal option, not a generalist harness.
It has no planner, no sandbox, no memory subsystem, no UI and no provider abstraction.
It orchestrates nothing: the declarative state machine of HT-INC-01/HT-INC-02 does that.
It authorizes nothing: the gateway does that. It persists nothing: it returns artifacts
and the state machine writes them.

## Discarded alternatives

| Alternative | Why it was rejected |
|---|---|
| **LangChain** | Its core value is provider abstraction and integration breadth. The gateway exists precisely to abstract providers and is the evaluated core of the project. Adding LangChain stacks a second provider abstraction over the first, obscures what each call did, and creates a path by which an integration can reach a provider directly, breaking the release criterion that all consumption flows through the gateway. |
| **LangGraph** | The strongest candidate on merit, and rejected for a structural reason. The project already has an orchestrator: the versioned YAML workflow. Release criteria require flow, state and decisions to be defined in versioned YAML with a resumable snapshot. Adopting LangGraph means either compiling the YAML into a `StateGraph`, which keeps two representations of one process in sync forever, or dropping the YAML and breaking an approved criterion. Its checkpointer would also become a second source of truth for state, while the design names the database as authoritative during concurrent execution. |
| **Building a generalist harness** | Explicitly out of scope in the solution design, and not achievable in the remaining sprints. |
| **Waiting for a contract extension before deciding** | Would block HT-HAR-01 behind work owned by another person on an already saturated critical path. The decision does not need the extension; the implementation of tool use does, and an evidence provider port absorbs that. |

## Consequences and follow-up work

1. The tool loop lives in the harness. Tool selection is emitted as structured output and
   validated against a schema before anything executes.
2. Tool invocation needs a governed surface that does not exist yet. Two options were
   raised with the gateway owner: extend the Responses contract to carry `tools`, or add
   dedicated MCP endpoints to the gateway. The second keeps the recently frozen LLM
   contract untouched and gives tool governance its own auditable surface.
3. The harness depends on that surface through an `EvidenceProvider` port with two
   implementations: fixtures now, gateway-backed later. Swapping them is configuration,
   so HT-HAR-01 and HT-HAR-02 are not blocked by the gateway's schedule.
4. The Python package is `src/sre_agent/investigator/`. The name `harness` is already
   taken by the contract conformance runner and must not be overloaded.
5. Contract 1.2.0 stays untouched by this spike. If it later gains `tools`, this decision
   should be revisited: a framework becomes viable again, and the trade-off changes.
