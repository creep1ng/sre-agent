# Apply progress

Delivery follows the chain declared in `tasks.md`, split further to keep each
pull request inside the size budget.

| PR | Scope | Deliverable | Status |
|---|---|---|---|
| 1 | Planning artifacts, manifest, digest lock, env overrides | 1 | Merged |
| 2a | Lifecycle: `up`, `verify`, `down`, composition overlay, operator guide | 2, partial | Merged |
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

## Open finding: the injected failure is not observable as a metric

CA2 asks for verifying a real signal and CA4 for two reproducible cycles. Both
need a check that separates a degraded environment from a healthy one. That
check is not part of this PR, because the signal it would read does not exist in
the form expected.

Measured on the reference host. The `checkout` service stops emitting series of
its own once the flag is on, so there is nothing to compare: a counter query
returns an empty vector rather than a low value. The load generator does emit
`user_checkout_multi` continuously, but it records the attempt whether or not
the payment succeeds: its rate went from 0.058 in baseline to 0.100 with the
failure injected, and every span stayed at `STATUS_CODE_UNSET`. Neither
direction nor status separates the two states.

The effect itself is real and was confirmed manually: with the flag on, placing
an order in the store does not complete, and after `reset` the same order
completes. What is missing is a programmatic reading of it. Two paths are worth
exploring, both of which need their own investigation: traces in Jaeger, which
show where the order stops, and logs in OpenSearch, which CA6 already requires
documenting.

Delivering `fail` and `reset` now keeps CA2 and CA3 available to the rest of the
vertical instead of holding them behind an unresolved verification.

## Findings already fixed

Four defects were found by running the operations rather than reading them, and
were corrected in 2a: operations hung silently when the Docker daemon was not
running, the flag working copy leaked a previous session's state into a
supposedly clean start, verification approved the environment while checking
only six of its services, and the synthetic traffic never reached the store
because k6 targeted the proxy's upstream port instead of 8090.
