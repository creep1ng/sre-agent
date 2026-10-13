# Investigator harness

The bounded investigation loop of issue #185, decided in
[ADR-007](adrs/ADR-007-harness.md) and specified in
`openspec/changes/issue-185-investigator-harness/`. It lives in
`src/sre_agent/investigator/`, takes an incident context and an objective, talks to the
gateway through governed Responses and MCP endpoints, and returns a validated result.
The loop remains stateless; on an `investigate` run start, the application composition
root dispatches it after the initial `start_investigation` transition and applies its
result through the incident runtime/unit of work. Other start objectives and read-only
resume do not dispatch this producer.

## Configuration

| Variable | Value |
|---|---|
| `INVESTIGATOR_GATEWAY_URL` | Gateway base URL, for example `http://api:8000` |
| `INVESTIGATOR_GATEWAY_API_KEY` | Key of a gateway principal, such as the seeded `incident-harness` |
| `INVESTIGATOR_MODEL_ALIAS` | Seeded logical model alias, `triage-agent` |

Those are the only values the harness reads. It holds no provider or MCP secret; the
provider key stays in the gateway's own environment. Changing the gateway or the alias is
a configuration change.

## Results

The investigator's internal result status describes the bounded loop:

| Status | When |
|---|---|
| `completed` | The model proposed a cited hypothesis, a mitigation or a conclusion |
| `needs_human` | The model explicitly requested human review, or the gateway rejected the response contract |
| `invalid_output` | Two consecutive answers were not one valid action or cited unknown evidence |
| `denied` | The gateway answered 401 or 403, or the model asked for an unauthorized tool |
| `pre_dispatch_rejected` | The MCP gateway rejected the tool request with HTTP 422 before upstream dispatch |
| `upstream_unavailable` | A gateway or tool call was unavailable, timed out, or returned a retryable error |
| `max_steps` | Six turns passed without a final answer |

The limits (6 steps, 45 s per gateway call, 10 s per tool) are fixed in the change's
`design.md`. A timeout, network error, or 5xx is not automatically retried: the remote
call may have completed even when its response was lost.

The run timeline records a durable `dispatch_receipt`: a committed `intent/pending`
before a governed call, followed by one terminal `success`, `confirmed_failure`, or
`unknown` outcome. Pending is not terminal; a concurrent idempotent start leaves an
active dispatch alone. On a subsequent exact idempotent start replay after a process
interruption, a still-pending receipt becomes `unknown`. Terminal outcomes are immutable
on replay, so the service never repeats an ambiguous external call. Receipt metadata contains only correlation IDs and bounded
status/reason codes, not prompts, model output, credentials, or raw tool arguments.
An MCP HTTP 422 contract rejection is a `confirmed_failure`: validation runs before the
upstream tool call, so no external effect was dispatched. Transient or ambiguous failures
remain `unknown`.

A cited hypothesis maps to the existing `continue_investigation` transition. A proposed
mitigation uses the existing `propose_mitigation` preconditions and creates a pending,
identified artifact. `request_human` and `conclude` have no transition in this workflow;
their validated result is recorded without inventing a domain-state transition.

Governed MCP discovery includes the JSON Schema generated from each tool's strict runtime
input model, but only for tools with a direct invocation grant. The investigator passes
those schemas to the model; the gateway still validates every invocation against the same
models before any upstream call.

When a cited hypothesis is the valid answer on the last allowed turn, there is no budget
for `continue_investigation`. The runtime records the validated hypothesis and its evidence
references with the successful dispatch receipt as one event-only result; it does not
fabricate another turn or change incident state. Runtime transitions and dispatch receipts
share a run-scoped PostgreSQL transaction lock. A transition emitted by an investigator
must still see that dispatch's pending intent before it can update incident state, so a
late provider response cannot replace a terminal `unknown` receipt.

## Skills

A request pins exact Skill versions in `skills` (issue #32). The harness resolves them through
`GET /v1/skills/{skill_id}/{version}/resolve` with the same key, never from the checkout, and again
before every model call and retry, without cache. The result lists each version with its digest,
dependencies and resolution request id, naming its `skills.resolve` audit event; resuming passes the
digest back. 401, 403 and 404 end the run as `denied`; a 5xx, network error or timeout, retried
once, as `upstream_unavailable`; another body or digest as `needs_human`. Skills grant no tools.

## Deterministic demonstration

`scripts/investigator_demo.py` runs six scenarios against a local demo gateway. The stub
validates each request against the Responses request contract of the running release,
rejects the restricted key with 403 and answers with scripted model outputs in the
contract's response shape. Evidence comes from the fixture provider, labeled
`source: fixture`.

    docker compose --env-file .env.example -p issue185 --profile checks run --build --rm \
      --no-deps python-checks python scripts/investigator_demo.py

| Scenario | Expected status |
|---|---|
| Valid context and objective: a tool, then a cited hypothesis | `completed` |
| Invalid output twice | `invalid_output` |
| Citation outside the context, twice | `invalid_output` |
| Tool not authorized | `denied`, the provider is not called |
| Gateway denial with the restricted key | `denied`, one gateway call |
| Step budget exhausted | `max_steps` after six turns |

Every scenario runs with a provider key in the environment; the output shows it never
reaches the gateway, that no request carries `turn_id` and that the incident fixture is
unchanged. The command ends with `RESULT: all scenarios as expected` or exits non-zero.

What is simulated: the gateway answers and the evidence. What is real: the harness code,
its HTTP client and the contract validation of every request. A run against the real
gateway with a live model is a separate step and needs the provider key in the gateway's
`.env`.
