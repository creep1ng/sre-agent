# EC2 rehearsal, 2026-11-02 (M1, #730)

Full incident flow on the AWS OpenTelemetry demo, run by the parent session the maintainer
scheduled on 2026-10-31. Nothing here is on `main`: the M1 stacks are still open, so the run used
the 2026-11-01 integration branch (#924, `bed6c000`) plus the maintainer's landing review
(#877/#878), merged as `f7bda735` on `t3/rehearsal-2026-11-02`.

## Environment

- Checkout `/home/creep/workshop/midnight-demo` at `f7bda735`, Compose project `sre-midnight-demo`,
  `SRE_OTEL_MODE=aws`, model `anthropic/claude-haiku-5.5` on provider `anthropic`,
  `OPENROUTER_TIMEOUT_SECONDS=30`, paid LLM enabled only for this run.
- EC2 instance `i-0203b11cc6153be8e` (`scripts/otel_ec2.py`), up 14:01:59Z, down 14:35:55Z
  (34 min of the 2 h TTL; the budget guard accepted `up`).
- Telegram: the real bot, with the maintainer's chat linked to `demo-human` (#767).
- Fault: `otel_ec2.py fail` (`paymentUnreachable`), caught by the generic `service-error-rate`
  rule (#765). The store has no `sre-checkout`, so the broken-deploy scenario of #730 could not run
  on EC2.

## Timeline (UTC)

| Step | Time | Elapsed |
| --- | --- | --- |
| `otel_ec2.py up` | 14:01:58 | returns in 13 s |
| Store answers 200 (guest bootstrap) | 14:08:33 | 6 min 35 s |
| `prepare-mcp` | 14:08:33-14:09:14 | 41 s |
| `connect-mcp` ready (after two failures, see below) | 14:11:24 | 2 min 10 s |
| `setup_sre.py` | 14:11:38-14:12:27 | 49 s |
| BoK, Skills, chat link, Telegram gateway, RC-2 console | 14:13:10 | 43 s |
| **Fault injected** | **14:14:00** | 0 |
| Grafana alert → incident declared by `system`/`grafana`, investigation running | 14:17:18 | +3 min 18 s |
| Telegram decision message sent (🟠, Aprobar / Rechazar) | 14:17:52 | +3 min 52 s |
| Run `awaiting_human` with `approve_mitigation` | 14:17:54 | investigation 36 s |
| No tap within 12 min → approval through the API, as `demo-human` (fallback) | 14:31:34 | |
| Operator applies the mitigation: `otel_ec2.py reset` | 14:31:41 | |
| Alert resolved by Grafana | 14:33:16 | 95 s after reset |
| `verification_passed` → `resolved` | 14:33:24 | |
| Postmortem run, agent draft (18.4 s), version 1 saved and approved, `close_incident` | 14:35:11 | |

No console action and no command happened between the fault and the Telegram decision message.

## Investigation (real model)

`investigation-reasoning.json`: three evidence items — recent changes (none for `checkout`),
Prometheus (`traces_span_metrics_calls_total` by span: 4 errors on `PaymentService/Charge`, 4 on
`PlaceOrder`, verdict *supports*) and Elasticsearch logs (inconclusive). Hypothesis (medium):
`PaymentService/Charge` fails and propagates to `PlaceOrder`. Proposed mitigation: confirm in
the payment logs, then revert or restart payment; medium risk.

## Cost

7 model calls (6 investigation turns, 1 postmortem draft), all `anthropic/claude-haiku-5.5` on
`anthropic`: USD 0.008403 in total (draft USD 0.0024), 50.1 s of model latency, from
`audit_events.consumption`. Real-LLM runs: 2 of the 5 allowed (one investigation, one draft).

## Failures and gaps

1. **Manual steps remain between the fault and recovery.** The approval was made through the API
   because nobody tapped within 12 min. The mitigation was applied by the operator (`reset`),
   because the executor (#722) is not merged. Verification was a human command, because #723 is
   not merged. No recovery message exists yet. #730's criterion "no manual command between the
   fault and the recovery message" is not met.
2. **RC-2 has no verification, postmortem or closure screens.** Those steps ran through the API
   the RC-1 postmortem page uses.
3. **Investigation quality:** the same hypothesis was proposed twice, 10 s apart. The mitigation
   is generic text, not a catalog operation: there is no operation for the store's services.
4. **Incident page title:** the whole Grafana summary, in English, including the evidence hint.
   It fills the top of the page (`1-pending-incident.png`).
5. **The postmortem cannot cite the declaration:** its event id (`evt-<incident>`) does not match
   the citable pattern `evt_…`, so one timeline entry of the draft was dropped.
6. **Bring-up:** `connect-mcp` failed twice before it worked. The pinned relay image was not
   pulled (`--pull never`), and the subnet clashed with a stale network.
7. **Services `setup_sre.py` does not start:** the RC-2 console (`/app/` answered 502) and the
   Telegram gateway. Both were started by hand.
8. **Telegram after an off-channel decision:** deciding through the API did not change the
   Telegram message. Tapping it now answers with the decision already taken (#767 design).
9. **Only `checkout` fired**; `payment` stayed below its threshold. The rule's warm-up was
   skipped, so the first alert took 3 min 18 s on the fresh instance.

## Files

- `timeline.jsonl`: every observed change (alert, incident, run, Telegram outbox), polled every 5 s.
- `investigation-reasoning.json`: hypotheses, evidence and mitigation of the investigation run.
- `postmortem.jsonl`, `postmortem-draft.json`: postmortem API calls with status and time; the
  agent's draft, its cost and the dropped citation.
- `1-pending-inbox.png`, `1-pending-incident.png`: RC-2 while the decision waited.
  `2-closed-inbox.png`: RC-2 after closing ("Nada te espera", recovered card).
