# Deploy executor: governed remediation over docker-socket-proxy

Issue #720 (epic #733, umbrella #697). Approving a mitigation today only moves the workflow
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
between `demo/checkout:1.4.0` and `1.5.0` ([demo-env](demo-env.md)). #724 adds a `flag.set`
adapter for the OTel store; a generic manifest is later.

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
  with no catalog (the OTel store until #724). The demo scenario must therefore be one an enrolled
  operation can fix.
- **Service names.** The proposal looks up operations by the alert's `service`, so an enrolled
  service needs a name no other source emits. Our second service (#721) is `sre-checkout`
  everywhere: catalog, the `checkout-orders-error-rate` rule, its `service.name`,
  `demo_env.py --service` and the grants. The store's `checkout`, alerted by
  `checkout-payment-error-rate`, keeps its name and stays without a catalog; sharing `checkout`
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
