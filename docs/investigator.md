# Investigator harness

The bounded investigation loop of issue #185, decided in
[ADR-007](adrs/ADR-007-harness.md) and specified in
`openspec/changes/issue-185-investigator-harness/`. It lives in
`src/sre_agent/investigator/`, takes an incident context and an objective, talks to the
gateway through `POST /v1/responses` and returns a validated result. It never writes
incident state: the incident runtime applies the result (#35).

## Configuration

| Variable | Value |
|---|---|
| `INVESTIGATOR_GATEWAY_URL` | Gateway base URL, for example `http://api:8000` |
| `INVESTIGATOR_GATEWAY_API_KEY` | Key of a gateway principal, such as the seeded `incident-harness` |
| `INVESTIGATOR_MODEL_ALIAS` | Governed model alias, for example `triage-agent` |

Those are the only values the harness reads. It holds no provider or MCP secret; the
provider key stays in the gateway's own environment. Changing the gateway or the alias is
a configuration change.

## Results

Each run ends with one `terminated_reason` of `run-state`:

| Status | When |
|---|---|
| `completed` | The model proposed a cited hypothesis, a mitigation or a conclusion |
| `needs_human` | The model asked for a person, or the gateway answered an unexpected status or body |
| `invalid_output` | Two consecutive answers were not one valid action or cited unknown evidence |
| `denied` | The gateway answered 401 or 403, or the model asked for an unauthorized tool |
| `upstream_unavailable` | The gateway failed twice (network, timeout or 5xx), or a tool failed |
| `max_steps` | Six turns passed without a final answer |

The limits (6 steps, 45 s per gateway call, 10 s per tool, one retry of each kind) are
fixed in the change's `design.md`.

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
