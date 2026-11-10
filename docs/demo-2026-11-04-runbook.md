# Demo runbook — Tuesday, November 4, 2026 (evaluated demo)

> **Draft for the #730 rehearsal of 2026-11-02.** Written on 2026-11-01 and updated on 2026-11-02
> against `main` `9fa9e75e`. Several steps depend on work that is not on `main` at that SHA; each
> one is marked **Pending** with the issue or PR that delivers it. Replace every Pending marker with the command and the
> timing the rehearsal actually measured, and fill the [Rehearsal record](#rehearsal-record),
> before tagging `rc-2026-11-04`. Nothing here was run yet.

One continuous story without opening the console: a broken deploy of `sre-checkout` fires an alert
in Grafana, Midnight investigates on its own, a Telegram message brings the cause and the proposal,
one tap approves the rollback, the governed deploy-executor runs it, the agent verifies the signal
and a recovery message arrives. The postmortem stays as a draft. The console is shown afterwards
as the record of the incident, not as the entry point.

Acceptance (#730): the rehearsal is documented with SHA, time per stage and cost; **no manual
command** runs between the failure injection and the recovery message; this runbook says what to
do when a step fails and does not hide it.

## Scope and what changed since 2026-10-19

- **Service:** `sre-checkout` (#721), our own checkout beside the OTel store, between
  `demo/checkout:1.4.0` (healthy) and `1.5.0` (answers 500 to 3 of every 10 orders). It runs in the
  local demo environment (`compose.demo.yaml`, [demo-env.md](demo-env.md)); the EC2 store of the
  2026-10-19 demo does not run it. The store's `checkout` keeps its name and has no catalog.
- **Alert source:** the demo's Grafana provisions Midnight's rules and the `midnight-intake`
  contact point; `sre-checkout-orders-error-rate` (5xx share over 30 s > 10%, held 1 min, severity
  `warning` → `sev2`) posts to the API's intake, which declares the incident and dispatches the
  investigation as `system`/`grafana` with no console action ([alert-intake.md](alert-intake.md),
  #765). The hand-written alert rule is retired. Measured on 2026-10-30 in the local demo: 84.9 s
  from `1.5.0` running to the dispatch (`docs/evidence/issue-765/local-demo-intake.json`).
- **Execution:** where the API has `DEPLOY_EXECUTOR_URL`, approving the mitigation checks the
  catalog and the exact grant `sre-checkout:deployment.rollback` of `incident-harness`, then calls
  the deploy-executor, signed, audits `mitigation.execute` and tells the result in the timeline
  (#722, see [deploy-executor.md](deploy-executor.md#approve-to-execute-722)). **The stack
  `scripts/setup_sre.py` starts leaves `DEPLOY_EXECUTOR_URL` empty, so every mitigation there stays
  simulated** ([investigator.md](investigator.md)); see the Pending item in Bring-up.
- **Model:** `anthropic/claude-haiku-5.5` on provider `anthropic`, measured in #880: calls of
  1.6-8.1 s, a whole investigation 24-27 s, about USD 0.0035
  ([investigator.md](investigator.md#demo-model)).
- **Channel:** Telegram carries the acknowledgment, the conclusion with the proposal, the one-tap
  decision and the recovery message ([telegram-channel.md](telegram-channel.md), #766, #767).
- **Seed:** every setup rerun restores any seed grant a person revoked (#851). A revoke shown live
  comes back on the next setup.

## Dependencies at `9fa9e75e`

| Issue | What the demo needs from it | State on 2026-11-02 (`9fa9e75e`) |
| --- | --- | --- |
| #721 | `sre-checkout` and its `fail`/`reset` | Closed, in `main` |
| #766 | Telegram link, acknowledgment and conclusion | Closed, in `main` |
| #761 | A dispatch that cannot finish ends its run | Closed, in `main` |
| #880 | Fast, stable model for the demo | Closed, in `main` (#892) |
| #765 | Grafana → intake → incident → investigation | In `main` (stack through #820); issue still open |
| #704 | The investigation starts on declaration; a lost dispatch ends its run | In `main` (#868); issue still open |
| #722 | Approve executes the rollback through the executor | In `main` (#919-#923); issue still open. **Pending:** the setup stack does not run the executor |
| #723 | The agent verifies the signal and the incident reaches `resolved` | **Pending:** no PR found on 2026-11-02 |
| #767 | Approve or reject from Telegram with one tap | **Pending:** #894, #884, #885 open |
| #705, #707, #714, #760 | Dispatch reason, evidence verdict, short title, empty-evidence rejection | **Pending** (#707 and #760 have parts merged) |

If the executor is not wired into the demo stack, or #723 or #767 is not in `main` on the rehearsal day, the journey cannot meet
"no manual command"; record which step needed a hand and do not tag the RC.

## Prerequisites (host)

- Git, Docker Engine with Compose 2.24.4 or later, Python with `pyyaml`; the demo environment needs
  4 CPUs, 4 GB of free memory and 15 GB of disk, and ports 8090 and 9090 free on `127.0.0.1`
  ([demo-env.md](demo-env.md#prerequisites)).
- A private env file as in [setup-sre.md](setup-sre.md), with four distinct `sre_` keys,
  `SRE_OTEL_MODE=local`, a unique `SRE_SETUP_PROJECT`, free ports, `AUDIT_HMAC_KEY`,
  `DEPLOY_EXECUTOR_SIGNING_KEY`, `ALERT_INTAKE_PRINCIPAL_ID=demo-human` (the default), and for the
  paid investigation `SRE_ENABLE_PAID_LLM=1`, `OPENROUTER_API_KEY`,
  `OPENROUTER_TIMEOUT_SECONDS=30`, `TRIAGE_AGENT_MODEL=anthropic/claude-haiku-5.5`,
  `TRIAGE_AGENT_PROVIDER=anthropic` (same for `REMEDIATION_AGENT_*`;
  [investigator.md](investigator.md#demo-model)). The intake secret is not set by hand: `up`
  creates `.demo-state/alert-intake.env` and setup passes it to the API.
- `TELEGRAM_BOT_TOKEN` in the ignored `.env`, and the operator's Telegram account at hand. Never
  show the token on screen.

## Bring-up (T-60 min)

```sh
python scripts/demo_env.py up          # pinned OTel Demo, sre-checkout 1.4.0, Grafana rules, intake secret
python scripts/demo_env.py verify      # exits non-zero if a service, digest, port or MCP is wrong
python3 scripts/setup_sre.py --env-file /abs/private.env   # the API reads .demo-state/alert-intake.env
docker compose --profile telegram up -d --wait telegram-gateway
docker compose --profile telegram run --rm telegram-gateway python -m sre_agent.chat.telegram link
#   open the one-time link from the operator's Telegram account (expires in 15 minutes)
```

Grafana's rules and contact point need no extra command: `up` provisions them from
`demo/grafana/alerting/` ([demo-env.md](demo-env.md#alert-intake-765)).

**Pending (#722, #723):** the stack `setup_sre.py` starts runs no deploy-executor and leaves
`DEPLOY_EXECUTOR_URL` empty, so approval stays simulated. Needed: how the executor is started
beside that stack with `DEPLOY_EXECUTOR_URL=http://deploy-executor:8000`, and how to confirm
`GET /v1/services/sre-checkout` lists both `1.4.0` and `1.5.0` locally. Ask the maintainer before
the rehearsal.

Measure each step and write the times in the [Rehearsal record](#rehearsal-record).

## Preflight (T-30)

- API `/health/ready` 200; `demo_env.py verify` exits 0.
- `python -m sre_agent.chat.telegram links` lists exactly the operator's chat.
- Grafana (`127.0.0.1:8090/grafana`, Alerting): `sre-checkout-orders-error-rate` is `Normal` and
  the contact point is `midnight-intake`. An unauthenticated `POST /v1/alert-intake/grafana`
  answers 401.
- The console's inbox shows no firing alert. On 2026-10-30 a shared host (load ~35 on 8 CPUs)
  fired five unrelated rules with nothing injected; if any rule fires before `fail`, stop and fix
  the host load first ([alert-intake.md](alert-intake.md#rules)).
- The `incident-harness` grant `sre-checkout:deployment.rollback` (`mitigation.execute`) that
  setup creates is active ([setup-sre.md](setup-sre.md), #722).
- Consumption limits "Not configured" (a monthly budget of `0` blocks the whole workspace).

## Demo script

| Min | Action | Expected |
| --- | --- | --- |
| 0:00 | Intro: independent freelancer, several services, no SRE team; one governed agent. | — |
| 1:00 | `python scripts/demo_env.py fail --service sre-checkout` (the bad release `1.5.0` goes out). **The last command until recovery.** | 3 of every 10 `sre-checkout` orders answer 500. |
| ? | Wait. Talk about governance while Grafana's rule fires. | Grafana delivers the alert (~85 s after `1.5.0` runs on 2026-10-30); intake declares a `sev2` incident and dispatches the investigation as `grafana`; Telegram sends "Investigando inc-…". |
| ? | Telegram: read the conclusion (24-27 s of investigation in #880). | Cause and evidence summary (#766). **Pending (#767):** the proposed `deployment.rollback` to `1.4.0` with Approve and Reject; it needs the executor's catalog (see Bring-up). |
| ? | Tap **Approve**. | **Pending (#767, #722):** the gateway checks state, catalog and grant, calls the executor; `sre-checkout` runs `1.4.0`. |
| ? | Wait. | **Pending (#723):** the agent verifies the error rate recovered; the incident reaches `resolved`; Telegram sends the recovery message. |
| ? | Console: open the incident as a record (timeline, evidence, approval, execution, cost). | The postmortem is a draft; it is not approved live. |

Fill the `?` minutes from the rehearsal.

## Fallbacks

Each one breaks "no manual command"; if the rehearsal needs it, record it.

| Symptom | Action |
| --- | --- |
| No Telegram acknowledgment ~3 min after `fail` | Console → Alertas: an `sre-checkout` card as `Nueva` means intake recorded it but did not declare (check `ALERT_INTAKE_PRINCIPAL_ID` and the `demo-human` grants). No card: check the rule in Grafana's Alerting page and that setup ran after `up`, so the API has the intake secret. Last resort: `demo_env.py reset --service sre-checkout` and restart the scenario. |
| Investigation ends without a proposal (`needs_human`, `unknown`) | A run that ended is not restarted on that incident (#761); a dispatch that lost its process also ends its run (#868). Declare a new incident from the console as in the [2026-10-19 fallbacks](demo-2026-10-19-runbook.md#fallbacks). The reason in the timeline: **Pending (#705)**. |
| Approve answers but nothing changes | Without the executor the mitigation is simulated. With it, a refusal or failure (409 `precondition_failed` or `execution_failed`, 403 `operation_not_authorized`, 503 `executor_unavailable`) leaves the incident `mitigating` and the timeline says why (#722). Apply the change by hand with `python scripts/demo_env.py reset --service sre-checkout` and say so. |
| No recovery message after the rollback | **Pending (#723).** |
| Telegram does not answer | Check `python -m sre_agent.chat.telegram links`; restart the `telegram-gateway` service. Show the same steps in the console instead. |
| Provider 429/503 | Same as the [2026-10-19 runbook](demo-2026-10-19-runbook.md#fallbacks): last resort `z-ai/glm-5.3-flash` on `relace` with `OPENROUTER_TIMEOUT_SECONDS=60`. |

## Budget

**Pending:** measured cost of one investigation and of the whole rehearsal (#730 asks for it).
#880 measured about USD 0.0035 per investigation with Haiku 5.5; the 2026-10-19 demo needed under
USD 0.01 for one investigation and one draft.

## Teardown

```sh
python scripts/demo_env.py reset --service sre-checkout
docker compose --profile telegram stop telegram-gateway
python3 scripts/setup_sre.py --env-file /abs/private.env --down   # keeps volumes and audit
python scripts/demo_env.py down
```

## Rehearsal record

To fill on 2026-11-02: SHA, time per stage (injection → alert → investigation dispatched →
conclusion in Telegram → approval → execution → verification → recovery message), cost, every
manual step taken and its reason, and links to the evidence.

| Run | Code | Result |
| --- | --- | --- |
| 1 | | |

## Known gaps

To fill after the rehearsal.
