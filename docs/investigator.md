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
| `denied` | The gateway answered 401 or 403, or the model asked for an unauthorized tool or BoK collection |
| `pre_dispatch_rejected` | The MCP gateway rejected the tool request with HTTP 422 before upstream dispatch |
| `upstream_unavailable` | A gateway or tool call was unavailable, timed out, or returned a retryable error |
| `max_steps` | Six turns passed without a final answer |

The limits (6 steps, 45 s per gateway call) are fixed in the change's `design.md`; the
per-tool limit is `INVESTIGATOR_TOOL_TIMEOUT_SECONDS` (below). A timeout, network error, or
5xx is not automatically retried: the remote call may have completed even when its response
was lost. The one exception is the gateway's own retry of a provider 503 (below).

### Provider 503 and tool timeout

Issue #719, from the 2026-10-19 demo (two runs lost to a provider 503, one to an Elasticsearch
timeout). Failure modes, written before the code:

| Scenario | Expected |
| --- | --- |
| The provider answers HTTP 503 to a model call within 5 s, reporting no tokens or cost | The gateway waits 1 s and sends it once more, with only the time left of `OPENROUTER_TIMEOUT_SECONDS`, so the whole call never outlasts it (30 s by default, under the investigator's 45 s). The request is not streamed, so such a 503 carries no output and no charge. The call keeps one reservation, settled once at the second answer's usage |
| The 503 took 5 s or more, or reports tokens or cost | Not retried: the provider may have worked on the request |
| The provider answers 503 twice | No third attempt: the gateway answers 503 `upstream_unavailable`, audited, and the run ends `upstream_unavailable` |
| The provider times out, drops the connection or answers 429, 500, 502 or 529 | Never retried: the provider may have accepted the request, so the outcome is ambiguous |
| The gateway answers 503 after the provider answered (audit or settlement) | Never retried by the investigator: the call was accepted and audited |
| A tool does not answer within `INVESTIGATOR_TOOL_TIMEOUT_SECONDS` | The run ends `upstream_unavailable` with the receipt's `reason_code: tool_timeout` and the diagnostic stage `tool_timeout` |

`INVESTIGATOR_TOOL_TIMEOUT_SECONDS` (default `30`, greater than 0 and at most 30) bounds each MCP
tool call the investigator makes. The cap is the gateway's own MCP transport timeout
(`MCP_TIMEOUT_SECONDS`, 30 s). Change it in `.env` and recreate `api`.

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

A denial blocks the run for a human (issue #39). A `denied` result, or an MCP discovery
answered with 401 or 403, keeps its `confirmed_failure` receipt (`governed_call_denied` or
`mcp_discovery_denied`) and, in the same transaction, the run becomes `awaiting_human` with
`pending_command` `escalate` and `terminated_reason` `denied`, through an `escalation` event
that replay applies. This is the workflow's escalation: the incident keeps its state and
version, and nothing is retried with another identity, endpoint or resource. Resuming takes
people, never a retry: an administrator must grant the denied capability again, and a human
must answer the escalation. The `escalate` command is still refused
(`src/sre_agent/incident/commands.py`), so a blocked run cannot be resumed yet.

Every outcome with a harness result also writes, in the same transaction, the run's turns as
its sensitive context: the input sent, the model output, the tool invocation when the tool
answered and the gateway request id. `GET .../runs/{run_id}/context` reads them back only with
`run.read_context`, which an administrator grants through the control plane (the demo
provisioning grants it to `demo-human`); `run.read` is not enough, a run of another incident is
404, and state, events and timeline stay safe. The same response carries `reasoning`: the
hypotheses, evidence and mitigation the incident recorded, which the war room and Decisiones
show to that reader. A dispatch
interrupted before its outcome leaves no context: its turns never came back.

A cited hypothesis maps to the existing `continue_investigation` transition. While steps
are left, the same dispatch then continues with the remaining budget and the recorded
hypothesis in its context, so the agent can reach the `evidence_sufficiency` decision again
and propose a mitigation based on it; the outcome receipt closes the dispatch only once. A
proposed mitigation uses the existing `propose_mitigation` preconditions and creates a
pending, identified artifact. Those preconditions need a recorded hypothesis with cited
evidence, so a mitigation proposed before one exists is rejected as invalid output and the
model is asked again. `request_human` and `conclude` have no transition in this workflow;
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

## BoK

A run searches only the BoK collection versions it authorizes as `bok_collection` capabilities with
action `bok.search`, each an exact `collection_id@version` (issue #34). The model asks with
`{"action": "search_bok", "collection": "...", "query": "..."}`; the harness posts it, with the same
key, to `POST /v1/bok/collections/{collection_id}/versions/{version}/search` for five fragments at
most and with no cache, so a revoked grant stops the next search. Each fragment is evidence with
`source: bok`, its collection version as `datasource_uid` and, as `query`, the producer's read of
exactly that chunk. An empty search is an answer; 401 and 403 end the run as `denied`, and a 5xx,
network error or timeout, retried once, as `upstream_unavailable` with the producer's code; another
body as `needs_human`. A failed search keeps the gateway's request id. None falls back to fixtures.

## Output language

`INVESTIGATOR_OUTPUT_LANGUAGE` (`es` by default, or `en`) sets the language of the model's prose:
hypothesis statements, mitigation descriptions, steps and verification checks, and the
request-human and conclude texts (issue #717). JSON keys, action names, tool names, ids and
`low|medium|high` stay in English. The web proxy serves the same value at `/workspace.json`, and
the console's agent postmortem draft uses it. Change the variable and recreate `api` and `web`;
nothing else changes.

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
