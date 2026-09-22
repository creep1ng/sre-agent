# Apply progress

Delivery follows the chain declared in `tasks.md`, split further to keep each
pull request inside the size budget.

| PR | Scope | Deliverable | Status |
|---|---|---|---|
| 1 | Planning artifacts, manifest, digest lock, env overrides | 1 | Merged |
| 2a | Lifecycle: `up`, `verify`, `down`, composition overlay, operator guide | 2, partial | Open, #273 |
| 2b | Failure cycle: `fail` and `reset` | 2, complete | This PR |
| 3 | Grafana MCP and its boundary, MCP availability, signal guide | 3 and 4 | Pending |

## Scope correction

`compose.demo.yaml` was forecast for PR 3 and arrived in 2a. Upstream mounts its
own `src/flagd` directory as the flagd configuration source, so operating on the
flags would have to either edit the upstream tree, which the contract forbids,
or replace the mount. Replacing it requires the overlay.

The flag definitions are not vendored. `up` copies them from the checkout into
`.demo-state/flagd/`, keeping 172 lines of upstream content out of the
repository and removing the need to resynchronise them on every version bump.

## Deviation from the forecast

The operations were forecast as `scripts/demo.sh` and are delivered as
`scripts/demo_env.py`: the repository implements validation logic in Python,
reserves shell for thin helpers, and CI runs `shellcheck` over the shell files
that exist. The script is not added to `ci.yml`, since the operations require a
running daemon and a started environment that CI does not provide.

## Corrected finding: the injected failure is observable

An earlier version of this file reported that `paymentUnreachable` left no
metric to read. That measurement was taken while no synthetic traffic reached
the store (see the port defect under the findings already fixed), so it
described an idle environment, not a degraded one. It is withdrawn.

Measured again on the reference host with traffic reaching the store, over two
`fail`, `verify`, `reset` cycles: 5xx responses at the proxy stay flat in
baseline and after each `reset`, and rise only while the flag is on. That
separates the two states. The manual check still holds: with the flag on, an
order placed in the store does not complete, and after `reset` it does.

Measuring it exposed a defect in `reset`. flagd already served the baseline, but
the store kept failing for more than 80 seconds, until `checkout` was restarted:
its flagd provider kept a cached evaluation across the flagd restart.
`compose.demo.yaml` now sets `FLAGD_CACHE=disabled` for `checkout`, and with it
both cycles restored cleanly.

`verify` still reports availability only and does not read this signal. Whether
that check belongs to this issue or to a separate one is pending with the
product owner, so CA4 stays open.

## Findings already fixed

Four defects were found by running the operations rather than reading them, and
were corrected in 2a: operations hung silently when the Docker daemon was not
running, the flag working copy leaked a previous session's state into a
supposedly clean start, verification approved the environment while checking
only six of its services, and the synthetic traffic never reached the store
because k6 targeted the proxy's upstream port instead of 8090.
