# Product direction after the 2026-10-28 review

Decisions taken by the maintainer on 2026-10-28, and the public evidence gathered the same day. The
post-demo backlog is being reshaped until the evaluated demo of 2026-11-04.

## Decisions

| Decision | Rationale |
| --- | --- |
| The primary persona is a freelancer or solo developer who runs several services and acts as admin by default. | Governance of identities gives this person nothing; they are admin, operator and agent owner at once. |
| AI-access governance (principals, grants, consumption, audit UI) stays as it is, apart from the bugs below. It belongs to a later team or enterprise tier. | It serves organizations that hand AI to employees, a different buyer with a different scope. |
| Risk evaluation of infrastructure actions and human approval of critical actions stay. | Conservative users want the last word on critical actions. |
| The API and the engine are the product. The console is one frontend among others and the place to get credentials and configure integrations, not the entry point. | "If I have to go to a dashboard to use your product, I'm not going to use your product." (Theo, 2026-10-28) |
| The product moves toward a background agent: it observes signals, remembers, works in the background, and talks through a chat channel with one-tap approvals. | Product principles: memory over model intelligence; instant interaction, slow work; most events end in "do nothing, remember it, don't interrupt". |

## Bugs prioritized the same day

| Issue | Priority |
| --- | --- |
| #758 Any active consumption limit makes every `/v1/responses` call answer 429 | P0 |
| #759 A revoked grant cannot be granted again | P0 |
| #760 A hypothesis is accepted although all its cited evidence is empty | P0 |
| #761 A dispatch that does not end in denial leaves the run running forever and blocks retry | P0. The maintainer said P1; it was raised because it is the cause of the retry failure in #705. |
| #762 A torn line in the deploy-executor journal causes a restart loop | P1 |
| #705 Show why a dispatch failed and allow retry | P0 |

## Public evidence

Reached: Hacker News, lobste.rs, dev.to, personal blogs, GitHub issues, and X through search snippets
only. Not reached: Reddit and Indie Hackers block the research tool. Hacker News skews toward
professional SREs rather than the persona. Voice counts are rough.

| Finding | Voices | Sources |
| --- | --- | --- |
| Agents must not hold production keys; people want scoped tokens, isolation and sign-off | ~25 | news.ycombinator.com/item?id=47911524 (PocketOS), lobste.rs/s/bfiq9k, item?id=50164831 |
| Confidently wrong root causes are the main fear of AI SRE tools | ~20 | item?id=41357765 (Parity), item?id=49185389 (HyperProbe) |
| Solo founders are never off call; they cope by buying managed services | ~15 | item?id=26203074 (2021) |
| Monitoring tools cost too much; solo devs self-host Uptime Kuma and alert to Telegram | ~10 | item?id=48265359, dev.to/driftdev/uptimerobot-raised-their-price-4-i-built-an-alternative-p57 |
| "Why not just Claude plus an MCP?" | ~8 | item?id=50009404, item?id=47702647, item?id=47049776 |
| Claude Code over SSH is already used for ops and debugging | ~8 | item?id=46854499, item?id=46587931, item?id=48421406 |
| Read-only and human-in-the-loop designs are praised, but "what makes read-only a guarantee rather than a convention?" | ~8 | item?id=49185389, item?id=48438180 |
| DIY agent-ops setups break on maintenance, a watcher that dies silently, lost messages, tool loops, runaway bills, memory bloat, and the agent rewriting its own rules | ~5 | okhlopkov.com/always-on-ai-agent-server-setup, github.com/openclaw/openclaw/issues/178558 |
| LLM-written incident reports remove the learning | ~5 | lobste.rs/s/ysxvko |
| Deploys and config changes cause most outages | ~4 | item?id=20391251, matthewswong.com/en/blog/claude-code-production-incident-debugging |
| Clients find the outage first and blame the freelancer | 3 first-hand | melapress.com/security-stories/when-a-hacked-website-puts-an-seo-freelancers-reputation-at-risk |

Disconfirming voices: Uptime Kuma takes 15 minutes to deploy (item?id=47752702); "I've gone out of my
way to ensure there will never be anything to page me about" (item?id=26203074); "If a project tells me
I have to use their interface or agentic setup, it's 95% not going to happen" (item?id=47702647).

Pricing anchors: UptimeRobot's rise from 8 to 34 USD/month drove solo developers away; PagerDuty and
OpsGenie are too expensive for a 15-engineer team (item?id=43285105); one investigation in our own
2026-10-19 rehearsal cost USD 0.002-0.005.

The five-point personal-agent post that inspired the principles could not be traced to an author.

## Implications

- Do not rebuild detection. Accept webhooks from what the persona already runs: Uptime Kuma,
  Alertmanager, Grafana.
- Compete on guarantees, not intelligence. The agent can run only catalog operations, critical ones
  need approval, and every action leaves a receipt and is never repeated when its outcome is
  ambiguous. This answers the two most common objections.
- The DIY gaps are the details to compete on. The engine already has step budgets, dispatch
  receipts, idempotency, consumption limits and the executor catalog.
- The narrower persona self-hosts client apps with Docker Compose on one to three VPS. People who
  buy managed platforms have less operational pain. The executor's Compose-only scope fits them.

## Honest evaluation protocol

- **Scenario bank.** The flagd flags of the pinned OpenTelemetry Demo 3.0.0: `paymentUnreachable`,
  `paymentFailure`, `cartFailure`, `productCatalogFailure`, `adFailure`, `adHighCpu`, `adManualGc`,
  `recommendationCacheFailure`, `imageSlowLoad`, `intlShippingSlowdown`, `emailMemoryLeak`,
  `failedReadinessProbe`. Add the broken deploy of `sre-checkout` (#721) and a no-fault control.
  `kafkaQueueProblems` is excluded because the Kafka layer is not deployed.
- **Blindness.** A third person or a seeded script picks the scenario. Neither the operator nor the
  agent knows it, and the alert carries no hint written by someone who knows the fault.
- **Precondition.** Generic error-rate and latency rules per service. Today the only rule is the
  checkout payment error rate, so most scenarios would never raise an alert.
- **Rubric, fixed before the runs.** Detection and its time; affected service; mechanism; whether
  the proposed mitigation is correct and safe; any action on an unaffected service counts as a
  severe failure; cost; interruptions sent during the no-fault control.
- **Baseline.** The same scenarios given to Claude Code with the same Grafana MCP and alert text.
- **Report.** Every run, failures included.

## Pending decisions

- Keep #761 at P0 or lower it to P1.
- Keep the 2026-10-30 release candidate of #730 or move it to 2026-11-04.
- Which EP-8 console stories to freeze.
