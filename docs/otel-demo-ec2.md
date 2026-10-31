# Shared OTel Demo EC2 sessions

The launcher manages one short-lived OTel Demo for Codex agents sharing this
host. It uses the `otel-demo` IAM profile in `us-east-1`, a `t3a.xlarge`, no
inbound security-group rules, and SSM loopback port forwarding. Account bootstrap
is a separate, explicit step; do not run it until the account setup has been
reviewed and authorized.

Before either bootstrap or a session command, configure
`OTEL_DEMO_EXPECTED_ACCOUNT_ID` in the local shell with the intended 12-digit AWS
account ID. The value is required for fail-closed STS identity verification; do
not commit the real account ID or persist this environment setting in the repo.

## Account setup (explicit operator action)

The three CloudFormation templates provision a dedicated `OTelDemoOperator` IAM user
with size-checked customer-managed policies, an EC2 instance role/profile with
Systems Manager core access, an EventBridge Scheduler group and execution role,
and an account-wide monthly USD 10 Budget. The Scheduler trust is scoped to the
exact `otel-demo` schedule-group ARN, and its execution policy can terminate only
instances carrying the OTel Demo ownership tags. The operator can create only a
`t3a.xlarge` in the selected VPC, create a tagged outbound-only security group,
manage schedules in the `otel-demo` group, and use SSM against tagged demo
instances, scoped with Systems Manager's `ssm:resourceTag` condition keys.
Before launch, the CLI queries `t3a.xlarge` availability by
availability zone and chooses deterministically among public default subnets in
supported zones; it fails closed if none are available. It cannot change
security-group ingress, create IAM identities, or manage unrelated instances.

The launcher resolves its AMI from Canonical's exact Ubuntu 24.04 SSM parameter.
The IAM `ec2:Owner` condition uses EC2's authorization-context value `amazon`,
not Canonical's numeric publisher account ID. Because the policy's image and
snapshot resource ARNs are wildcarded, direct use of this IAM key outside the
launcher could also launch from other Amazon-owned AMIs or snapshots.

Budget alerts go to the email supplied at deployment and fire at 80% and 100% of
the monthly budget. An automatic Budget action at 100% ACTUAL attaches an
explicit `Deny ec2:RunInstances` policy to `OTelDemoOperator`, preventing that
user from launching additional EC2 instances after the action is evaluated.
The action's execution role may only attach or detach this exact deny policy on
this exact IAM user. Confirm the email subscription if AWS requests it. Do not
place the recipient address in this repository. The budget is account-wide: it
includes costs unrelated to OTel Demo.

Only during the separately authorized account bootstrap, provide the expected
account ID, verified VPC, and alert address to the helper. It verifies that
`personal` is the root principal for that account, deploys the operator,
runtime, and budget stacks, and creates one key for the dedicated IAM user—not
a root key. It stores the key in the local AWS credentials file under
`otel-demo`, atomically with mode `0600`, and never prints the secret. If
writing fails, it deletes the newly created IAM key. An existing `otel-demo`
profile is left untouched only after STS verifies both the expected account and
the exact `OTelDemoOperator` identity; a wrong or unavailable identity fails
closed.

```sh
export OTEL_DEMO_EXPECTED_ACCOUNT_ID='<your-12-digit-account-id>'
python3 scripts/bootstrap_otel_account.py \
  --expected-account "$OTEL_DEMO_EXPECTED_ACCOUNT_ID" \
  --alert-email '<budget-alert-recipient>' \
  --vpc-id '<verified-vpc-id>' \
  --apply
```

This command changes AWS and local credentials. Do not run it as a connectivity
test. The `--apply` flag is mandatory. Verify identity and permissions before
using the resulting profile:

```sh
aws --profile otel-demo --region us-east-1 sts get-caller-identity
```

## Session commands

```sh
export OTEL_DEMO_EXPECTED_ACCOUNT_ID='<your-12-digit-account-id>'
python3 scripts/otel_ec2.py up
python3 scripts/otel_ec2.py status
python3 scripts/otel_ec2.py extend --hours 1
python3 scripts/otel_ec2.py connect --local-port 18090 --remote-port 8090
python3 scripts/otel_ec2.py down
```

