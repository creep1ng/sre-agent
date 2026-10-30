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
| #761 A dispatch that does not end in denial leaves the run running forever and blocks retry | P1. Raised to P0 on 2026-10-28 because it causes the retry failure in #705; the maintainer lowered it back to P1 on 2026-10-29. |
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
- The DIY gaps are the details to compete on. The engine has the pieces: step budgets, dispatch
  receipts, idempotency, consumption limits and the executor catalog. Today #758, #761 and #762
  break three of them, so they are a target rather than a guarantee.
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

## Second round of decisions

The maintainer answered the review the same day. [The vision and values draft](vision.md) turns
these decisions into the criteria that order the backlog.

| Decision | Note |
| --- | --- |
| Keep the structured catalog of predefined operations and add routines composed of catalog operations, defined by the user or proposed by the agent. | Agent-proposed routines enter the catalog only after the operator approves them. |
| Add an autonomy mode for operators who want to rest from on-call: chosen operations run without approval. | It is set per operation and never adds capabilities. The catalog, not a risk model, is what prevents a deletion like PocketOS's. |
| Detection stays out of scope. Signals come in through APIs and MCP for agentic queries. Statistical per-service failure rules may come later. | Today `gateway/alerts.py` evaluates one hard-coded rule, and only while the inbox polls. |
| Two distributions: open source self-hosted for those who accept its maintenance, and a paid cloud later where the user keeps no server running and configures no bot. | Pricing is open: subscription or per successful resolution. |
| The engine, with memory and mature primitives, is the product; anyone can put their own interface on it or use ours. | |
| The maintainer implements the Telegram channel. | |
| Memory: index closed postmortems with the BoK full-text search, recall them by service and signal when an investigation starts, and keep a change log. A weekly job proposes BoK entries, skill changes or alert mutes and never applies them. | Postgres already holds incidents, hypotheses, mitigations and postmortems. |
| Deploys become change events with a 10 to 15 minute before-and-after watch: silence when healthy, one message with the change and a rollback on regression, and red CI on main goes to the digest. Dogfood it on `arte-webpage` and `frantic`. | |
| Write the vision and values of the project and order the backlog around them. | Draft in [vision.md](vision.md). |

## Open questions raised by the second round

- **No decision model exists yet.** Every mitigation requires human approval. Risk is static tags
  per catalog operation (`touches_data`, `blast_radius`, `downtime`, `reversible`) plus a level the
  model declares in its proposal. A model that judges another model's action can be wrong or be
  steered by log content, so it may decide when to ask, never what is allowed.
- **Pricing per resolution conflicts with silence.** It pays more when more breaks and when the agent
  acts instead of waiting, "success" is hard to attribute, and a freelancer's incident volume is low
  and irregular. Intercom Fin's per-resolution price works at high volume with a clear criterion.
- **Which persona the cloud plan targets first.** People on managed platforms have the least
  operational pain; people who self-host on a VPS have the most and also suffer maintaining one more
  server. Splitting plans by who runs Midnight, not by where the apps run, avoids charging the
  persona with the least pain.
- **The dogfood repositories do not exercise the executor.** `arte-webpage` verifies in GitHub
  Actions and deploys staging by hand to S3 and CloudFront with an archived rollback artifact.
  `frantic` lives on Gitea, verifies in Gitea Actions and deploys with AWS CDK by hand. Neither runs
  on Docker Compose nor emits Prometheus metrics. They fit a watch-only trial with synthetic HTTP
  checks; the rollback demo stays on `sre-checkout`.
- **Detection without rebuilding it.** Grafana alert rules provisioned in the demo stack, sent to
  Midnight through a webhook contact point, would cover the blind evaluation and remove the
  poll-only gap, with the rules living in the user's Grafana.

## Third round of decisions (2026-10-29)

The maintainer answered the second round and asked for the backlog to 2026-12-04, recorded in
[backlog-2026-12-04.md](backlog-2026-12-04.md).

| Decision | Issue |
| --- | --- |
| Catalog operations may run without approval, chosen per operation. | #769 |
| By default, operations carry a risk classification and a decision model assesses which set is safe. A spike inspired by the permission levels of Claude Code and Codex designs it first. The recommendation going in: the model may only move an operation from running alone to asking, never the reverse. | #768 |
| In the harness, the agent never sees keys or secrets but may see environment variables to diagnose. How depends on the user's infrastructure, for example secrets stored as `String` instead of `SecureString` in SSM. | #780 |
| Pricing: a flat subscription with investigations included. | |
| Plans split by who operates Midnight, not by where the apps run. | |
| Midnight ingests the observability solution the customer already has. | #765 |
| The engine is exposed through MCP and webhooks: "we give you the engine, connect it and view it wherever you want". An engineer can ask Claude through MCP for the most recurring incidents, cross them with the code and propose fixes; that does not make Midnight replaceable by Claude Code. | #777, #778 |
| Change events integrate only with GitHub Actions. Gitea is dropped: most users live on GitHub, and a single integration keeps the scope small. Other forges can still call the generic endpoint. | #770 |
| EP-10 and EP-11 come first, by 2026-11-03, when the maintainer meets a professor for feedback before the presentation. EP-13 tasks such as the vision, the feedback and the blind evaluation run in parallel. The governance bugs #758 and #759 move to M2, outside the demo path. | #784, #785, #787 |
| Horizon to 2026-12-04, with the evaluated demo on 2026-11-04 and the release candidate of #730 moved to that date. EP-8 console stories that the chat flow does not need are frozen. | #730, #732 |

## Fourth round of decisions (2026-10-29)

| Decision | Issue |
| --- | --- |
| #761 goes back to P1. | #761 |
| The vision and values are accepted. `AGENTS.md` summarizes them and asks every product change to weigh them. | #764 |
| #758 and #759 come back to M1: they are small to finish. | #758, #759 |
| The maintainer takes every issue of the new epics EP-10 to EP-13, so the rest of the team keeps EP-8, EP-9 and the bugs. | #784 to #787 |
| #487 closes if its acceptance criteria hold on `main`; otherwise the missing part is finished and merged first. | #487 |

## Pending decision: #487

Checked on `main` at `578f6316` on 2026-10-29, #487 does not meet its criteria, and most of what is
missing is frozen work:

- CA1 and CA5 hold; CA2 and CA4 hold under the scope agreed in the issue comments.
- CA7, the shared session, and the part of CA3 that depends on it wait for #486, which is frozen.
- CA6 needs the governance views to follow #57 (units 4 and 5 of `ht-web-shell.md`), about 300 to
  500 lines of governance UI, which belongs to the later teams tier.
- CA3 and CA8 lack a real-stack revoked-grant scenario, about 60 to 80 lines, on the old console
  that #715 retires.

Finishing #487 therefore means unfreezing #486 and governance work before 2026-12-04. The
alternative is to close it after moving CA7 to #486, the entry and old sidebar to #715, and CA6 to
the governance backlog. The maintainer decides.
