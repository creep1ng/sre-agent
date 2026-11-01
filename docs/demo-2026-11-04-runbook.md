# Demo runbook — Tuesday, November 4, 2026 (evaluated demo)

> **Draft for the #730 rehearsal of 2026-11-02.** Written on 2026-11-01 against `main` `813d0892`.
> Several steps depend on pull requests that were still open at that SHA; each one is marked
> **Pending** with the PR that delivers it. Replace every Pending marker with the command and the
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
- **Alert source:** Grafana delivers its alerts to the API's intake, which opens the incident and
  dispatches the investigation with no console action (#765). The hand-written alert rule is
  retired.
- **Execution:** approving the mitigation calls the deploy-executor, signed, with an exact grant
  `sre-checkout:deployment.rollback` for `incident-harness` (#722, see
  [deploy-executor.md](deploy-executor.md#approve-to-execute-722)). The 2026-10-19 demo applied
  the mitigation by hand; this one does not.
- **Channel:** Telegram carries the acknowledgment, the conclusion with the proposal, the one-tap
  decision and the recovery message ([telegram-channel.md](telegram-channel.md), #766, #767).
- **Seed:** every setup rerun restores any seed grant a person revoked (#851). A revoke shown live
  comes back on the next setup.

## Dependencies at `813d0892`

| Issue | What the demo needs from it | State on 2026-11-01 |
| --- | --- | --- |
| #721 | `sre-checkout` and its `fail`/`reset` | Closed, in `main` |
| #766 | Telegram link, acknowledgment and conclusion | Closed, in `main` |
| #761 | A dispatch that cannot finish ends its run | Closed, in `main` |
| #765 | Grafana → intake → incident → investigation | **Pending:** stack #816 → #836 → #817 → #837 → #882 → #818 → #838 → #819 → #839 → #820 |
| #722 | Approve executes the rollback through the executor | **Pending:** #921, #919, #920 |
| #723 | The agent verifies the signal and the incident reaches `resolved` | **Pending:** no PR found on 2026-11-01 |
| #767 | Approve or reject from Telegram with one tap | **Pending:** #894, #884, #885 |
| #705, #707, #714, #760 | Dispatch reason, evidence verdict, short title, empty-evidence rejection | **Pending** (#707 and #760 have parts merged) |

If any of #765, #722, #723 or #767 is not in `main` on the rehearsal day, the journey cannot meet
"no manual command"; record which step needed a hand and do not tag the RC.

## Prerequisites (host)

- Git, Docker Engine with Compose 2.24.4 or later, Python with `pyyaml`; the demo environment needs
  4 CPUs, 4 GB of free memory and 15 GB of disk, and ports 8090 and 9090 free on `127.0.0.1`
  ([demo-env.md](demo-env.md#prerequisites)).
- A private env file as in [setup-sre.md](setup-sre.md), with four distinct `sre_` keys,
  `SRE_OTEL_MODE=local`, a unique `SRE_SETUP_PROJECT`, free ports, `AUDIT_HMAC_KEY`,
  `DEPLOY_EXECUTOR_SIGNING_KEY`, and for the paid investigation `SRE_ENABLE_PAID_LLM=1`,
  `OPENROUTER_API_KEY` and the timeout the 2026-10-19 runbook explains
  (`OPENROUTER_TIMEOUT_SECONDS`, [investigator.md](investigator.md)).
- `TELEGRAM_BOT_TOKEN` in the ignored `.env`, and the operator's Telegram account at hand. Never
  show the token on screen.

## Bring-up (T-60 min)

```sh
python scripts/demo_env.py up          # pinned OTel Demo plus sre-checkout at 1.4.0
python scripts/demo_env.py verify      # exits non-zero if a service, digest, port or MCP is wrong
python3 scripts/setup_sre.py --env-file /abs/private.env
docker compose --profile telegram up -d --wait telegram-gateway
docker compose --profile telegram run --rm telegram-gateway python -m sre_agent.chat.telegram link
#   open the one-time link from the operator's Telegram account (expires in 15 minutes)
```

**Pending (#765, #818):** the command that provisions the per-service rules in the demo's Grafana
and points its contact point at the API's intake, and how to confirm Grafana can reach it.

**Pending (#722):** how the deploy-executor is started for the demo and how to confirm
`GET /v1/services/sre-checkout` lists both `1.4.0` and `1.5.0` locally.

Measure each step and write the times in the [Rehearsal record](#rehearsal-record).

## Preflight (T-30)

- API `/health/ready` 200; `demo_env.py verify` exits 0.
- `python -m sre_agent.chat.telegram links` lists exactly the operator's chat.
- **Pending (#765):** Grafana's rule for `sre-checkout` is `Normal`, and a test delivery reaches
  the intake.
- **Pending (#722):** the `incident-harness` grant `sre-checkout:deployment.rollback`
  (`mitigation.execute`) is active.
- Consumption limits "Not configured" (a monthly budget of `0` blocks the whole workspace).

## Demo script

| Min | Action | Expected |
| --- | --- | --- |
| 0:00 | Intro: independent freelancer, several services, no SRE team; one governed agent. | — |
| 1:00 | `python scripts/demo_env.py fail --service sre-checkout` (the bad release `1.5.0` goes out). **The last command until recovery.** | 3 of every 10 `sre-checkout` orders answer 500. |
| ? | Wait. Talk about governance while Grafana's rule fires. | **Pending (#765):** Grafana delivers the alert; intake opens the incident and dispatches the investigation; Telegram acknowledges. |
| ? | Telegram: read the conclusion. | **Pending (#766, #767):** cause, evidence summary and the proposed `deployment.rollback` to `1.4.0`, with Approve and Reject. |
| ? | Tap **Approve**. | **Pending (#767, #722):** the gateway checks state, catalog and grant, calls the executor; `sre-checkout` runs `1.4.0`. |
| ? | Wait. | **Pending (#723):** the agent verifies the error rate recovered; the incident reaches `resolved`; Telegram sends the recovery message. |
| ? | Console: open the incident as a record (timeline, evidence, approval, execution, cost). | The postmortem is a draft; it is not approved live. |

Fill the `?` minutes from the rehearsal.

## Fallbacks

Each one breaks "no manual command"; if the rehearsal needs it, record it.

| Symptom | Action |
| --- | --- |
| No Telegram acknowledgment several minutes after `fail` | Check the incident list in the console. If there is no incident, the intake did not receive the alert: **Pending (#765)** how to inspect deliveries. Last resort: `demo_env.py reset --service sre-checkout` and restart the scenario. |
| Investigation ends without a proposal (`needs_human`, `unknown`) | A run that ended is not restarted on that incident (#761); the timeline names the reason (#705). **Pending:** how to start a new attempt. |
| Approve answers but nothing changes | The executor failed or answered `execution_unknown`: the incident stays `mitigating` and the timeline shows it (#722). Apply the change by hand with `python scripts/demo_env.py reset --service sre-checkout` and say so. |
| No recovery message after the rollback | **Pending (#723).** |
| Telegram does not answer | Check `python -m sre_agent.chat.telegram links`; restart the `telegram-gateway` service. Show the same steps in the console instead. |
| Provider 429/503 | Same as the [2026-10-19 runbook](demo-2026-10-19-runbook.md#fallbacks). |

## Budget

**Pending:** measured cost of one investigation and of the whole rehearsal (#730 asks for it). The
2026-10-19 demo needed under USD 0.01 for one investigation and one draft.

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
