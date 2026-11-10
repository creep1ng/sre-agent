# Interrupt policy (#771)

Silence is the default. Every event that comes in ends in one recorded decision, and only
`interrupt` writes to the operator's chat at once. The policy decides when to ask a person,
never what is allowed: grants and approvals stay where they are.

| Event | Decision | Rule | When |
| --- | --- | --- | --- |
| Alert episode starts firing | `remember` | `investigating` | First time; the investigation's result decides. |
| Alert episode starts firing | `ignore` | `repeat` | Same rule and service fired within the last hour. |
| Alert episode resolves | `remember` | `recovered` | It was firing. |
| Alert episode resolves | `ignore` | `resolved_unseen` | `resolved` arrived without a `firing`. |
| Deploy or rollback recorded | `digest` | `change_recorded` | Always (#772 will watch it). |
| CI result recorded | `remember` | `ci_result` | Always. |
| Investigation result | `interrupt` | `sustained_pending_decision` | Its alert still fires and a mitigation waits for approval, the investigator asks for a person, or it ended without a conclusion. |
| Investigation result | `digest` | `recovered_before_result` | Every alert of the incident resolved before the result. |
| Investigation result | `digest` | `concluded_without_decision` | Still firing, nothing to decide. |
| Investigation result | `interrupt` | `requested` | A person started the run: they asked for the answer. |

## Where it runs

Migration `20261030_771` adds `incident.event_decisions` (append-only, one row per
`(event_kind, event_id)`) and the triggers that write it in the transaction that records the
event: on `incident.alert_episodes` (insert, and `status` going from `firing` to `resolved`), on
`incident.change_events` (insert) and on dispatch receipts, where it replaces the body of the
#766 function `incident.enqueue_dispatch_chat_messages()`. No code path can record an event
without its decision.

That function now queues:

- `investigation_ack` only for a run a person started; an automatic run (#765, `system` actor)
  says nothing when it starts.
- `investigation_conclusion` only when the decision is `interrupt`, except for an automatic run
  proposing a mitigation when #767's `incident.enqueue_mitigation_decision()` exists: then #767's
  decision message (cause, suspect change, proposal, buttons) is the single immediate message.

An edit is not an interrupt. When a decision on a mitigation is taken on any channel, or its
verification passes or fails, the decision message the person already has is edited in place
(`decision_update`, migration `20261102_01`; see [the Telegram channel](telegram-channel.md#editing-the-decision-message)).
That writes no `event_decisions` row and sends nothing new, so the policy does not gate it; a chat
that never got the decision message gets no edit either.

## Daily digest

The Telegram gateway queues one `daily_digest` message per linked chat each day at
`TELEGRAM_DIGEST_HOUR` (default `8`, `off` disables) in `TELEGRAM_DIGEST_TIMEZONE` (default
`UTC`). It covers the decisions taken since the previous digest (or the last day), opens with
«N eventos, M mensajes» (every decision, and the interrupts among them), then lists the
`interrupt` and `digest` decisions, grouping identical ones. A period without events sends
nothing. To queue one now, as the E2E does:

```bash
docker compose --profile telegram run --rm telegram-gateway \
  python -m sre_agent.chat.telegram digest [--until 2026-10-31T08:00:00+00:00]
```

## API

`GET /v1/event-decisions?since=&until=&decision=&limit=` (`alert.read` over
`incident_workflow/incident-response`) lists the decisions taken in `[since, until)` (default:
the last day), newest first, up to `limit` (1..200, default 100). `counts` covers the whole
period, so it matches the digest of the same period.

```json
{
  "period": {"since": "2026-10-30T08:00:00Z", "until": "2026-10-31T08:00:00Z"},
  "counts": {"events": 7, "messages": 1, "ignore": 0, "remember": 3, "digest": 3, "interrupt": 1},
  "decisions": [
    {
      "decision_id": 12, "event_kind": "investigation", "event_id": "run_…",
      "service": "sre-checkout", "incident_id": "inc_…",
      "title": "Investigación de [e2e:broken] sre-checkout: checkout-5xx-rate is firing.",
      "occurred_at": "…", "decided_at": "…", "decision": "interrupt",
      "rule": "sustained_pending_decision",
      "reason": "La alerta sigue activa y hay una mitigación esperando tu decisión.",
      "link": "/v1/incidents/inc_…/runs/run_…"
    }
  ],
  "request_id": "…"
}
```

`event_kind` is `alert`, `resolution`, `change` or `investigation`; `link` is the API path that
shows the event: `/v1/alerts/{id}/triage`, `/v1/incidents/{id}/runs/{run}`, or
`/v1/changes?service=…&since=…&until=…` with both bounds at the change's own instant.

## E2E

`scripts/run_interrupt_policy_e2e.sh` (needs `scripts/bootstrap-worktree.py`) runs the real API,
Postgres, gateway and fake Bot API, with the model and Grafana MCP scripted by
`scripts/interrupt_policy_upstreams.py`. Evidence: [`docs/evidence/issue-771/`](https://github.com/creep1ng/sre-agent/tree/0cb2ad441e4f9923f3ff6d804dc59a6cfc51aa63/docs/evidence/issue-771).