The launcher does not accept profile or region overrides. Before any session
operation it verifies STS account and exact IAM user identity against
`OTEL_DEMO_EXPECTED_ACCOUNT_ID`. Every AWS CLI call is pinned to profile
`otel-demo` and `us-east-1`.

`up` returns the existing active shared instance when its Scheduler deadline is
verified, rather than launching another one. Repeating `down` after the instance
is absent is a no-op after five EC2 lookups with exponential backoff (up to
30 seconds). This avoids treating a single temporarily empty `DescribeInstances`
result after launch as confirmed absence. EC2 remains eventually consistent,
so an empty result even after retry is not a proof that no instance exists;
Scheduler and the guest deadline remain the automatic termination fallback.

The initial lifetime is two hours. Extensions are bounded by twelve hours from
the original launch. `connect` opens only a local SSM port-forward; select a
different local port for each agent using the shared instance concurrently.
The EC2 security group has no inbound rules; only the local loopback tunnel is
exposed on this host. There is no public inbound route to the demo.

### Local Session Manager Plugin prerequisite

`connect` requires the AWS Session Manager Plugin on the local host, in addition
to the AWS CLI. The CLI launches this plugin to establish the SSM port-forward.
Install it for your operating system using the
[official Session Manager Plugin installation guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html).
The plugin is a local prerequisite; it is not installed on the EC2 instance.

There is intentionally no live-resource snapshot in this guide. Instance IDs,
security-group IDs, public addresses, and dated cloud state are ephemeral and
should only appear in sanitized, current PR evidence when freshly verified.

## Cost and cleanup limits

Before launching, the CLI queries account-wide month-to-date Cost Explorer data
and adds a reserve sized to the session it is about to start: the `t3a.xlarge`
On-Demand rate in `us-east-1` plus an hourly margin for the root volume, public
IPv4 address and egress (`instance_hourly_usd` and `hourly_margin_usd` in
`DemoConfig`, about USD 0.20/h), multiplied by the session's lifetime (two hours by
default, about USD 0.40). `extend` repeats the same check for the whole session up
to its new deadline, before it touches the guest, tag or Scheduler, so a session is
never extended past the budget. Both fail closed if Cost Explorer is unavailable,
returns a currency other than USD, or the estimated total would exceed the USD
10 monthly threshold.

This is a prelaunch guard, not a billing guarantee. Cost Explorer data lags by up
to about 24 hours, so hours a session has already run may not be billed yet; that
is why `extend` reserves the session's full lifetime rather than only the added
time. The rate is a published list price, not a live quote, and ongoing account
charges may continue after a launch is blocked. On the first UTC day of a month,
`up` and `extend` refuse because there is no completed in-month date range to query.

The AWS Budget is delayed: billing data and budget actions are evaluated
asynchronously, so the deny can arrive after spending has passed USD 10. This is
not a hard billing cap; it applies only to future EC2 launches by this operator,
not unrelated services, other principals, or already-running EC2 instances.
Each EC2 launch independently creates a one-time EventBridge Scheduler
termination schedule for its deadline. This server-side schedule is the primary
cleanup control and does not rely on the guest OS or this laptop; the separate
100% budget action does not replace it. The guest systemd deadline is only a
secondary safety net. If a schedule cannot be created, the CLI immediately
requests EC2 termination and refuses to report a successful launch.

The shared launcher lock prevents duplicate starts from agents on the same
host. Agents in separate worktrees on that host can reuse the same instance; use
a distinct local forwarding port per concurrent agent. This is not a distributed
lock across multiple machines. Keep the account limited to one operator
host/session and verify `status` before coordinating work from another machine.

The account bootstrap also takes a mode-`0600` local lock beside the AWS
credentials file to prevent concurrent runs from creating duplicate IAM keys.

Treat the IAM access key as a long-lived secret: restrict access to
`~/.aws/credentials`, rotate it under a separately reviewed process, and revoke
the previous key immediately after confirming the replacement profile. To
revoke the current key, use the root `personal` profile to delete that key from
`OTelDemoOperator`, then remove the local `[otel-demo]` credentials section.
Never print, paste, or commit access-key secret material.

