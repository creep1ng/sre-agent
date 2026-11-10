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

Resolved on 2026-10-31: #487 stays in scope, see the fifth round.

## Fifth round of decisions (2026-10-31)

The maintainer reviewed the work shipped on 2026-10-30 and the local run of #765.

| Decision | Reason | Issue |
| --- | --- | --- |
| The new console (`web/incident-console`, served at `/app/`) is the UI used from now on. The console stories frozen on 2026-10-29 that the chat-first flow needs come back to M1. | The features shipped on 2026-10-30 (verdict per evidence, recalled memories, dispatch causes, change events) were visible only in the old war room, so they could not be shown in the UI the product will use. | #703, #708, #709, #710, #711, #715 |
| #487 stays in scope. Administration is re-evaluated inside `/app`, starting with the annotation session of #728 with the maintainer. One session serves operations and administration, which makes the SharedWorker stack of #486 obsolete. | This reverses "governance stays as it is" of 2026-10-28 for the solo tier's own settings: credentials, integrations, grants, audit and consumption. The solo admin still has to configure them. Multi-team governance stays out. | #487, #728, #847 |
| The seed is a reset to zero: it restores the seed grants a human revoked and leaves an audit record of it. | Follow-up to #823: after #759 a revoked grant can be granted again, and the seed must return the demo to a known state. | #759, #823 |
| The OTel store's topology goes into the BoK as content, not as a Skill. | The BoK informs the mechanism and measurements support the hypotheses. BoK entries and recalled memories never count as measured evidence. | #718, #831 |
| Change events appear in the console's incident story, and later in the outbound webhooks and the MCP server. | A backend-only capability cannot be demonstrated. | #770, #777, #778 |
| Correlating cascading alerts into one incident, and a minimum of failed spans in the error-rate rules, wait until after the demo of 2026-11-04. For the demo, a `paymentFailure` opens two incidents, `payment` and `checkout`. | The local run of 2026-10-30 measured both alerts and both investigations; the correlation criterion must be decided before it is built. | #845 |
| The evidence for the `paymentFailure` criterion of #765 must come from the OTel demo on EC2. The local run of 2026-10-30 is recorded but does not close it. | The account's AWS Budget of USD 10 per month currently blocks the EC2 run. | #765 |
| PRs that add Alembic revisions are renumbered and chained before each merge. | Several stacks each added `20261030_01`; merging them broke `main` until #846. | #846 |
| The investigator's model-call timeout follows `OPENROUTER_TIMEOUT_SECONDS`. | A fixed 45 s cut calls the provider may take 60 s to answer. | #843, #844 |
| The local OTel demo gives `product-catalog` and `checkout` 64 MiB of memory instead of upstream's 20 MiB. | At 20 MiB the store starves and fires false alerts. | #818 |

## Sixth round of decisions (2026-11-02 and 2026-11-03)

The maintainer walked the demo candidate on the EC2 OTel demo and set the scope of the evaluated
demo of 2026-11-04. The value column names the value of [the vision](vision.md) each decision
serves. Checked on `main` at `3961b304`.

