# Demo runbook — Monday, October 19, 2026, 17:00 Bogotá (22:00Z)

One continuous story on the real product: a live alert from the AWS OpenTelemetry demo store,
triage, a real agentic investigation (OpenRouter LLM through the governed gateway, real Grafana
MCP evidence), a human decision, verification, an agent-drafted postmortem reviewed by a human,
closure, and then the AI-governance segment. The only simulated part is **executing** the
mitigation: the operator applies it (`otel_ec2.py reset`) and the product labels it "ejecución
humana o simulada, fuera del agente".

Rehearsed end to end on 2026-10-19 (see [Rehearsal record](#rehearsal-record)). Earlier
fixture-based drafts of this runbook (T1/T2/T3 slices, `pm_demo0001`, unpublished
`run-command:2.1.0`) are obsolete: everything below runs on `main`.

## Prerequisites (host)

- Git, Docker Engine + Compose >= 2.24.4, Python 3.10+, AWS CLI with the `otel-demo` profile and
  the Session Manager plugin (user-local in `~/.local/bin` is enough), the pinned relay image
  from `docker/api.Dockerfile` already pulled (`connect-mcp` runs with `--pull never`).
- A private env file (mode 0600) as in [setup-sre.md](setup-sre.md), with four distinct `sre_`
  keys, `SRE_OTEL_MODE=aws`, a unique `SRE_SETUP_PROJECT`, free ports, explicit
  `SRE_RUNTIME_SUBNET`/`SRE_CONSUMER_SUBNET` if Docker pools are exhausted, and for the paid
  investigation: `SRE_ENABLE_PAID_LLM=1`, `OPENROUTER_API_KEY`, `OPENROUTER_TIMEOUT_SECONDS=60`
  (the investigator then waits 75 s per model call, 135 s with `OPENROUTER_MANAGEMENT_API_KEY`;
  see [investigator.md](investigator.md)),
  `TRIAGE_AGENT_MODEL=deepseek/deepseek-v4.1-flash`, `TRIAGE_AGENT_PROVIDER=decart` (same for
  `REMEDIATION_AGENT_*`). `DEMO_STATE_DIR` points at a **new** state directory per AWS instance.
- `export OTEL_DEMO_EXPECTED_ACCOUNT_ID=…` in the operator shell (private; never shown).

## Bring-up (T-60 min; the instance self-terminates 2 h after launch)

Do not launch before 15:45 Bogotá. Run from a checkout of the rehearsed `main`.

```sh
python3 scripts/otel_ec2.py up                    # returns in ~11 s; reuses an active instance
python3 scripts/otel_ec2.py connect --local-port 18690 --remote-port 8090   # keep running (store)
# WAIT until http://127.0.0.1:18690/ answers 200 (guest bootstrap pulls ~25 images, see below)
python3 scripts/otel_ec2.py prepare-mcp           # 20-50 s
setsid nohup python3 scripts/otel_ec2.py connect-mcp --state-dir "$STATE" --network sre-demo-mcp-boundary \
  --subnet 10.252.230.0/28 --local-port 18292 > connect-mcp.log 2>&1 < /dev/null &
grep -q "keep this owner process running" connect-mcp.log && echo MCP-ready     # ~16 s
python3 scripts/setup_sre.py --env-file /abs/private.env                        # 26-34 s cached
docker compose --project-directory . --env-file /abs/private.env -p "$PROJECT" -f compose.yaml \
  -f compose.mcp.yaml -f "$STATE/sre-setup/$PROJECT.json" run --rm seed python -m sre_agent.persistence.seeds --seed-bok
docker compose --project-directory . --env-file /abs/private.env -p "$PROJECT" -f compose.yaml \
  -f compose.mcp.yaml -f "$STATE/sre-setup/$PROJECT.json" run --rm -v ./demo/skills:/skills:ro seed python /setup/provision_skills_demo.py
python3 scripts/otel_ec2.py extend --hours 1      # if less than ~2.5 h remain
```

`$STATE` is the absolute `DEMO_STATE_DIR` of the env file; `$PROJECT` its `SRE_SETUP_PROJECT`.
`setup_sre.py` grants demo-human `alert.*`, `incident.declare`, `run.*`, `run.read_context`
(hypothesis, evidence, mitigation and postmortem text) and `invoke` on `llm_model/triage-agent`
(postmortem draft); it probes the governed MCP calls and fails until Grafana answers (rerun it).
The seed is a reset to zero: every rerun restores any seed grant a person revoked, as a new
`<grant id>-restored-N` row (#851). To keep a seed grant revoked for safety, change the seed, not
the grant; a revoke shown live in the governance segment comes back on the next setup.

**Never run `prepare-mcp` before the store answers.** In the rehearsal it ran at minute 5 while
the guest bootstrap was still pulling images; both `compose up`s raced on the `otel-collector`
name, the bootstrap aborted and only 5 of 26 containers stayed up (store and Grafana down, MCP
502 `upstream_invalid`). Recovery used the same guest compose files plus the MCP overlay
(`docker compose -p otel-demo … -f /var/lib/otel-demo-sre/compose.json up -d --pull never
--no-build` over SSM), ~2 min.

Measured on 2026-10-19: see the table in [Rehearsal record](#rehearsal-record).

## Preflight (T-30)

- API `/health/ready` 200; console 200; store 200; demo-human `GET /v1/alerts` 200 and
  `POST /v1/mcp/tools/query_prometheus` 200; admin `GET /v1/principals` 200.
- On a fresh instance the alert rule reads `no_data` until the first error exists (the error
  series is empty); that is normal. Warm-up (free, ~3 min): `otel_ec2.py fail`, see the SEV1 card,
  do **not** declare, `otel_ec2.py reset`, see it leave.
- Consumption page → "Consumption limits": both values "Not configured".
- Console tabs: store `http://127.0.0.1:18690/`; console connected as demo-human (session chip);
  governance tabs connected with the admin key.

## Demo script (~14 min journey + ~8 min governance)

| Min | Action | Expected |
| --- | --- | --- |
| 0:00 | Intro: independent freelancer, several services, no SRE team; one governed agent. | — |
| 1:00 | Store: a product → Add To Cart → Place Order works. `otel_ec2.py fail` (~12 s). Place Order again. | Order never completes (stays on the cart; `POST /api/checkout` 500, no banner). |
| 2:00 | Console → Alertas. | SEV1 · Crítica card "checkout payment calls failing: …% errors … Evidence: …" ~55 s after `fail` once the warm-up ran (up to ~2 min 15 s for the very first failure on a fresh instance). |
| 3:00 | Card → Iniciar triage. Reason, severity sev1, impact; tick "Confirmo…"; Enviar comando. | `declared` + `inc-…` link; the alert context (service, summary, time, source, severity) is prefilled. |
| 4:00 | War room → Iniciar investigación. Talk about identity, grants, alias, audit while it runs. | 1.5-3 min (91-118 s in the rehearsal). "Hipótesis actual" with confidence, "Evidencia recolectada (3-5)" with the real queries, "Ir a Decisiones". |
| 7:00 | Ir a Decisiones: read "Mitigación propuesta" (steps, risk, verification) → Aprobar mitigación (+ comment). | Receipt `approve_mitigation … verifying`; war room approvals show "Aprobado". |
| 8:00 | Operator applies it: `otel_ec2.py reset`; store Place Order. | "Your order is complete!" after ~11-15 s; the card leaves the inbox after 58-122 s (no need to wait for it). |
| 9:30 | Decisiones → Verificación estable. | Run `resolved`. |
| 10:00 | Postmortem → Abrir postmortem → Generar borrador con el agente. | Draft in 43-68 s, "Borrador del agente (triage-agent → deepseek/…, USD 0.001…)". |
| 11:00 | Edit one field → Guardar versión → Aprobar versión 1 → Decisiones link. | Version 1, review "Aprobada", close hint. |
| 12:00 | Decisiones (postmortem run) → Cerrar incidente → tick the explicit approval → submit. | Receipt `close_incident … closed`; Postmortem shows "Cerrado". |
| 13:00 | Governance segment. | See below. |

## Governance segment (~8 min)

Admin console, sidebar "Gobierno de IA": the catalog lists 10 governed resources (2 BoK
collections, workflow, 2 LLM aliases, MCP server, 2 MCP tools, 2 Skills). Repoint only
`remediation-agent` (`z-ai/glm-5.3-flash`, provider `deepinfra`); never edit `triage-agent`
(investigation and postmortem use it). Create `shop-agent` and `blog-agent`, issue one credential
each (shown once), grant each its own LLM alias, BoK collection, MCP discovery + one MCP tool (and
`shop-agent` the `incident-triage@1.0.0` Skill, action `invoke`). Then the same requests with the
two keys: discovery is filtered per agent; each reaches only its own tool, collection, Skill
(the other gets 404, non-disclosing) and alias; admin APIs 403; denied calls never reach the
provider. Audit lists every decision (`allow · grant_matched` / `deny · no_matching_grant`),
Consumption shows per-request alias, model, provider, tokens and USD. Monthly budget `0` →
next LLM call `429 consumption_limit_exceeded`; **restore it to empty at once** (it blocks the
whole workspace). Revoke `shop-bok-incident` → next BoK search 403.

## Fallbacks

| Symptom | Action |
| --- | --- |
| No card 2 min after `fail` | Place an order yourself; confirm `fail` printed `{"flags": "fail", …}`; rerun `fail`. |
| Inbox "Fuente de alertas no disponible" for more than a minute | MCP relay died: restart `connect-mcp` (remove a leftover `sre-demo-mcp-boundary-link` container and `$STATE/transport/ssm.sock` first). |
| Timeline "Investigation dispatch ended: unknown" (or `needs_human`), no mitigation; the war room keeps saying "en curso" | A run that ended cannot be restarted on that incident. Declare a new one: Triage with a new alert id (e.g. `alt-checkout-retry-1`) and the same alert context, or the same two triage commands through the API (`open_triage`, then `triage_declare`, both `expected_version: 1`; this path was rehearsed), then Iniciar investigación. Seen once in three rehearsal runs: OpenRouter answered 503 `upstream_unavailable` on the first call; transient LLM failures are not replayed by design. |
| Repeated 429/503 from the provider | Wait a minute and use the fallback above; last resort, repoint `triage-agent` to provider `novita` (31-49 s per call). |
| Agent postmortem draft fails | Retry once; the form is already prefilled from the incident events: edit, save, approve. |
| Store stops loading | The SSM forward dropped: rerun `otel_ec2.py connect …`. |

## Budget

OpenRouter key usage went from USD 0.0628 to USD 0.0801 during the whole rehearsal (USD 0.017:
five investigation starts, three agent drafts, governance calls and probes). The demo itself needs one
investigation (USD 0.002-0.005), one draft (~USD 0.0012-0.0015) and two governance calls
(~USD 0.00002): under USD 0.01.

## Teardown

```sh
python3 scripts/setup_sre.py --env-file /abs/private.env --down   # keeps volumes and audit
pkill -INT -f "otel_ec2.py connect-mcp"; pkill -INT -f "otel_ec2.py connect --local-port"
python3 scripts/otel_ec2.py down                                    # or let the TTL end it
```

## Rehearsal record

Executed 2026-10-19 11:42Z-13:11Z by the maintainer's rehearsal session, through the real console
(Playwright in the repository e2e image, `--network host`, as demo-human), with each state
transition confirmed through the API. Evidence: [docs/evidence/demo-2026-10-19/](evidence/demo-2026-10-19/)
and the two #691 captures in [docs/evidence/issue-672/](evidence/issue-672/).

| Run | Code | Result |
| --- | --- | --- |
| 1 | main `f8d1190`, click-only | Alert 101 s after `fail`; declared; investigation ended `unknown` after 2 min 42 s: with only the error-ratio summary the model queried `service.name` / `{service="checkout"}`, found nothing, low-confidence wrong hypothesis. Fixed by #691. |
| 2 | `f8d1190` + evidence sentence typed into the summary | First LLM call 503 `upstream_unavailable` → `unknown` in ~1 s. Fallback (new incident through the two triage commands) → `mitigating` in 118 s → approve → reset → store paid 14 s later, alert gone after 65 s → resolved → agent draft 43 s (USD 0.00117) → v1 approved → **closed**. |
| 3 | #691 head `73cfdf1` (= main after #691), click-only | Alert 55 s after `fail`; declared; `mitigating` in 91 s, hypothesis "Checkout's PaymentService/Charge calls are failing at a 100% error rate" (high, 4 evidence items); approve → `verifying` (approvals 1) → reset → store paid 11 s later, alert gone after 77 s → `resolved` → postmortem run → agent draft 58 s (USD 0.0015) → v1 approved → close (submit disabled until the checkbox) → **closed**. |
| 4 (final) | **main `281e779`** on a fresh instance brought up from zero, click-only | Alert 41 s after `fail`; declared; `mitigating` in 101 s (hypothesis: 50% errors on PaymentService/Charge, likely the payment dependency; medium); approve → `verifying` → reset → store paid 11 s later, alert gone after 122 s → `resolved` → agent draft 68 s (USD 0.0015; one citation dropped as not a stored event) → v1 approved → **closed** 13:11:09Z. Captures in `docs/evidence/demo-2026-10-19/` come from this run. |
| Gov | `73cfdf1` build (same tree as `281e779`) | 10 resources; `remediation-agent` → GLM 5.3 Flash/deepinfra; two principals, credentials and 9 grants in the UI; the access matrix exactly as in the segment above (MCP Prometheus 17 series vs 403, Elasticsearch 1 doc vs 403, BoK 200 vs 403, Skill 200 vs 404, other alias 403, admin 403); two allowed LLM calls 200; audit allow/deny rows; consumption per request; budget 0 → 429, restored; revoke → 403. |

Bring-up from zero (`up` → store 200 → `prepare-mcp` → detached `connect-mcp` → `setup_sre.py`
→ BoK/Skills → TTL +1 h), measured 12:48:17Z-12:56:32Z: guest bootstrap until the store answered
6 min 13 s; prepare + connect 51 s; setup 35 s; seeds and extend 18 s; **total 8 min 14 s**;
rerun with everything up 32 s. First `fail` on that fresh instance → alert after 134 s (the
error series did not exist yet); `reset` → alert gone after 58 s. Later cycles: 55 s / 64-77 s.

## Known gaps (do not click into them live)

- The incident title and the alert card show the whole alert summary, including the evidence
  hint (#691): long but intended — it is the only alert text the investigator receives.
- The close-incident approval is not listed under "Responsables y aprobaciones".
- The inbox card stays "Nueva" after the declaration; a new episode gets a new id.
- Grants "Resource" filter fails for versioned ids (BoK, Skills): filter by principal.
- A 429 budget refusal is audited as `consumption_bounds_unavailable`.
