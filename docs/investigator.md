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

The step limit (6 steps) is fixed in the change's `design.md`; the per-tool limit is
`INVESTIGATOR_TOOL_TIMEOUT_SECONDS` (below). A gateway call follows the provider timeout:
`OPENROUTER_TIMEOUT_SECONDS` + 15 s, or 2 × `OPENROUTER_TIMEOUT_SECONDS` + 15 s when
`OPENROUTER_MANAGEMENT_API_KEY` configures the endpoint catalog (admission may fetch it before the
provider call), at most 180 s. With the demo's 60 s that is 75 s, or 135 s with the catalog, so
the run waits for a slow answer the gateway records and charges. A timeout, network error, or
5xx is not automatically retried: the remote call may have completed even when its response
was lost. The one exception is the gateway's own retry of a provider 503 (below).

### Provider 503 and tool timeout

Issue #719, from the 2026-10-19 demo (two runs lost to a provider 503, one to an Elasticsearch
timeout). Failure modes, written before the code:

| Scenario | Expected |
| --- | --- |
| The provider answers HTTP 503 to a model call within 5 s, reporting no tokens or cost | The gateway waits 1 s and sends it once more, with only the time left of `OPENROUTER_TIMEOUT_SECONDS`, so the whole call never outlasts it (30 s by default, under the investigator's gateway timeout above). The request is not streamed, so such a 503 carries no output and no charge. The call keeps one reservation, settled once at the second answer's usage |
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
active dispatch alone. A process interruption (an API restart mid-dispatch) leaves a
still-pending receipt; when the API starts again, it claims every `running` run with a pending
intent and no outcome that no live process holds, records `unknown` with `producer_interrupted`
and ends the run `needs_human` (#704). So does an exact idempotent start replay. Nothing
redispatches such a run: a person retries with a new run. A hand-off that fails before its claim
(for example the agent identity cannot be read) still claims the run and ends it with
`investigator_failed`, so no run stays `running` with no dispatcher. Terminal outcomes are immutable
on replay, so the service never repeats an ambiguous external call. Receipt metadata contains only correlation IDs and bounded
status/reason codes, not prompts, model output, credentials, or raw tool arguments.
An MCP HTTP 422 contract rejection is a `confirmed_failure`: validation runs before the
upstream tool call, so no external effect was dispatched. Transient or ambiguous failures
remain `unknown`.

A denial ends the run for a human (issues #39, #788). A `denied` result, or an MCP discovery
answered with 401 or 403, keeps its `confirmed_failure` receipt (`governed_call_denied` or
`mcp_discovery_denied`) and, in the same transaction, an `escalation` event that replay
applies sets the run `terminated` with `terminated_reason` `denied` and no pending command.
This is the workflow's escalation: the incident keeps its state and version, and nothing is
retried with another identity, endpoint or resource. The `escalate` command stays deferred
(`src/sre_agent/incident/commands.py`), so no run announces it. The way out takes people: an
administrator grants the denied capability, then a human retries with a new run.

Every other ending terminates the run (issue #761). In the same transaction as the terminal
receipt, a `run_terminated` event sets `status` `terminated` (or `completed` for `conclude`),
`pending_command` null and a `terminated_reason`: `upstream_unavailable`, `max_steps`,
`invalid_output`, or `needs_human` for the rest. This covers an interrupted dispatch replayed
as `unknown`, an exception after the claim (`investigator_failed`, only its type is logged)
and a mitigation a human sends back. The incident stays in `investigating`. Only a human
retries: `POST .../runs` with `objective: investigate` opens a new run through
`continue_investigation`, refused with 409 for an agent, beside a live run, or for the loser
of two concurrent retries. The ended run is never redispatched. The receipt and the
`run_terminated` event carry the ending's `reason_code`; the timeline projects only the codes
in `src/sre_agent/incident/reasons.py`, each with a readable cause (issue #705), and the war
room shows that cause in Spanish with the code in parentheses. An MCP tool that fails or does
not answer is `investigation_tool_unavailable`, distinct from the model provider's
`investigation_upstream_unavailable`; both store `terminated_reason` `upstream_unavailable`.

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

## Evidence verdicts

Each piece of evidence recorded with a hypothesis carries a verdict on it (issue #707):
`supports`, `contradicts` or `inconclusive`, with a one-line `finding` in the output language.
The model gives them in `verdicts` of `propose_hypothesis`, keyed by evidence id; a missing or
invalid verdict is recorded as `inconclusive`, not rejected. The harness, not the model, measures
whether a tool answered with data: a Prometheus query without series or a log query without
documents is recorded with `empty: true` and as `inconclusive`, whatever the model says. A
hypothesis that cites no measured data is invalid output (issue #760): every citation is empty
evidence, a BoK fragment (`source: bok`), which describes what should happen, not what did, or a
recalled past incident (`source: incident_memory`, #773), which describes what happened before, not
now. The
model is told why and asked again. A second such answer ends the dispatch without a hypothesis, and
its receipt carries `reason_code: investigation_no_measured_evidence`, shown in the timeline as "no
cited evidence had measured data". The fields
are optional in incident-state 1.2.0 and the run context, so earlier documents stay valid. On the
evidence the current hypothesis cites, the war room shows «Respalda la hipótesis», «Contradice» or
«No concluyente»; on any empty evidence, «No encontró nada». Reproduce it against the real API,
with a scripted model and Grafana MCP:

    C="scripts/worktree-compose -f compose.evidence-verdict-e2e.yaml"
    $C up --build --wait db api web
    $C run --rm -T seed python -m sre_agent.persistence.seeds --seed-mcp
    $C run --rm -T seed python /e2e/provision_demo.py
    mkdir -p /tmp/evidence-verdict-e2e  # default artifact dir (EVIDENCE_VERDICT_ARTIFACTS)
    HOST_UID=$(id -u) HOST_GID=$(id -g) $C --profile verdict-e2e run --rm verdict-e2e
    $C --profile e2e run --rm --no-deps -u "$(id -u)" -e HOME=/tmp -e EVIDENCE_DIR=/artifacts \
      -v "$PWD/scripts:/e2e/scripts:ro" -v /tmp/evidence-verdict-e2e:/artifacts \
      e2e node scripts/capture_evidence_verdict.mjs

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

## Recalled incidents

An `investigate` dispatch seeds the run with up to three memories of closed incidents of the
same service (issue #773, see [incident postmortem](incident-postmortem.md)). Each is evidence
with `source: incident_memory`, no `datasource_uid`, the source incident's postmortem as `query`
and its `indexed_at` as `collected_at`. The model may cite them like any other evidence. Only a
memory the outcome cites is kept in the incident evidence and in the result event's
`evidence_references`. If recall fails, the run goes on without memories and its outcome receipt
lists `memory_recall_unavailable` in `notes`.

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

## Slow provider demonstration

`compose.investigator-timeout-e2e.yaml` runs the real API, database and investigator with
`OPENROUTER_TIMEOUT_SECONDS=60` and a model that answers after 50 s
(`scripts/investigator_timeout_upstreams.py`). The run must complete and its receipt must name
the request id the gateway audited. From a worktree with `.env` and `.env.worktree`:

    scripts/worktree-compose -f compose.e2e.yaml -f compose.investigator-timeout-e2e.yaml up --build --wait db api
    scripts/worktree-compose -f compose.e2e.yaml -f compose.investigator-timeout-e2e.yaml run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
    scripts/worktree-compose -f compose.e2e.yaml -f compose.investigator-timeout-e2e.yaml run --rm --no-deps -T seed python /e2e/provision_demo.py
    scripts/worktree-compose -f compose.e2e.yaml -f compose.investigator-timeout-e2e.yaml --profile timeout-e2e run --rm --build timeout-e2e
    scripts/worktree-compose -f compose.e2e.yaml -f compose.investigator-timeout-e2e.yaml down -v --remove-orphans

The report goes to `$INVESTIGATOR_TIMEOUT_ARTIFACTS` (default `/tmp/investigator-timeout-e2e`).
