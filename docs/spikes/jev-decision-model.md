# Jev as a mitigation scorer through the governed gateway

- **Issue:** [#725](https://github.com/creep1ng/sre-agent/issues/725)
- **Type:** Spike, half-hour timebox
- **Owner:** @papiarcacamilo
- **Run:** 2026-10-24, 15:44–15:46Z, on `main` at `d039138`
- **Decision:** structured output with `remediation-agent`; Jev gets no alias of its own

## Question

> Does the gateway accept Jev's response shape (a decision model that returns scores, not
> text), and which dimensions does it return for a real mitigation proposal?

## What Jev is on OpenRouter

The issue names `typesafe/jev-latest`, and OpenRouter answers 404 for that id. Its public catalog
(469 models that day) holds one Jev entry, whose description points to a second, unlisted one:

| Id | Catalog data | Endpoints of its own |
| --- | --- | --- |
| `typesafe/jev-router` | tokenizer `Router`, output `text`; "picks the best model and reasoning effort for each request" and runs on Jev | none |
| `~typesafe/jev-latest` | tokenizer `Router`, modality `text+image->decisions`, output `decisions`; "always redirects to the latest model in the Jev family" | none |

## Calls

Every call carried the same incident and proposal: `checkout` answers 500 to 30 % of requests
since `demo/checkout:1.5.0` was deployed, `1.4.0` served cleanly for the previous 24 hours, both
images are in the local registry, and the proposal is
`deployment.rollback(service=checkout, to_tag=1.4.0)` through the governed deploy-executor. It is
the scenario of #721–#723.

| # | Call | Result | Billed |
| --- | --- | --- | --- |
| 1 | `~typesafe/jev-latest` straight to OpenRouter, outside the gateway, on `/api/v1/responses` and then on `/api/v1/chat/completions` | 400 on both: "is a decisions model and cannot be used with the chat/completions endpoint. Use the /api/alpha/decisions endpoint instead." | nothing, no generation |
| 2 | Control plane: `POST /v1/model-aliases` with `concrete_model: ~typesafe/jev-latest` | 422 `validation_error` | nothing |
| 3 | Alias `jev-router` to `typesafe/jev-router` (provider `typesafe`), `invoke` granted to `incident-harness`, then `POST /v1/responses` through the gateway | 503 `upstream_unavailable`; audited as `responses.create`, stage `upstream`, outcome `error`, consumption `unavailable` | nothing |
| 4 | `remediation-agent` (`z-ai/glm-5.3-flash` via `novita`) through the gateway, asked for one JSON object with five scores, a recommendation and a one-sentence rationale | 200; audited as `success`, content `absent`; 310 input and 970 output tokens | **0.00029764 USD**, exact |

Call 1 is the only one outside the governed path. It ran from the `api` container, the only one
holding the provider key, with `data_collection: deny` as the gateway sends it, and only to learn
what Jev answers.

## Why the gateway cannot carry Jev

Four independent reasons; any one of them is enough.

1. **Another API.** Jev answers only on OpenRouter's `/api/alpha/decisions` (call 1). The gateway
   adapter speaks `/api/v1/responses` (`OpenRouterProvider.create` in
   `src/sre_agent/gateway/openrouter.py`). Carrying Jev means a second adapter against an alpha
   contract.
2. **Another output.** The gateway accepts a completed assistant `message` with `output_text`
   content and nothing else (`_completed_output_text`; `ResponseContent.type` is
   `Literal["output_text"]` in `src/sre_agent/gateway/responses.py`). A `decisions` output fails
   as `invalid_response`.
3. **Pinned routing.** Every request pins one provider with `allow_fallbacks: false`. A response
   is accepted only when OpenRouter reports `strategy: direct` with exactly one selected endpoint of
   that provider, and any drift from the requested model must be confirmed against the catalog
   (`_selected_model`, `_catalog_match`). Both Jev entries redirect and have no endpoint of their
   own to pin. Call 3 shows it: pinned to its vendor with fallbacks off, the router found no
   eligible endpoint, and the adapter reported the routing availability failure it documents for
   issue #204 (503 `upstream_unavailable`) before anything was billed. Had OpenRouter routed it
   anyway, the evidence checks above would have refused the answer.
4. **The alias contract.** The model pattern `^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$` leaves no room
   for the `~` prefix, so Jev cannot even be registered (call 2).

Which dimensions Jev returns stays open: only a call to the alpha decisions endpoint, outside the
governed path, could tell, and it falls outside this timebox.

## Decision

**Structured output with `remediation-agent`.** The caller asks for a fixed JSON object and
validates it on its own side, as the investigator already validates its output. Nothing changes in
the gateway or its contract. Jev gets no alias of its own; reconsider only if OpenRouter moves
decisions to a stable API and the gateway contract gains a decisions output.

## What the alternative returned

```json
{
  "reversibility": 0.9,
  "containment": 1.0,
  "diagnosis_confidence": 0.9,
  "time_to_effect": 0.6,
  "regression_safety": 0.85,
  "recommendation": "approve",
  "rationale": "Los errores comenzaron exactamente con el despliegue de 1.5.0 tras 24 horas limpias de 1.4.0, lo que atribuye el fallo a la nueva versión con alta confianza, y el rollback a una imagen disponible en el registry local es una acción acotada al servicio en falla, reversible redeployando 1.5.0 y de bajo riesgo residual (salvo posible incompatibilidad con migraciones de estado), con la única demora típica del rollout."
}
```

The prompt defined every score so that 1 is the most favorable value for executing the proposal.

- The five keys, their 0–1 ranges and the recommendation enum came back exactly as asked.
- The rationale, requested as one sentence, ran to 416 characters against the 400 that the spike's
  validator allows, so the validator refused the object. Names, types and enums held; free-text
  length did not. The consumer has to bound and refuse on its side, which the investigator's
  contract validation already does for its own output.
- The rationale names a risk that none of the five dimensions captures: a rollback is unsafe when
  the newer version ran state or schema migrations.
- It came back in Spanish, following `INVESTIGATOR_OUTPUT_LANGUAGE` (#717).

## For #722 and #723

- The investigator's mitigation proposal can carry these scores inside its validated JSON.
  `mitigation.execute` keeps treating them as advice to the approving human, never as
  authorization: the exact grant per service and the human approval stay the only gates.
- Add state compatibility to the dimensions, or a short list of caveats, before the scores reach
  the war room.

## Reproduce

The pull request for #725 carries the exact containerized commands, the Compose overlay and the
output of this run. The four calls, in platform terms:

1. From the `api` container: `POST https://openrouter.ai/api/v1/responses` with
   `{"model": "~typesafe/jev-latest", "input": <proposal>, "provider": {"data_collection": "deny"}}`.
2. As `admin-human`: `POST /v1/model-aliases` with `concrete_model: ~typesafe/jev-latest`.
3. As `admin-human`: the `jev-router` alias and its `invoke` grant; then, as `incident-harness`,
   `POST /v1/responses` with `{"model": "jev-router", "input": <proposal>}`.
4. As `incident-harness`: `POST /v1/responses` with `{"model": "remediation-agent"}` and the
   scoring prompt followed by the proposal.
