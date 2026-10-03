# Connecting the harness to the governed gateway

How to configure and run the investigator harness against the gateway, and how to
verify that a permitted request works and that the two rejections are safe.
Issue: #38. The harness itself is HT-HAR-RUNTIME (#185); this guide does not
change it.

## What each side holds

The harness reads three values and nothing else:

| Variable | Meaning |
|---|---|
| `INVESTIGATOR_GATEWAY_URL` | Base URL of the gateway, for example `http://localhost:8000` |
| `INVESTIGATOR_GATEWAY_API_KEY` | Credential of the harness Principal |
| `INVESTIGATOR_MODEL_ALIAS` | Declared alias, for example `triage-agent` |

No provider key and no provider address reach the harness. Changing the gateway
or the alias is configuration: `GatewaySettings.from_environment` reads those
three names and the client sends the alias, never a concrete model.

The gateway holds the rest in its own environment: `OPENROUTER_API_KEY`,
`AUDIT_HMAC_KEY`, the seeded Principal keys, and the alias route
(`TRIAGE_AGENT_MODEL`, `TRIAGE_AGENT_PROVIDER`).

## How the verification runs

Every command below starts a container. None needs Python, `curl` or a package
tool on the host: only Git, Docker and the local `.env`, which holds the secrets,
stays on the machine and is never attached anywhere.

The commands share one Compose project, `harness-gateway`, and the overlay
`compose.harness-verify.yaml`. The project name keeps this stack apart from any
other on the same machine. The overlay publishes no host port, and gives the
verification client, and only it, the two extra gateway credentials the rejection
steps need. The provider key stays in the `api` service. The project's database
is created and seeded from `.env` the first time a command needs the gateway.

## Choosing the model and the provider

The provider adapter pins routing: a single provider in `order`,
`allow_fallbacks: false` and `data_collection: "deny"`. When OpenRouter serves a
dated canonical model (for example `z-ai/glm-5.3-flash-20260826` for
`z-ai/glm-5.3-flash`), the gateway confirms the pair against the public endpoint
catalog before accepting the answer as evidence. That confirmation compares the
catalog's provider name **ignoring case** and its endpoint tag **exactly**,
against the same configured value, and requires one matching endpoint.

So `TRIAGE_AGENT_PROVIDER` must be the catalog provider name in lower case, and
that value must also be the endpoint tag or its prefix before `/`. Providers
whose tag is not derived from their display name cannot satisfy both conditions
and are unusable here: `Z.AI` (tag `z-ai`), `Sail Research`
(`sail-research/...`), `InferenceNet` (`inference-net/...`). Verified working
pairs for `z-ai/glm-5.3-flash`: `novita` and `deepinfra`.

List the providers a model can be pinned to. The catalog query carries the
provider key, so it runs inside the gateway's own container, which already holds
it; only provider names are printed:

```sh
docker compose --env-file .env -f compose.yaml -f compose.harness-verify.yaml -p harness-gateway run --rm --no-deps api python -c 'import httpx, os, sys; d = httpx.get(f"https://openrouter.ai/api/v1/models/{sys.argv[1]}/endpoints", headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}, timeout=30).json()["data"]; print("\n".join(sorted({e["provider_name"].casefold() for e in d["endpoints"] if e["tag"].split("/")[0] == e["provider_name"].casefold()})))' z-ai/glm-5.3-flash
```

A provider that is eligible can still answer `429` from its shared pool. The
adapter reports that as `upstream_unavailable` instead of falling back, which is
the intended behaviour: routing stays declared.

## Aliases are seeded once

The seed runs when the database is created. Editing `TRIAGE_AGENT_MODEL` or
`TRIAGE_AGENT_PROVIDER` afterwards does **not** reseed, and the gateway keeps
using the stored route, so a stale provider produces
`502 provider_evidence_invalid` while the configuration looks correct. Read what
the gateway actually uses. The user and the database are `POSTGRES_USER` and
`POSTGRES_DB` from `.env`; `sre_agent` is their value in `.env.example`:

```sh
docker compose --env-file .env -f compose.yaml -f compose.harness-verify.yaml -p harness-gateway exec -T db psql -U sre_agent -d sre_agent -c "select alias, concrete_model, router, inference_provider, status from resources where resource_type = 'llm_model' order by alias;"
```

