# Midnight: vision and values

Proposed on 2026-10-28 and accepted by the maintainer on 2026-10-29. It states what the product is
for and the values that decide scope. Every backlog item should trace to one of these values; anything that
serves none of them waits. The decisions and public evidence behind it are in
[the product direction record](product-direction-2026-10-28.md).

## Vision

A freelancer who keeps several clients' services running can close the laptop at night. Midnight
watches the signals they already have, remembers every incident and deploy, acts only through
operations the freelancer approved in advance, and wakes them only when a human decision changes
the outcome.

## Who it is for

- **Primary user.** An independent developer who maintains services for several clients and is
  admin, operator and owner of the agent at once.
- **Open source, self-hosted.** For people who accept running and maintaining Midnight themselves,
  with their own model key.
- **Paid cloud, later.** Midnight runs the investigation; a small connector on the user's host keeps
  the credentials and executes only signed catalog operations. The user keeps no extra server
  running and configures no bot. Its first persona and its pricing are open.
- **Teams, later.** Inherits the existing governance: principals, grants, consumption and audit.

## Values

Each value names what it rules out and how we check that we keep it.

### 1. Silence is the default

The operator's attention is the scarce resource. Every event ends as ignore, remember, digest or
interrupt, and Midnight interrupts only when a human decision changes the outcome.

- Rules out: notifications for blips that recover alone, messages sent "for your information",
  and dashboards as the place where value shows up.
- Check: messages per real incident, target one; interrupts during a week without faults, target
  zero.

### 2. What is not in the catalog cannot happen

Safety is a property of the system, not of the model's judgment. The agent invokes named operations
with typed inputs, and a separate executor holds the only credentials. Risk evaluation decides when
to ask a human, never what is possible. Autonomy is set per operation.

- Rules out: a shell tool, any mode that adds capabilities, credentials inside the agent process,
  and routines that are anything other than compositions of catalog operations.
- Check: the agent process holds no Docker or cloud credentials, and adversarial alert or log
  content cannot produce an operation outside the catalog.

### 3. Every action is accountable

Every action leaves a receipt, an ambiguous outcome is never retried automatically, and every run
ends in a terminal state with a reason the operator can read.

- Rules out: runs stuck without a reason (#761), restart loops (#762), a watcher that dies
  silently.
- Check: kill the gateway and the executor at each step of the golden journey; nothing repeats,
  nothing hangs, and the operator learns what happened.

### 4. Memory has provenance; the agent proposes, the human approves

Memory is the operator's own history: incidents, hypotheses, mitigations, postmortems and deploys,
each traceable to its source. The agent never rewrites its own instructions, skills or catalog;
changes arrive as proposals the operator accepts or rejects.

- Rules out: facts extracted by a model without a source, and self-modifying prompts.
- Check: every recalled item in an investigation links to the record it came from.

### 5. The engine is the product; interfaces are clients

Every capability exists in the API first. Chat, the console and other agents through MCP are
clients of the same engine.

- Rules out: features that exist only in our UI.
- Check: the demo runs end to end from chat and the API with the console closed.

### 6. We claim only what we measured

Claims come from blind evaluations against a rubric fixed before the runs, next to a Claude Code
baseline, and reports include the failed runs.

- Rules out: alerts carrying hints written by someone who knows the fault, and pull-request
  screenshots as proof of acceptance.
- Check: the evaluation report lists every run.

### 7. Pocket-sized economics

Runtime stays under USD 1 per user per month at freelancer volume. Rules and memory decide before a
model is called.

- Rules out: a model call per event when a rule or a remembered decision suffices.
- Check: cost per investigation and per idle month are recorded.

## Not building

- Detection. Midnight ingests what the user already runs through APIs, MCP and webhooks from
  Grafana, Alertmanager or Uptime Kuma. Statistical per-service failure rules may come later.
- A general-purpose shell agent.
- A dashboard-first product.
- Governance for organizations before the teams tier.

## Why this is not a two-day build

A weekend clone gets the happy path: an alert, a model call, a message. The value of Midnight is in
what holds when things fail and in what accumulates over time:

- runs that survive crashes without repeating or losing an action;
- execution bounded by a catalog behind a separate, signed executor;
- memory of the operator's own incidents and deploys, which only exists after weeks of running;
- an interruption budget tuned on real deploys;
- published blind-evaluation results next to a Claude Code baseline.

Several of these do not hold today: #758 to #762 break consumption limits, grant reissue, evidence
checks, run termination and the executor journal. The vision is a commitment that orders the
backlog, not a description of the current state.
