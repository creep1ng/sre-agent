# Apply progress

Delivery follows the chain declared in `tasks.md`, split further to keep each
pull request inside the size budget.

| PR | Scope | Deliverable | Status |
|---|---|---|---|
| 1 | Planning artifacts, manifest, digest lock, env overrides | 1 | Approved |
| 2a | Lifecycle: `up`, `verify`, `down`, composition overlay, operator guide | 2, partial | This PR |
| 2b | Failure cycle: `fail`, `reset`, signal check in `verify` | 2, complete | Next |
| 3 | Grafana MCP and its boundary, MCP availability, signal guide | 3 and 4 | Pending |

The split follows the work units already forecast in `tasks.md`, which separate
the lifecycle from the failure cycle.

## Scope correction

`compose.demo.yaml` was forecast for PR 3 and arrives here. Upstream mounts its
own `src/flagd` directory as the flagd configuration source, so failure
injection would have to either edit the upstream tree, which the contract
forbids, or replace the mount. Replacing it requires the overlay, and `up`
already needs it to apply the baseline. Verified on a real host: the resolved
composition contains a single mount at `/etc/flagd`, the owned copy, because
Compose merges volumes by target path.

The flag definitions are not vendored. `up` copies them from the checkout into
`.demo-state/flagd/`, keeping 172 lines of upstream content out of the
repository and removing the need to resynchronise them on every version bump.

## Deviation from the forecast

The operations were forecast as `scripts/demo.sh` and are delivered as
`scripts/demo_env.py`: the repository implements validation logic in Python,
reserves shell for thin helpers, and CI runs `shellcheck` over the shell files
that exist. The script is not added to `ci.yml`, since the operations require a
running daemon and a started environment that CI does not provide.

## Findings from validating on a real host

**Operations hung silently without a running Docker daemon.** The socket never
answers and the process waits with no output, which is what a first-time user
meets. Every operation now probes the daemon before doing anything.

**The flag working copy persisted between runs.** An environment started after a
previous session came up with that session's flag state while reporting success.
CA1 requires a clean start, so `up` applies the declared baseline before
starting rather than reusing whatever was left behind.

**No synthetic traffic reached the store.** The upstream `.env` derives
`FRONTEND_PROXY_ADDR` and `K6_TARGET_URL` from `ENVOY_PORT` while Compose reads
it, before `demo/demo.env` moves the proxy to 8090, so both kept 8080. k6 called
a closed port and still logged each checkout as completed, and `verify`
approved the environment, since it checks availability rather than traffic.
Measured on the reference host: in 30 seconds Envoy received 6 requests before
the fix, one every five seconds as the health check does, and 208 after it.
Both variables are now redeclared in `demo/demo.env` with the literal port,
because a reference there resolves against the upstream value first.
