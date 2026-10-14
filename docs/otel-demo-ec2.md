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
and adds a USD 3 session reserve. It fails closed if Cost Explorer is unavailable,
returns a currency other than USD, or the estimated total would exceed the USD
10 monthly threshold. This is a prelaunch guard, not a billing guarantee: Cost
Explorer is delayed, the reserve is an estimate rather than a live price quote,
and ongoing account charges may continue after a launch is blocked. On the first
UTC day of a month, the guard refuses launch because there is no completed
in-month date range to query.

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

## AWS references

- [Scheduler confused-deputy protection](https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html)
- [AWS Budgets actions](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html)
- [IAM policy size quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html)