## MCP and declared signal lifecycle (#618)

`prepare-mcp` explicitly adds the digest-locked read-only Grafana MCP service and
owned flag working copy. It converges current declared public Demo environment
overrides for legacy instances without editing upstream or rotating the token.
Use `connect-mcp` to consume that environment from SRE; see the
[setup guide](setup-sre.md#prepared-aws-connection). MCP listens on remote loopback
17800 only. Temporary token handoff listens on loopback17900, has a120s server-side
lifetime and is stopped after transfer. Neither port opens public ingress.
The local relay holds no MCP/provider/AWS keys and publishes no host port.

The producer's `fail`/`reset` operations apply the manifest's declared flag/baseline
and retain synthetic traffic. Read both metrics and logs through the governed SRE
API after150s, as explained in [demo-signals](demo-signals.md); health alone is not
signal recovery. `connect-mcp` only proves transport and denies anonymous callers;
SRE readiness, user workflow acceptance and real signal recovery are separate.

Token transfer uses SSM port forwarding, not secret-bearing Run Command output.
AWS documents that [session-content logging is unavailable for port-forwarding
sessions](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging.html).
SSM API/session metadata may still be audited. Never print token payloads, request
headers, owner credentials or private connection metadata into evidence.

## Open the store and see its live alert (#672)

`connect` forwards one declared port to this host's loopback over SSM; nothing
opens to the internet. The store is the frontend proxy on port 8090, which also
serves `/grafana`, `/jaeger/ui` and `/feature`:

```sh
python3 scripts/otel_ec2.py connect --local-port 18690 --remote-port 8090
```

Open `http://127.0.0.1:18690/`, add a product to the cart and place the order.
With `fail` applied, Place Order leaves you on the cart (`POST /api/checkout`
answers 500; the store shows no error banner). After `reset` it reaches
"Your order is complete!".

## Alerts from the instance's Grafana (#765)

`prepare-mcp` also provisions Midnight's rules and webhook contact point
(`demo/grafana/alerting/midnight.yaml`, see [alert intake](alert-intake.md)) in the
instance's Grafana, with a secret it generates in `alert-intake.env` beside the MCP
token. Grafana reads its provisioning from `/etc/midnight-provisioning`, outside
upstream's bind mount, so the upstream checkout stays untouched. SSM forwards only
from this host to the instance, so Grafana cannot reach the local API: it posts to an
outbox on the instance (`mcp_guest.py serve-outbox`, a systemd unit listening on the
Docker bridge gateway for Grafana and on remote loopback 17801 for the drain; it keeps
the last 200 deliveries in memory). `connect-mcp` hands the secret off with the token,
forwards 17801 to local port `--local-port + 2` and relays each delivery, body and
`Authorization` unchanged, to `--intake-url` (default
`http://127.0.0.1:8000/v1/alert-intake/grafana`, the API's published port). With
`SRE_OTEL_MODE=aws`, `setup_sre.py` reads the same `alert-intake.env` from
`DEMO_STATE_DIR` and gives the API the secret, so a firing rule opens the incident with
nobody at the console. Measured on an instance on 2026-10-31
([record](evidence/issue-765/ec2-paymentfailure.json)): a 20 min healthy watch fired
no rule; `paymentFailure` at 100% opened `payment` and `checkout` and dispatched both
investigations 103.5 s and 164.9 s after the flag, and both resolved 87 s after `reset`.
To inject it, edit `paymentFailure` in the flag working copy over SSM as `fail` does
(`fail` itself turns on `paymentUnreachable`). If `/` on port 8090 refuses after
`prepare-mcp`, check that `frontend-proxy` is running; the connect-mcp tunnel can end
after about 25 idle minutes, so reconnect before a run.

Grafana's anonymous user is Admin upstream, so anyone who reaches `/grafana` through
`connect` can read the contact point and its secret. The secret guards only this
demo's intake.

## AWS references

- [Scheduler confused-deputy protection](https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html)
- [AWS Budgets actions](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html)
- [IAM policy size quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)
