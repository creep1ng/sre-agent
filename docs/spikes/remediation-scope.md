# Remediation scope: environments, competitors and a model of controls

- **Issue:** [#1088](https://github.com/creep1ng/sre-agent/issues/1088)
- **Type:** Spike, exploratory desk research; no code and nothing measured
- **Run:** 2026-11-14, repository at `862a55df`
- **Status:** draft for the maintainer's review
- **Decision:** none. The [vision](../vision.md) is not amended; the ideas that conflict with it
  are listed under [Conflicts with the vision](#conflicts-with-the-vision-as-written).

## Questions

> 1. In which environments does a catalog of predefined operations work, and what can Midnight
>    offer someone who deploys on a VPS, or who has logs and no observability stack?
> 2. What lies between unsupervised shell or cloud-administrator access and a catalog of
>    approved, non-destructive operations?
> 3. What do competitors execute today, and where can Midnight stand out in how it understands
>    and handles infrastructure, beyond being open source and cheap per run?

## Where Midnight stands

- The executor acts on one host through Docker Compose (`deployment.rollback`,
  `deployment.restart`) and sets fault flags to their baseline (`flag.set`). Functions, managed
  containers, Kubernetes, PaaS and hosts without containers are out of reach
  ([deploy executor](../deploy-executor.md#known-limitations-of-the-academic-demo)).
- Every operation is code we ship: a new one needs a release.
- Alerts arrive only from Grafana ([alert intake](../alert-intake.md)), and changes only from
  GitHub Actions ([change events](../change-events.md)).
- An investigation is at most six turns ([investigator](../investigator.md)).
- The workflow has no state in which a person leads the incident while the agent observes.
- The stated narrow persona already deploys with Compose on one to three VPS
  ([product direction](../product-direction-2026-10-28.md#implications)). The uncovered host is
  the one without containers: systemd units, nginx, cron.

## Findings

### A catalog fits best where it is needed least

A catalog fits a style of product that has versioned artifacts and an API with fine-grained
authorization: operations come out typed and reversible, and the platform's own access policy
enforces them.

| Style of product | Natural operations | What enforces them | Fit |
| --- | --- | --- | --- |
| Functions | point to the previous version, set concurrency | the platform's access policy per resource | high |
| Managed containers | previous task revision, desired count | the platform's access policy per service | high |
| Orchestrators | undo or restart a rollout, scale | role-based access per named workload | high |
| PaaS | redeploy the previous deployment, restart | a token, often for a whole project or account | medium: only our executor narrows it |
| One host with Compose | roll back a tag, restart | socket proxy and executor | built |
| One host with systemd | restart, reload | sudoers and Unix permissions | restart is easy; rollback exists only if the deploy keeps releases |

Platforms where the catalog fits well already heal themselves and offer a rollback button, so
their owners have the least pain. The host where pain is greatest has few safe remedies and a
hard diagnosis. This points at wide, typed reading and narrow writing.

### Four ways vendors execute

Details, quotations and links are in
[what the vendors do](../deploy-executor.md#what-the-vendors-do).

| Model | Vendors | Human gate |
| --- | --- | --- |
| Commands or API calls the model generates, filtered by lists | Azure SRE Agent, AWS DevOps Agent, Google Gemini Cloud Assist | Azure has an autonomous mode; AWS asks per action, always; Google's user clicks Run |
| Fixed typed actions | Datadog, Resolve.ai, Rootly | Datadog offers Ask or Deny; Resolve.ai lets an admin release one kind of tool |
| Code or infrastructure pull requests that a person merges | Sentry, Cleric, Wiz, Grafana, incident.io, Railway | the merge |
| Workflows written in advance | Dynatrace, New Relic, PagerDuty, Wiz | set by the workflow |

### Already common: a baseline to match, not a difference

- A typed catalog with a separate executor. Resolve.ai: "the AI model that generates proposals
  never has direct access to write APIs".
- Credentials scoped to the approved action. AWS issues a session limited to the approved
  operation and resource.
- Autonomy set by static policy, per plan or per tool.
- A topology graph, from infrastructure templates and tags (AWS) or from the vendor's own
  telemetry (Dynatrace, Grafana).
- Connectors to repositories, CI, chat and documents as sources of evidence. Users expect them.

### Not described in any page read

Absence from the pages read does not prove a product lacks the feature.

- **Reversibility as a property of each action.** Lists separate reading from writing and block
  deletion of resources. None says whether an action can be undone or loses data. AWS refuses
  delete-class operations, yet the approval example in its documentation is `sqs:PurgeQueue`.
- **A handoff to the person.** No page describes a person taking over the incident while the
  agent keeps observing and recording. PagerDuty sells a separate scribe agent.
- **A native catalog across platforms.** Each vendor acts natively on its own platform (Datadog:
  Kubernetes and AWS). AWS reaches other systems through third-party and MCP tools that the
  customer classifies.
- **Recovery as a process.** No page describes staged steps with verification between them.
  Azure verifies after acting; Datadog's verification is a click by the user.
- **Topology without the vendor's telemetry**, for the observability vendors.

## Hypotheses

None of these is measured. Each names the [value](../vision.md#values) it would serve.

1. **A graph of resources with controls** (values 2 and 3). Nodes are resources by kind (queue,
   balancer, worker pool, function, deployment), not by provider; an adapter per platform maps a
   kind to its API. Edges are dependencies, each with its source (a trace, an infrastructure
   file, the operator's declaration), and unknown parts stay marked unknown. A *control* is a
   named setting on a node with a declared range and a readable current value. A change records
   the previous value in its receipt, so undoing it is setting it back. `flag.set` already has
   this shape, and a rollback is the "version" control set to the previous value. The vocabulary
   is short: version, capacity, flow, traffic, configuration, plus restart. Purging or deleting
   is not a control: no previous value can be restored. The agent composes controls for each
   incident; it does not look a failure up in a library of scenarios.
2. **Stabilize at night, repair by day** (value 1). At night the agent moves only reversible,
   bounded controls the operator authorized in advance, and reverts when verification fails.
   Repairing the cause waits for the morning, with the report.
3. **The handoff** (values 1 and 3). The incident is led by the agent, by both (approval) or by
   a person. When a person leads, the agent observes signals, records each change, verifies the
   recovery and drafts the postmortem. The signal can be deterministic: Midnight holds a receipt
   for everything it executes, so a change on a resource of the incident without a receipt was
   made by someone else. It needs a list of automation principals (an autoscaler is not a
   person), and pending approvals expire on handoff so that two hands never act at once.
4. **Autonomy levels** (value 2; maintainer's proposal). 0 read-only; 1 automatic approval of
   non-destructive operations; 2 an approver that combines a model with a deterministic
   inspector; 3 full access. For level 2, the inspector would set the ceiling and the model
   could only lower it, that is, decide to ask a person: a steered model then approves nothing
   the inspector did not already allow. The [Jev spike](jev-decision-model.md) found a risk
   (state migrations) that none of its five score dimensions captured.
5. **Background discovery** (value 4). Connectors feed the graph: decisions, infrastructure
   missing from the first triage, undocumented details. Driven by events (a push that touches
   Compose, Terraform or workflow files), rules before a model, results marked unconfirmed with
   a link to their source and sent to the digest. Text from chat or documents is data, never
   instructions.
6. **Repair after the incident** (value 4). With the timeline and what stabilized the system, a
   background process advances the investigation of the fix and, if the operator configures it,
   a draft pull request. A stopping point per project (cause, plan, draft), as Sentry does, and
   implementation handed to a coding agent.
7. **A path for the host without containers** (value 2). Entry through one `authorized_keys`
   line with a forced command, so the key runs one binary and no daemon is added; typed
   read-only probes (journal by unit, unit status, disk, memory, certificate expiry, declared log
   paths); restart and reload through exact sudoers entries. Allowing binaries is not enough:
   `find`, `tar`, `awk` or `git` give a shell.
8. **A signal for the user with only logs** (value 1). systemd's `OnFailure=`, Docker events and
   an external ping, received by a generic webhook intake.
9. **Quarantined readers** (values 2 and 3). Reading subagents, each a principal with read
   grants only, return structured facts with a reference to the evidence. The coordinator never
   sees raw text an attacker could write, and pruning its context loses nothing because the raw
   text stays stored and audited.
10. **Posture from the graph, and a red team against Midnight itself** (values 2 and 6).
    Reliability findings for the digest (single points of failure, services with no rollback
    artifact, certificates about to expire), and adversarial tests of injection through logs. A
    security product like Wiz's is another product with another buyer.

## Conflicts with the vision as written

- Operations the operator declares (hypothesis 7, and the general idea of a catalog that grows
  from resolved incidents) are new primitive operations. Value 2 rules out "routines that are
  anything other than compositions of catalog operations".
- Level 3 as full access (hypothesis 4) contradicts value 2: "a shell tool, any mode that adds
  capabilities".
- Host signals (hypothesis 8) sit next to "Not building: detection". They ingest what the host
  already emits; a log-pattern rule engine would be detection.
- A security product (hypothesis 10) is outside the vision.

## Open doubts

- **Whether this is the right path.** Azure goes the other way: generated commands and autonomy
  by default cover the long tail a closed vocabulary cannot. The handoff plus learning new
  controls is our answer, and nothing shows it is enough.
- **Whether anyone would pay.** Nothing in this spike addresses it. The only inputs are the
  public voices in the [product direction](../product-direction-2026-10-28.md) and the vendors'
  prices (per agent-second, per investigation or per seat).
- **No real infrastructure or incident data.** Reality is more complex than the cases considered
  here. Public postmortems come from large companies; a freelancer's expired certificate is not
  published.
- **The cross-platform advantage is narrower than it first looked**, since AWS already runs
  customer-classified MCP tools with approval.

## Cheapest next checks

1. **Corpus check of the control vocabulary.** Classify the mitigations people applied in public
   postmortems: the fraction a reversible control expresses, the destructive ones, the ones not
   foreseen. "Metastable Failures in the Wild" did this for one class of failure, 22 incidents.
2. **Blind evaluation on a host**, with typical faults (full disk, out of memory, expired
   certificate, crash loop, bad deploy): typed probes against the Claude Code over SSH baseline
   that value 6 already requires. If narrow reading loses much diagnosis, widen reading, never
   writing.
3. **The handoff signal on the demo.** A change without a Midnight receipt during an open
   incident, for example a manual `docker restart`.
4. **One scenario where restart and rollback do not help**, as a case of the class and not as a
   goal. `compose.full.yaml` adds the Kafka layer that `kafkaQueueProblems` needs.
5. **Willingness to pay.** Show the handoff and the night stabilization to freelancers of the
   persona before building further. This check was not discussed with the maintainer.

## Sources and how far to trust them

- **Read by the author on 2026-11-14:** the eight pages added to
  [what the vendors do](../deploy-executor.md#what-the-vendors-do): AWS directed actions, Azure
  run modes and mitigations, Datadog infrastructure actions, Google investigations, Resolve.ai
  security, Sentry Autofix and Vercel Agent permissions.
- **Reported by three research passes the same day and not read again:** Grafana, New Relic,
  Dynatrace, Cleric, Railway, AWS topology and pricing, the Google SRE book, the AWS Builders'
  Library and both metastable-failure papers.
- **Announcements or marketing only:** Wiz, Traversal, NeuBird, PagerDuty's new agent and Rootly's
  autonomy ladder. **Press only:** Komodor, whose site refused the request.
- Azure's documentation states two defaults: Autonomous for a response plan or task, Review for
  the agent-level fallback.
