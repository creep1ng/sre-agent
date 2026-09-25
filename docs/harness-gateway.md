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

List the providers a model can be pinned to:

    curl -sS "https://openrouter.ai/api/v1/models/$TRIAGE_AGENT_MODEL/endpoints" \
      -H "Authorization: Bearer $OPENROUTER_API_KEY" \
      | python -c 'import sys,json; d=json.load(sys.stdin)["data"]; print("\n".join(sorted({e["provider_name"].casefold() for e in d["endpoints"] if e["tag"].split("/")[0] == e["provider_name"].casefold()})))'

A provider that is eligible can still answer `429` from its shared pool. The
adapter reports that as `upstream_unavailable` instead of falling back, which is
the intended behaviour: routing stays declared.

## Aliases are seeded once

The seed runs when the database is created. Editing `TRIAGE_AGENT_MODEL` or
`TRIAGE_AGENT_PROVIDER` afterwards does **not** reseed, and the gateway keeps
using the stored route, so a stale provider produces
`502 provider_evidence_invalid` while the configuration looks correct. Read what
the gateway actually uses:

    docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      -c "select alias, concrete_model, router, inference_provider, status from resources where resource_type='llm_model';"

To adopt a new route, either recreate the environment
(`docker compose --profile live-smoke down -v`) or change the alias through the
governed model-alias route of the control plane.

## One permitted request

    RUN_OPENROUTER_LIVE_SMOKE=1 docker compose --profile live-smoke run --build --rm live-smoke

The smoke sends one request with the harness credential and validates the answer
against the JSON Schema of the contract release the gateway runs, so it cannot
drift from the published contract. It also checks the routing metadata, that the
consumption evidence is complete, and that the response never echoes the client
credential. The container receives a presence flag for the provider secret, not
the secret.

## The two rejections

A Principal without a grant is refused at the boundary, with no provider call:

    curl -sS -o /dev/null -w "%{http_code}\n" "$INVESTIGATOR_GATEWAY_URL/v1/responses" \
      -H "Authorization: Bearer $RESTRICTED_HARNESS_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"model":"triage-agent","input":"Reply with one short health status."}'

Expected: `403` with `resource_unavailable`.

A revoked credential fails safely. Issue one, use it, revoke it through the
control plane, and use it again:

    NEW=$(curl -sS -X POST "$INVESTIGATOR_GATEWAY_URL/v1/principals/incident-harness/credentials" \
      -H "Authorization: Bearer $ADMIN_HUMAN_API_KEY" -H "Idempotency-Key: ht-har-01-revocation" \
      -H "Content-Type: application/json" -d '{}')
    CREDENTIAL=$(echo "$NEW" | python -c 'import sys,json; print(json.load(sys.stdin)["credential"]["credential_id"])')
    KEY=$(echo "$NEW" | python -c 'import sys,json; print(json.load(sys.stdin)["key"])')
    curl -sS -o /dev/null -w "before revocation: %{http_code}\n" "$INVESTIGATOR_GATEWAY_URL/v1/responses" \
      -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
      -d '{"model":"triage-agent","input":"Reply with one short health status."}'
    curl -sS -o /dev/null -w "revocation: %{http_code}\n" -X DELETE \
      "$INVESTIGATOR_GATEWAY_URL/v1/credentials/$CREDENTIAL" -H "Authorization: Bearer $ADMIN_HUMAN_API_KEY"
    curl -sS -o /dev/null -w "after revocation: %{http_code}\n" "$INVESTIGATOR_GATEWAY_URL/v1/responses" \
      -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
      -d '{"model":"triage-agent","input":"Reply with one short health status."}'

Expected: `200`, then `204`, then `401` with `authentication_failed`. The same
credential before and after, so the refusal comes from the revocation and not
from an invalid value.

In the harness, both rejections arrive as `GatewayError("denied", status)` and
the run ends with `terminated_reason = denied`: no tool runs and no incident
state changes.

## Acceptance

| Criterion | Evidence |
|---|---|
| CA1 | The permitted request returns `200` with `requested_model_alias`, `router`, `inference_provider` and consumption; the harness environment holds no provider secret |
| CA2 | Base URL and alias come from `INVESTIGATOR_GATEWAY_URL` and `INVESTIGATOR_MODEL_ALIAS`; the route behind the alias changes in the gateway, not in harness code |
| CA3 | Revoked credential answers `401`; Principal without grant answers `403`, both before any provider call |
| CA4 | `request_id` correlates the answer, and the consumption evidence carries its pricing context |
| CA5 | Every command above runs against the integrated SHA; the smoke complements them and does not replace them |
