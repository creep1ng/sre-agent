# Investigator Harness Specification

## Purpose

Define a bounded investigation loop that consumes the gateway, validates every model action before using it and returns a result the incident runtime can apply, without writing incident state.

## Requirements

### Requirement: Return a validated result without writing state

The harness MUST accept an incident context, an objective, authorized capabilities, `incident_id` and `run_id`, and MUST return a validated result with its status, outcome, collected evidence and turns. It MUST NOT import or call persistence, incident runtime or gateway code.

#### Scenario: A valid context yields a validated outcome

- GIVEN a context in an agentic state and a model that proposes a cited hypothesis
- WHEN the harness runs
- THEN the result has status `completed`, carries that hypothesis and changes no incident state

#### Scenario: A path to state is rejected by the architecture check

- GIVEN a harness module that imports persistence code
- WHEN the import contracts are checked
- THEN the check fails

### Requirement: Bound the interpretation of model output

Each model output MUST be exactly one known action. An invalid output MUST be re-interpreted once; a second consecutive invalid output MUST end the run with `invalid_output` without running a tool.

#### Scenario: Two invalid outputs escalate

- GIVEN a model that answers twice with text that is not a valid action
- WHEN the harness runs
- THEN the result has status `invalid_output`, no outcome and no tool invocation

### Requirement: Validate tools and citations before use

A tool MUST be run only if the authorized capabilities grant it. A citation MUST name evidence or a hypothesis from the received context, or evidence collected earlier in the same run.

#### Scenario: An unauthorized tool is not run

- GIVEN a model that requests a tool absent from the authorized capabilities
- WHEN the harness runs
- THEN the result has status `denied` and the evidence provider is not called

#### Scenario: An unknown citation is rejected

- GIVEN a model that cites an evidence id absent from the context and from the run
- WHEN the harness validates the output
- THEN the output is treated as invalid

### Requirement: Bound the investigation

The run MUST stop when the step budget is exhausted, with status `max_steps`, and MUST NOT call the gateway again.

#### Scenario: The budget runs out

- GIVEN a model that requests an authorized tool on every turn
- WHEN the step budget is reached
- THEN the result has status `max_steps` and the number of turns equals the budget

### Requirement: Treat a gateway denial as a block

A 401 or 403 from the gateway MUST end the run with status `denied`, without retry and without any other model call.

#### Scenario: The restricted credential is denied

- GIVEN the credential of a principal without a grant for the alias
- WHEN the harness runs
- THEN the result has status `denied` and no outcome

### Requirement: Configure only the gateway connection

The gateway base URL, the gateway API key and the model alias MUST come from configuration. The harness MUST NOT read provider or MCP secrets.

#### Scenario: A new alias needs no code change

- GIVEN a second valid alias
- WHEN only the alias variable changes
- THEN requests carry the new alias and the result is validated as before

### Requirement: Correlate every turn

Every gateway request MUST carry `incident_id`, `run_id` and a `task_id` derived from the turn, and MUST NOT carry `turn_id`. Evidence served by a fixture MUST carry `source: fixture`.

#### Scenario: A turn is traceable to the gateway audit

- GIVEN a completed run
- WHEN its turns are read
- THEN each `task_id` equals its `turn_id` with the `turn_` prefix replaced by `task_`