To adopt a new route, replace the assignment through the governed route of the
control plane. `route` reads the alias with its current `updated_at` and sends
that value back as `expected_updated_at`, so a concurrent change answers `409`
instead of being overwritten:

```sh
docker compose --env-file .env -f compose.yaml -f compose.harness-verify.yaml -p harness-gateway --profile live-smoke run --rm live-smoke python scripts/verify_harness_gateway.py route triage-agent z-ai/glm-5.3-flash deepinfra
```

The gateway resolves the alias on every request, so the next one uses the new
route without a restart. Do not recreate the environment to adopt a route:
removing the project's volumes deletes its database, audit trail included.

## One permitted request

```sh
docker compose --env-file .env -f compose.yaml -f compose.harness-verify.yaml -p harness-gateway --profile live-smoke run --build --rm -e RUN_OPENROUTER_LIVE_SMOKE=1 live-smoke
```

The smoke sends one request with the harness credential and validates the answer
against the JSON Schema of the contract release the gateway runs, so it cannot
drift from the published contract. It also checks the routing metadata, that the
consumption evidence is complete, and that the response never echoes the client
credential. The container receives a presence flag for the provider secret, not
the secret.

## The harness end to end

```sh
docker compose --env-file .env -f compose.yaml -f compose.harness-verify.yaml -p harness-gateway --profile live-smoke run --rm live-smoke python scripts/verify_harness_gateway.py check
```

`check` drives the harness's own `GatewayClient` through seven steps and prints
one JSON line for each, with status codes, error codes and request ids; never a
credential or the model's text. It refuses to run if the provider key is visible
to it. Expected, in order:

| Step | Expected |
|---|---|
| permitted request | `200` with the harness credential, alias `triage-agent`, consumption `complete` |
| alias-only change | `200` for `remediation-agent`: the same client code, only the alias differs |
| principal without grant | `403` `resource_unavailable`, with no provider call |
| credential issued | `201`: a new credential for `incident-harness`, issued by the admin through the control plane |
| before revocation | `200` with that credential |
| credential revoked | `204` |
| after revocation | `401` `authentication_failed` with the same credential |

The last line is `RESULT: every step as expected`, and the command exits 0 only
then. The same credential before and after the revocation shows that the refusal
comes from the revocation, not from an invalid value. Three steps reach the
provider; the two rejections never do. Each run issues its credential with a new
idempotency key and revokes it, so the check can be repeated.

In the harness, both rejections arrive as `GatewayError("denied", status)` and
the run ends with `terminated_reason = denied`: no tool runs and no incident
state changes.

## Correlation

The request ids that `check` prints are the keys of the audit trail. The
incident, run and task travel as HMAC references, never in clear, and only the
requests that reached the provider carry consumption. The rows from `check`
share one incident reference; the smoke sends no incident context, so its row
has none:

```sh
docker compose --env-file .env -f compose.yaml -f compose.harness-verify.yaml -p harness-gateway exec -T db psql -U sre_agent -d sre_agent -c "select correlation->>'request_id' as request_id, stage, outcome, response_status, left(correlation->'incident_ref'->>'digest', 12) as incident_ref, consumption->>'availability' as consumption from audit_events where operation = 'responses.create' order by occurred_at;"
```

## Cleaning up

```sh
docker compose --env-file .env -f compose.yaml -f compose.harness-verify.yaml -p harness-gateway --profile live-smoke stop
```

It stops this project's containers and nothing else. The project's volume keeps
the database, so the next run starts from the same seeded route and audit trail;
no command in this guide removes a volume.

## Acceptance

| Criterion | Evidence |
|---|---|
| CA1 | The permitted request returns `200` with `requested_model_alias`, `router`, `inference_provider` and consumption; the verification client refuses to run where the provider key is visible, and the overlay never gives it one |
| CA2 | Base URL and alias come from `INVESTIGATOR_GATEWAY_URL` and `INVESTIGATOR_MODEL_ALIAS`: `check` changes only the alias with the same client code, and `route` changes the assignment in the gateway, not in harness code |
| CA3 | Revoked credential answers `401`; Principal without grant answers `403`, both with no provider call |
| CA4 | Each `request_id` from `check` is an audit row with HMAC references to the incident, run and task, and consumption only where the provider was called |
| CA5 | Every command above runs against the integrated SHA; the smoke and `check` complement each other and neither replaces the other |