| Decision | Reason | Value | Issue |
| --- | --- | --- | --- |
| Cutoff: whatever is not on `main` by 2026-11-03 23:00 UTC ships after the tag `rc-2026-11-04`. | A smaller change that lands beats a complete one that misses the demo. | 6 | #870 |
| Manual triage is discarded: declaration stays automatic from alerts. #703 is closed. | Declaring, dismissing and linking by hand as the main path breaks "silence is the default". | 1 | #703 |
| Requesting changes or giving a reason on reject, and a CI job for `web/incident-console/e2e`, are known demo limitations. Pending. | Neither is on the demo path; the E2E suites still run in their containers. | 6 | #709 |
| #710 joins the demo: «El servicio está estable» / «Sigue fallando» on the incident page are the fallback of the agent's automatic verification. On `main` (#991). | Automatic verification can fail or be slow on EC2; a person must still be able to say the service recovered. | 3 | #710, #723 |
| #711 joins the demo: a read-only postmortem preview and «Aprobar y cerrar» in one action, with a closing timeline. On `main` (#992, #993). Inline editing and Markdown export are pending. Plan B: the previous console's `/?view=postmortem&incident_id=…` stays served. | The walkthrough ends by closing the incident from the RC-2 console. | 3, 4 | #711 |
| In live mode, `/app/incidentes` shows no simulated incidents: without an incident it opens the inbox. On `main` (#985). | The simulator's seed listed incidents that never happened. | 6 | #715, #870 |
| The actions page has no copy-signature button. On `main` (#964). | The page shows what may run and what ran; a signature to copy is not a decision. | 2 | #870, #722 |
| The demo opens on the action catalog (`/app/acciones`), and on EC2 an approval runs `flag.set` through the deploy-executor with no operator shell. On `main` (#937–#941, #950–#954, #964). | Nothing outside the catalog can run, and nothing on it runs without a person's approval. | 2, 3 | #722, #724 |
| The chat side writes the recovery message: on `resolved` it edits the decision message («Resuelto a las … · … tras la mitigación que aprobaste · ver la consola»). Verification waits in-process in the API for M1. On `main` (#933, #934, #943–#945). | One message per decision, edited, instead of a new one. | 1 | #723 |
| Milestones: #31 and #33 move to M1, #28 to M3, and the integrations of #847 move to #971 (M3). Done on GitHub. | Skills and BoK publishing matter for the investigation; MCP registration and integrations do not block the demo. | 4 | #28, #31, #33, #847, #971 |
| The investigator writes the incident's short title: a projection-policy exception for exactly one `title` field, validated server-side and shown as text. An invalid or missing title falls back to the alert's title; the title stays in the hypothesis language, so the English console shows it in Spanish (accepted for the demo). On `main` (#989, #990). | The alert's words do not say what fails; the agent's title does. | 1 | #870 |
| Verification runs 150 s after the mitigation, over a window that starts at `executed_at`. On `main` (#983). | On EC2 a 60 s delay measured a window that still held the fault. | 6 | #723 |
| The agent's catalog lists flags and their allowed values but not their current values. After a refused `flag.set`, the run gets steps to search the BoK and measure again, and the prompt asks for the BoK before naming a fault flag (options b and c). On `main` (#996–#998). | The agent must name the flag from the signals, not read the answer from the catalog. | 6, 2 | #724 |
| The `flag.set` executor contract is published as 1.1.0 after the demo. Pending: `schemas/executor/1.0.0` stays. | Publishing a contract is not on the demo path. | 5 | #724 |

## Seventh round of decisions (2026-11-03 morning)

| Decision | Reason | Value | Issue |
| --- | --- | --- | --- |
| A model writes the postmortem draft: one bounded call with strict parsing and no tools; if it fails, the record's draft stays, labelled «Borrador desde el registro» instead of «Borrador del agente». `POSTMORTEM_DRAFT=agent` in compose. On `main` (#999). This overrides the draft composed without a model of #992. | A narrative read from the record reads as a form; the fallback keeps the close working when the model fails. | 4, 7 | #711 |
| After a failed verification, the agent's own or a person's «Sigue fallando», the system starts a new investigation told what ran and failed, at most twice per incident; then it stops and sends one Telegram message saying a person is needed. Workflow rule: the system may retry, the agent may not. On `main` (#1004–#1007). This overrides "keep only «Reintentar la investigación»". | A failed mitigation should not need a person to press retry, but retries must stay bounded. | 1, 7 | #710 |
| A recovered incident reads «Resuelto» and a closed one «Cerrado» instead of «en curso»; the inbox renders code spans instead of literal backticks; the postmortem carries the agent's title. On `main` (#1000). | The walkthrough showed a resolved incident still «en curso». | 6 | #870, #711, #995 |

## Eighth round of decisions (2026-11-03 afternoon)

At about 16:10 UTC the maintainer accepted the recommendations on the five questions left open by
#1000, #999 and #1004, after a real-model rehearsal on EC2 in which the automatic verifier asked
for a person.

| Decision | Reason | Value | Issue |
| --- | --- | --- | --- |
| Every failed verification of an incident counts toward the limit of 2 re-investigations, including one after a person's manual retry. On `main` (#1004). | The bound is about the incident, not about who retried. | 7 | #710 |
| Re-investigations are silent in Telegram: they start as `system`, and the chat hears only when a decision is needed. On `main` (#1004). | Silence is the default. | 1 | #710 |
| The gave-up message is not amber, although a person is needed: amber stays on decision messages. On `main` (#1004). | Amber marks a decision waiting, and this message asks for none in particular. | 1 | #710 |
| The postmortem draft is one model call writing four sections; the impact, the probable cause's certainty grade, the timeline and the cited actions stay the record's. On `main` (#999). | In the rehearsal the real model's draft was good and appeared 9 s after `resolved`; one call bounds cost and keeps facts out of the model's hands. | 4, 7 | #711 |
| An incident in its postmortem reads «Resuelto» before its draft exists. On `main` (#1000). | The service has recovered; the draft is paperwork. | 6 | #870, #711 |
| The verifier is given the current time and the seconds since the mitigation ran. On `main` (#1009). Checked again with the real model on EC2 at 17:28 UTC: the verification ran 150 s after the approval, measured the window after the mitigation and resolved the incident on its own; the model's draft appeared 8 s later. | In the rehearsal the verifier lacked the current time and stopped for a person. | 6 | #723 |
| If that fix misses the cutoff, the tag `rc-2026-11-04` is cut anyway, with «El servicio está estable» as the documented plan B ([demo script](demo-2026-11-04-script.md#the-walk), step 6). | The manual verdict resolved the incident in the rehearsal at 16:04 UTC. | 3 | #710, #723 |
| This record and the demo script (#1008) merge before the cutoff. | The demo is run from `main`. | 6 | #870 |
| The EC2 demo gives Grafana 1G of memory, and the bootstrap retries `compose up` up to three times, 30 s apart. Approved at about 16:55 UTC; on `main` (#1011). | In the maintainer's review that day the Demo Dashboard failed and the fault could not be shown: upstream caps Grafana at 175M, a dashboard load peaks near 275M and the kernel killed it. Two of three fresh instances that day started only half the store. | 6 | #870 |

## Ninth round of decisions (2026-11-09)

After a read-only code-quality audit of `main` at `0cb2ad44`, the maintainer opened epic #1015
(clean, understandable codebase; light hexagonal architecture over the existing ports).

| Decision | Reason | Value | Issue |
| --- | --- | --- | --- |
| The previous console (`index.html`, `public/`, `styles/`) is retired: its remaining views move to `/app` and it is deleted, and the CI browser job runs the `web/incident-console` e2e instead. It waits for #715 and #711. | Two consoles split the evidence; today CI tests only the previous one. | 5 | #1019 |
| `docs/evidence` leaves git, and a local copy is kept with checksums (`~/sre-agent-evidence-archive/0cb2ad44/SHA256SUMS` on the maintainer's host, 1,014 files). Rewriting git history is not part of it. | 101.8 MB of 133 MB tracked, and its scripts and texts surface in every code search. | 7 | #1018 |
| New PR evidence, screenshots and videos, is attached to the PR body or a PR comment, for good. GitHub takes `.mp4`, `.mov` and `.webm` up to 10 MB (100 MB on paid plans); the repository is public, so attachments are readable without signing in. Video stays optional. | Storage now exists without growing git. | 7, 6 | #1018 |
| Where the code and `agent/workflows/incident-response.yaml` or `agent/schemas/` disagree on the lifecycle, the code wins and the YAML and schemas are corrected. Today the only real divergence is the `verifying` objective; the triage statuses and `pre_dispatch_rejected` are deliberate mappings and stay. | The code is what runs; those files are not published releases. | 2 | #1020 |
| Governed routes share one authentication semantics and one order, the one in [architecture](architecture.md): validate, authenticate, authorize; inactive principals are rejected on every route. Responses that change are listed per route in the PR. | Safer, already the documented rule, and one way to authenticate instead of two. | 3 | #1021 |
| The console's scenario simulator exists only behind a build variable, on in the demo compose and off in production. | The console is a client of the engine, not a second simulated engine. | 5 | #1025 |
| Milestones: cheap enabling work (#1016, #1017, #1018, #1020, #1024) in M2, the large refactors and #1019, #1025 in M3. They move if they do not fit: no academic release is left to honour. | No strict release commitments remain after the 2026-11-04 demo. | — | #1015 |
| Every issue of the epic carries quality indicators with a baseline measured at `0cb2ad44` and a target, measured by a versioned script so they can be checked after implementation. | We claim only what we measured. | 6 | #1016 |

## Administration plane decisions (2026-11-02 and 2026-11-03)

The maintainer reviewed the administration plane rewritten inside `/app/admin` in the RC-2 style.
The cutoff and the milestone moves of #31, #33, #28 and the integrations are in the sixth round above.

| Decision | Reason | Issue |
| --- | --- | --- |
| The previous administration pages under `public/admin` are removed now, Triage included, with the browser suites and the CI job that only exercised them. Their old addresses redirect to `/app/admin` and to the inbox. | Identities, permissions, models and resources, consumption and audit live in `/app/admin`; the RC-2 inbox carries triage. Two consoles for the same task split the evidence. | #487, #847, #715 |
| Publishing BoK collections leaves the limbo it had been in since sprint 5 and is built now: a governed publish route and a «Conocimiento» page in `/app/admin`. | The BoK has been readable by the agent since #332, but content entered only through the seed command, so no one could add or check a collection without the CLI. #779 also needs a write path for the BoK entries a human accepts. | #33, #779 |
| Which part of administration the individual tier sees is decided later. | It needs its own design and tests; the solo tier's scope of the fifth round still holds. | #847 |
| Publishing Skills gets its page in Administration, stacked on the administration plane: publish a version, activate or deactivate it, read its manifest. Skills and BoK come first; both are in M1. | The publish API already exists (`POST /v1/skills/versions`); without a page only the API can publish. Stacking avoids a third set of changes to the console's sidebar and routes. | #31, #33 |
| The previous console's postmortem and decisions views (`/?view=postmortem`, `/?view=decisions`) stay until #711 brings postmortem and closure to `/app`. | They are the only UI for the postmortem and for closing an incident, which the demo reaches. | #711 |
| A published BoK version keeps who published it and from where (the console, or later a #779 proposal) in its own table, through a migration, not in the audit contract. | The audit correlation is a closed, published contract; provenance belongs to the version it describes. | #33, #779 |
| Knowledge collections can be published from `.md` files or a `.zip` of them, and Skills from their `.zip` archive (a `SKILL.md` with `name` and `description`). A Skill keeps only its instructions; other files in the archive are listed as left out. | Runbooks and Skills usually already exist as files; retyping them is the friction. | #33, #31 |
| Identities can rotate and revoke an API key, and mark the key the console holds. The control plane already had both routes; the console had no screen for them. Added on 2026-11-03 (#1010). | Without it, cutting off a leaked or retired key meant calling the API by hand. | #847 |
