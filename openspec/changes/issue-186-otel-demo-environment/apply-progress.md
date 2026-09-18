# Apply progress

Delivery follows the chain declared in `tasks.md`, split further to keep each
pull request inside the size budget.

| PR | Scope | Deliverable | Status |
|---|---|---|---|
| 1 | Planning artifacts, manifest, digest lock, env overrides | 1 | Merged |
| 2a | Lifecycle: `up`, `verify`, `down`, composition overlay, operator guide | 2, partial | Open, #273 |
| 2b | Failure cycle: `fail` and `reset` | 2, complete | Open, #275 |
| 3a | Grafana MCP, its network boundary, MCP and port checks in `verify` | 3 | This PR |
| 3b | Signal guide and sanitized output of two cycles | 4 | Pending |

PR 3 is split in two because the MCP boundary and the signal guide carry
different evidence and would not fit one review budget together.

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

## PR 3a findings

**Upstream published most services to the host.** The short port syntax used
upstream (`"3000"`) binds every host interface to a random port, so Grafana
with anonymous Admin, OpenSearch, flagd-ui and the store database were reachable
outside the proxy. Measured on the reference host: Grafana answered on
`0.0.0.0:58224`. That contradicted the manifest, which declared three host ports,
and was a bypass of both the proxy and Grafana MCP. The overlay now resets every
undeclared publication and `verify` fails if one reappears.

**The MCP was validated before writing the overlay**, with a disposable
container on the demo network: ten tools with the chosen categories and none
that writes, HTTP 401 without the caller token, Prometheus and OpenSearch
queries answered through Grafana's datasources, and a container outside the demo
network unable to resolve it. `query_elasticsearch` works against the
`grafana-opensearch-datasource` plugin the demo provisions. The image reports
its version as `(devel)`, so the pin rests on the digest in `demo/digests.lock`.

