# Deploy executor: governed remediation over docker-socket-proxy

Issue #720 (epic #733, umbrella #697). Without it, approving a mitigation only moves the workflow
(`execution_mode: simulated`); the operator applies it by hand. The deploy-executor makes the
product apply it: a container that executes **named operations with a strict schema** against the
Docker Engine, through `docker-socket-proxy` with only the `containers` and `images` families
enabled. No endpoint takes a command, a script, an image name or a path. The contract is
`schemas/executor/1.0.0/deploy-executor.yaml`.

```
console ──approve──▶ gateway (#722: exact grant, audit, idempotency by run) ──signed──▶ deploy-executor
                                                                                           │ fixed call list
                                                                                docker-socket-proxy (containers, images)
                                                                                           │ unix socket
                                                                                        dockerd
```

A Telegram tap takes the same path: the Telegram gateway only queues the verified tap, and the
API carries it out as the linked human ([Telegram channel](telegram-channel.md#deciding-from-the-chat)),
so neither the signing key nor any credential lives in the internet-facing gateway.

The harness never reaches the executor: it talks to the gateway only. The executor has no
published port, sits on the internal `executor-call` network with the api alone, and verifies the
gateway's signature on every operation (#743); the proxy sits on a second internal network that
only the executor joins.

## Failure modes, written before the code

| Scenario | Expected | Proof |
| --- | --- | --- |
| `to_tag` not present in the local image store | 422 `image_tag_unknown`; container untouched | fixture `unknown-tag` |
| Service not in the catalog | 404 `service_not_enrolled`; nothing looked up | fixture `unknown-service` |
| Operation not enrolled for that service | 404 `operation_not_enrolled` | fixture `operation-not-enrolled` |
| Missing parameter, extra field, tag carrying a repository | 422 `contract_validation_failed` | fixtures `missing-to-tag`, `extra-field`, `tag-with-repository` |
| No `Idempotency-Key` | 400 `invalid_idempotency_key` | fixture `missing-idempotency-key` |
| Same key and payload sent twice | 200, `replayed: true`, one execution | E2E `double-submission` |
| Same key with another payload | 409 `idempotency_conflict` | fixture `key-reused-with-other-payload` |
| Rollback to the tag already running | 200 `already_at_target`; container untouched | E2E `already-at-target` |
| Socket proxy down | readiness 503; operations 503 `docker_unavailable` | E2E with the proxy stopped |
| Executor died between intent and result | 409 `execution_unknown` on replay; never re-executed | journal rule |
| Journal's last line cut off mid-write (#762) | the executor starts, readiness 200; the fragment is kept in a `truncated` record; a key it names answers 409 `execution_unknown` and is listed in `GET /v1/executions`; new keys run | E2E `journal-tail` |
| A damaged journal line before the last one (#762) | no restart loop: readiness 503 `dependency: journal` naming the line; operations 503 `journal_corrupt`; nothing runs until an operator repairs the file | E2E `journal-damaged` |
| A full disk cuts an append short while the executor stays up (#762) | the file is truncated back to its last complete line; the request answers 503 `journal_unwritable`; an intent that failed never reached Docker; the next start finds no damage | E2E `journal-disk-full` |
| Journal volume read-only (#762) | no restart loop: readiness 503 `dependency: journal`; operations 503 `journal_unwritable` | manual: the journal volume mounted `:ro` (PR #826) |
| Any API family other than containers/images | 403 at the proxy | E2E against `/info`, `/networks`, `/volumes`, `/version`, `/events`, `/exec/*/start` |
| No signature, wrong key, body tampered after signing, signature for another key, stale timestamp (#743) | 401 `signature_missing`, `signature_invalid` or `signature_expired`; container and journal untouched | fixtures `signature-*` |
| A negative fixture sent signed | its own code, never 401: the signature is checked first | the eight fixtures above, now signed |
| `DEPLOY_EXECUTOR_SIGNING_KEY` unset or a placeholder | readiness 503; operations 503 `signing_key_unconfigured`; nothing runs | one-off executor without the key |
| A container that is only on `runtime` | `deploy-executor` does not resolve | `gethostbyname` from `probe` |

The E2E fires each fixture of `schemas/executor/1.0.0/fixtures/negative/` at the real executor
and then checks that the probe container keeps its id, image and start time.

## Operations

Both operations resolve their target the same way: the catalog entry names a Compose service, the
executor finds its container by the Compose project and service labels (one container, or 409
`service_ambiguous`), and inspects it. Every check runs before any write.

`deployment.rollback(service, to_tag)` builds the target reference from the catalog's
`image_repository` and the tag, and refuses the request if the daemon does not have that image. If
the container already runs that reference, the outcome is `already_at_target` and nothing moves.
Otherwise it creates a new container cloned from the running one (same command, environment,
mounts, networks and aliases, labels, restart policy) with the target image, and only then stops
the old one, swaps the names, starts the new one, waits until it is running and healthy, and
removes the old one. If the new container fails to start, the old one gets its name back and is
started again; the request answers 502 `execution_failed`. A later `docker compose up` recreates
the service at its declared version: the rollback is an operational override, not a redeclaration.

`deployment.restart(service)` restarts the container in place and waits for running and healthy.

Idempotency works at two levels. By **key**: each POST carries an `Idempotency-Key` as the
gateway's own mutations do; the key binds to the operation and the payload digest when execution
starts, a replay returns the stored result with `replayed: true`, a different payload is 409, and
a request still in flight is awaited rather than re-run. By **state**: a rollback to the running
tag is a no-op, so even a replay after a lost journal cannot roll twice. The journal
`/var/lib/deploy-executor/executions.jsonl` records an intent line before the first write and a
result line after; an intent without a result answers 409 `execution_unknown` and is never
re-executed, the rule the runtime applies to lost investigator dispatches (#567).

A crash or a full disk can cut the journal's last line short (#762). At start the executor treats
an unparseable last line as an interrupted write: it rewrites the file atomically, replacing that
line with a complete `truncated` record that keeps the fragment and whatever binding, payload
digest, execution id, operation, service and rollback `to_tag` the fragment still names. An intent
is written and `fsync`ed before the first Docker call, so a cut intent, even one that lost its
binding, never reached Docker, and after a power loss its key cannot run twice; a cut result
follows an intent already on disk. Either way the key answers 409 `execution_unknown`, whatever its payload,
and `GET /v1/executions` lists the record as a 409 `execution_unknown` entry so the operator learns
an operation may have run. A damaged line anywhere else is not an interrupted write, so the executor
does not guess: it starts, readiness answers 503 with `dependency: journal` and the line number,
and every operation answers 503 `journal_corrupt` until an operator repairs the file and restarts it.
An append that fails while the executor stays up (a full disk) truncates the file back to its last
complete line, so the next record cannot glue onto a fragment, and answers 503 `journal_unwritable`.
A journal directory the executor cannot write leaves it running with readiness 503 instead of a
restart loop.
`GET /v1/executions` lists the results; `GET /v1/services/{service}` shows the live container and
the locally present tags of its repository, which is what a proposal needs to pick `to_tag`.

## What the proxy confines, and what it cannot

| Family | Setting | Why |
| --- | --- | --- |
| `containers` | `CONTAINERS=1`, `POST=1` | list, inspect, create, start, stop, restart, rename, remove |
| `images` | `IMAGES=1` | inspect the target tag, list the repository's tags |
| `_ping` | `PING=1` | readiness |
| everything else | `0` | `exec` start, `networks`, `volumes`, `info`, `events`, `build`, `swarm`... answer 403 |

The proxy gates API families, not fields: with `containers` and `POST` enabled it would also pass
a `create` with a host bind or a privileged flag. The executor is the second layer: a fixed list
of calls, and `create` only ever sends the configuration of the container it replaces. Both
layers are needed; neither replaces the gateway's grant.

## Caller authentication

The executor is the hands, not the policy: it knows no principal and no grant. What it checks is
that the exact request in front of it came from its one caller. Every `POST /v1/operations/*`
carries `X-Executor-Timestamp` and `X-Executor-Signature: v1=<hex>`: HMAC-SHA256 with the key in
`DEPLOY_EXECUTOR_SIGNING_KEY` over the method, the path, the `Idempotency-Key`, the SHA-256 of the
body and the timestamp. The signature is checked before anything else, so an unsigned request
learns nothing, not even whether the operation exists; a tampered body, a signature made for
another key, a wrong secret or a timestamp outside 300 s answer 401 and write nothing. A captured
request re-sent inside the window meets its own `Idempotency-Key` binding and replays the stored
result. Without a usable key the executor fails closed: readiness 503 and every operation 503
`signing_key_unconfigured`. The gateway signs from #722; until then the only signer is the E2E.

Four layers, each answering one question: the network (only the api shares `executor-call`, so a
container on `runtime` cannot even resolve the name) says who can reach it; the signature says the
gateway produced this exact request; the grant (#722) says the agent may run that operation on
that service; the human approval says this instance may run now. One call goes the other way
(#770): after answering a completed rollback, the executor sends `POST /v1/changes` to the api over
the same `executor-call` network with its own `change.write` credential. That credential opens no
operation and reads nothing; it only records changes.

## Known limitations of the academic demo

Stated so that the exposition does not overclaim; a green E2E hides none of them.

- The key is symmetric: whoever reads the api container's environment can sign. An asymmetric
  `v2` (the executor holding only a public key) is the upgrade, not needed for the demo.
- The proxy gates API families, not fields. From inside the executor container, `POST
  /containers/create` with a host bind is an allowed call, so compromising that container is
  compromising the host. That is why it runs read-only, without capabilities, without privilege
  escalation and with only two secrets, the verification key and the `change.write` credential
  of the `deploy-executor` principal (#770), and why the catalog, not the proxy, is the action
  space.
- A compromised executor can forge change events: with that credential it can record deploys,
  rollbacks or CI results of any service, and the investigator reads them as evidence ("what
  changed"), so a forged event can steer a hypothesis. Each event names its `source` and
  `recorded_by`, the investigator's evidence keeps the read's `request_id`, and the human approves
  every mitigation; compromising the executor is compromising the host anyway. Without
  `DEPLOY_EXECUTOR_CHANGES_API_KEY` nothing is recorded and the credential does not exist.
- The host, its Docker socket and the administrator who grants are the root of trust by design.
- No mTLS, no key rotation, no nonce beyond the `Idempotency-Key`; the window bounds a replay.
- Single host, Compose only: no Kubernetes, no remote executor, no registry authentication.
- Until #722 nothing in the product calls the executor; until #726 nothing scores risk.

## Catalog

`agent/executor/catalog.v1.yaml` enrols services: a `service` name, its `compose_service`, the
`image_repository` the tag is appended to, and the `operations` offered. `probe` (the E2E target)
offers both; `web` offers restart only, its image being built locally without release tags.
`sre-checkout` (#721) offers both: the demo's second service, in the `otel-demo` project,
between `demo/checkout:1.4.0` and `1.5.0` ([demo-env](demo-env.md)). On the OTel demo on EC2,
`scripts/setup_sre.py` mounts `agent/executor/catalog.otel-aws.v1.yaml` instead: the store's
`checkout` and `payment` with `flag.set` only (below). A generic manifest is later.

## flag.set on the OTel demo (#724)

On EC2 the store runs on the instance, out of the executor's Docker reach, and its fault is a
flagd flag (`otel_ec2.py fail` turns `paymentUnreachable` on). `flag.set(service, flag, variant)`
turns it back off through the deploy-executor, so approving the agent's proposal recovers the
store with no operator shell.

```
api ──signed──▶ deploy-executor ──Bearer flag token──▶ otel-flags (link) ═SSM═▶ instance 127.0.0.1:17802
               (no Docker proxy)                   network <mcp>-flags        mcp_guest.py serve-flags
                                                   (executor only)            writes demo.flagd.json;
                                                                              flagd reloads it
```

- **Catalog.** Each service lists the flags it may set and the only variants allowed:
  `checkout` → `paymentUnreachable`, `paymentFailure`; `payment` → `paymentFailure`; every
  variant is `off`, the manifest's baseline. `GET /v1/services/{service}` shows each flag's
  current variant next to what it may be set to. That serves the gateway's checks; the agent
  never sees the current variant (below).
- **The agent reaches the flag from evidence** (maintainer decision of 2026-11-02). Its prompt
  lists only the operation, the flags and their allowed values. A proposal is still checked
  against the real state twice. At proposal time, the investigator refuses a flag that is
  already off ("paymentUnreachable is already off on the demo, so setting it changes nothing")
  and gives the model one retry, after which it asks a person. At approval, the gateway re-reads
  the catalog (#919) and answers 409 `precondition_failed` with the same reason when the flag
  went off in the meantime.
- **Instance side.** `prepare-mcp` installs `mcp_guest.py serve-flags` as a systemd unit on the
  instance's loopback, port 17802, with its own 48-hex token (`flag-write.env`, mode 0600). It
  answers `GET /flags` (the fault flags' current variants) and `PUT /flags/<name>`
  `{"variant"}`, and writes only a flag in the manifest's `fault_flags`, only to its
  `flag_baseline` variant (403 otherwise, 409 if the flag file does not offer it).
- **Path.** `connect-mcp` hands the token off with the MCP token, forwards 17802 over SSM to
  local port `--local-port + 3`, and links it as `otel-flags` on its own internal network
  `<network>-flags`. Only the deploy-executor joins that network and reads the token
  (`env_file`); the api, the harness and the MCP link do not.
- **Outcomes.** `flag_set`, or `already_at_target` when the flag already holds the variant
  (nothing is written). The receipt carries no image; the timeline says
  `ran flag.set on checkout: flag_set (paymentUnreachable → off)`.

Failure modes, written before the code:

| Scenario | Expected | Proof |
| --- | --- | --- |
| A flag or variant outside the service's catalog (`paymentUnreachable=on`, `loadGeneratorTraffic=off`) | 422 `flag_not_allowed`; nothing written | E2E `checks`, local and EC2 |
| Unsigned `flag.set` | 401 `signature_missing`; nothing written | E2E `checks` |
| The listener asked to turn a fault on, or to write a non-fault flag, with its token | 403; nothing written | listener probe from the executor (local) |
| Wrong listener token | 401 | listener probe (local) |
| Listener or tunnel down | 503 `flags_unavailable`, retryable; readiness 503 `dependency: flags` | readiness gates `setup_sre.py` |
| The flag file lacks the variant | listener 409 → 502 `execution_failed` | code path |
| The flag is already at the variant | 200 `already_at_target`; no write | code path |
| The agent proposes a flag that is already off | refused at proposal with the reason; one retry, then `request_human` | E2E `flow` with `paymentFailure` on `checkout` |
| The flag goes off between proposal and approval | 409 `precondition_failed`, the reason, incident stays `mitigating`, nothing runs | E2E `flow` with `STALE=1` |
| The prompt shows a flag's current variant | never: the agent's state has only `allowed` | E2E `flow` reads every turn's input |
| A write restarts flagd, and every client's flag stream breaks | never: flagd reloads the file in place, and clients get `configuration_change` | flagd 0.16.0 probe and E2E stream check |
| The api resolving `otel-flags` | fails: only the executor's network has it | E2E `checks`, local and EC2 |

### Security limits of the demo

- **The token is the listener's only control.** Whoever holds `flag-write.env` (the host user
  running `connect-mcp`, the executor container) can turn the two payment faults off, and
  nothing else: the listener cannot turn a fault on or touch other flags. It holds no AWS
  credential, and the executor runs no command on the instance.
- **Anyone with `connect`'s store tunnel can still change any flag** through upstream's flagd UI
  at `/feature`, unauthenticated, as before #724. The listener adds no new way to break the demo.
- **flagd reloads; nothing restarts it.** The instance's flagd (`v0.16.0`, upstream's
  `--uri file:./etc/flagd/demo.flagd.json` on a directory mount) polls the file's metadata
  about once a second (`fileinfo` sync). It picks up an atomic replace and an in-place write
  within ~1 s, and open `EventStream`s get `configuration_change`. A restart sends
  `provider_shutdown` and breaks every stream. Until 2026-11-02, `fail`, `reset` and the listener
  restarted flagd, and the burst of `payment` `EventStream` / `tcp.connect` errors after a
  `fail` opened a spurious `payment` incident. They now only replace the file. An approved
  `flag.set` therefore takes effect up to ~1 s after the receipt.
- **Demo honesty: the agent does not read the answer from the catalog.** It names the flag from
  traces, metrics and logs; the current values are only checked server-side. One bit still
  leaks by design: a refused proposal tells the model that the flag it named is already off.
  With two flags on `checkout`, the retry can then guess the other. Each step is recorded in the
  run's turns, so a reviewer can see when a proposal needed a refusal.
- **The catalog trusts the alert's service name.** `checkout` and `payment` are the store's names
  only in this catalog; locally they stay unenrolled (`catalog.v1.yaml`), as decided in #751.
- **The contract file stays 1.0.0.** `schemas/executor/1.0.0` does not describe `flag.set` yet:
  publishing it as 1.1.0 comes after the 2026-11-04 demo (maintainer decision of 2026-11-03).

## Levels of autonomy

The executor is the same at every level; what changes is who may call it and when.

| Level | Who executes | Requires | Issue |
| --- | --- | --- | --- |
| L0 simulated | nobody; the operator applies it by hand | nothing | today |
| L1 approve-to-execute | the gateway, on the human's `approve_mitigation` | exact grant `{service}:{operation}`, audit before responding, idempotency by `(run_id, mitigation_version)` | #722, #723 |
| L2 one-click when low risk | the gateway after a one-click approval; high or unknown risk forces `RequestHuman` | a risk score stored with the proposal (reversible, touches data, blast radius) | #726 |
| L3 autonomous within a budget | the gateway with no human, for low-risk operations on enrolled services | L2 plus a per-service cooldown and a daily auto-execution budget that degrades to L1, never queues | later |

The decisions of #733 hold at every level: no shell even when a human approves, the risk scorer
never authorizes without a human, and the catalog is the whole action space.

## Approve-to-execute (#722)

Maintainer decisions of 2026-10-26 closing the definition of ready of #722. The goal is
demonstrable agentic remediation for the demo, not a simulated one.

- **Grant.** Resource type `service_operation`, `resource_id` `{service}:{operation}` (for example
  `sre-checkout:deployment.rollback`), action `mitigation.execute`, as the contract's `governance`
  block already says. The holder is the agent principal `incident-harness`: the grant says the
  agent may run that operation on that service. A separate executor identity (#697) would add a
  credential and no control, since the executor checks only the gateway's signature; it remains a
  possible upgrade.
- **Proposal.** For a service enrolled in the catalog the investigator must propose an enrolled
  operation with its parameters. A proposal without one is invalid investigator output, not a
  `simulated` mitigation: the investigator retries with the validation error and otherwise
  escalates through `RequestHuman`, visible in the timeline. `simulated` is kept only for services
  with no catalog (the OTel store until #724, and still locally). The demo scenario must therefore be one an enrolled
  operation can fix.
- **Service names.** The proposal looks up operations by the alert's `service`, so an enrolled
  service needs a name no other source emits. Our second service (#721) is `sre-checkout`
  everywhere: catalog, the Grafana rule `sre-checkout-orders-error-rate` (#765), its
  `service.name`, `demo_env.py --service` and the grants. The store's `checkout`, alerted by the
  generic `service-error-rate` rule, keeps its name and stays without a catalog; sharing `checkout`
  would hand a store payment incident the rollback of an unrelated service (decided on 2026-10-28
  in #751).
- **Order on approval.** Check the incident is still `mitigating` at `expected_incident_version`,
  validate the operation against the catalog the executor serves (`GET /v1/services/{service}`),
  evaluate the grant, and only then call the executor, signed, with an `Idempotency-Key` derived
  from the run and the mitigation. A stale approval never reaches the executor.
- **Executor failure.** 4xx, 5xx, timeout or `execution_unknown` apply no transition: the incident
  stays `mitigating` and the failure is audited and shown in the timeline. An `execution_unknown`
  intent keeps answering 409 for its key; the operator applies the change by hand or asks for a
  new proposal. This is a known limitation of the demo.
- **Audit.** `mitigation.execute` enters the `audit_events` CHECK through a migration, without
  publishing a new audit schema release.
- **Delivery.** The cuts (grant, proposal, execution on approval) merge through PRs into an
  integration branch `feature/722-mitigation-execute`; one final PR from that branch to `main`
  closes #722. #723 owns the agent's verification, the return to `investigating` and the full
  scenario up to `resolved`.

The gateway follows that order on `approve_mitigation` (`src/sre_agent/gateway/execution.py`).
The api needs `DEPLOY_EXECUTOR_URL` and the executor's own `DEPLOY_EXECUTOR_SIGNING_KEY`, and the
key it sends is `mitexec-{run_id}-{mitigation_id}`. A refusal answers 409 `precondition_failed`
(the catalog no longer offers it), 403 `operation_not_authorized` (no grant) or 503
`executor_unavailable`; a failure the executor answers is 409 `execution_failed`, 503 when the
executor marks it retryable. None of them moves the incident. Otherwise the incident moves to
`verifying` with `execution_mode: executed` and the receipt in `mitigation_strategy.execution`.

Every approval that reaches the agent's identity is audited as `mitigation.execute`, however it
ends: the agent and its grant decision, the operation as an HMAC resource reference, the status,
the reason code and the latency, correlated with the request, the incident and the run
(`GET /v1/audit-events?incident_id=`). Like every audit event it keeps no content: what ran and
how it ended stays in the receipt. Nothing runs without `AUDIT_HMAC_KEY` (503
`executor_unavailable`), and an operation that ran is not answered before its audit is written:
if the write fails the approval answers 503 and moves nothing, and the retry sends the same key,
so the executor replays its result.

The timeline's `apply_mitigation` event tells what ran, on which service and how it ended, from
the receipt. A refused or failed approval moves nothing but still enters the run's timeline: a
`denial` event for 403 `operation_not_authorized` and a `human_command` event otherwise, each
with the approver, the request id and the reason code, saying that the incident stays
`mitigating`.

## The action catalog in the console (#870)

`GET /v1/action-catalog` is what the console shows as the list of what Midnight may do. The
gateway joins three sources; the browser never reaches the executor:

- **What exists:** the executor's `GET /v1/catalog`, and for a rollback the tags
  `GET /v1/services/{service}` lists, minus the one running. A `flag.set` service lists its flags
  and their allowed variants, never the current one.
- **Who runs it:** the same `mitigation.execute` evaluation an approval passes, for the agent the
  gateway runs approvals as. No grant, an inactive agent or an inactive `service_operation`
  resource means no one runs it.
- **What it ran:** the latest `mitigation.execute` audit events, matched to the operation by its
  HMAC resource reference and to a recent run by the run reference; the approver is the run's
  `mitigation_approval` decision recorded right after. Without `AUDIT_HMAC_KEY` nothing ran.

It is a `run.read` incident query, not audited, and it returns no executor address, signing
detail or proposal parameters. An executor that does not answer gives `executor_status:
unavailable` with the registered `service_operation` resources and unknown parameters; without
`DEPLOY_EXECUTOR_URL` it is `not_configured`. Contract: `agent/schemas/action-catalog.schema.yaml`.

## What the vendors do

Official documentation, read on 2026-10-22; marketing claims are left out.

| Vendor | Executes remediation? | Model | Human gate |
| --- | --- | --- | --- |
| [Datadog](https://docs.datadoghq.com/actions/private_actions/execution_policies/) | Yes: Workflow Automation, Bits one-click Kubernetes actions (preview) | Private Action Runner in the Agent, polling outbound; Execution Policies allow or deny actions per Agent and namespace; "the default Execution Policies cover read-only actions only" | [Guardrails](https://docs.datadoghq.com/bits_ai/bits_remediation/) per action set and scope: Ask (named approvers) or Deny; no Allow |
| [PagerDuty](https://docs.pagerduty.com/ai-automation/automation/automation-actions) | Yes: Automation Actions (scripts or Rundeck jobs) on a self-hosted runner; the SRE Agent recommends | Per action: "allow invocation manually", "from event orchestration", "only on unresolved incidents"; Rundeck ACL per job; single execution by default | Roles; no native approval step in Rundeck |
| [Rootly](https://docs.rootly.com/private-agent) | Workflows with HTTP, Redis and Heroku actions; Edge Connector scripts (enterprise); AI SRE is "not a read-only guarantee" | Private Agent registers typed capabilities in read, sensitive-read and write tiers; "Rootly can narrow local access, but it cannot expand it" | None documented; "no Private Agent capability pauses for interactive approval" |
| [incident.io](https://docs.incident.io/investigations/trust-and-safety) | No: "Investigations don't take action on your behalf without your request or approval"; only webhooks to an external runner | Workflow "Ask first": Run or Dismiss, first answer wins, 24 h expiry, conditions re-checked | Yes, on the workflow; investigation budgets degrade to confirmation |

Takeaways this design applies: typed named actions, not scripts (Rootly's Private Agent, against
PagerDuty's script actions); two enforcement layers, control plane and local allow-list (Datadog's
policies plus the Agent's `actions_allowlist`; here the gateway's grant plus the proxy); write
actions are an explicit grant, read is the default (Datadog); autonomy decided by static,
reviewable policy, never by the model's confidence (no vendor scores risk at execution time); a
budget degrades to approval and never queues (incident.io, Rootly cooldowns); and attribution
follows the human who approved, not the agent (incident.io).
