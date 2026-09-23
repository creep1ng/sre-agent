# Demo environment operations

Operate the pinned OpenTelemetry Demo used by the incident vertical. The
environment is declared in `demo/manifest.yaml`; this page covers how to drive
it. Issue: #186.

## Prerequisites

- Docker Engine with Compose 2.24 or later, **running**. The overlay uses the
  `!reset` tag, and every operation probes the daemon first and stops with a
  readable message if it is unreachable.
- 4 CPUs, 4 GB of free memory, 15 GB of free disk. Observed on a reference host:
  2.8 GB of memory and 8.7 GB of images.
- Host ports 8090 and 9090 free on `127.0.0.1`. Both are published on the
  loopback interface only, so the environment answers on this host and on no
  other machine. The Envoy admin interface is not published.
- Python with `pyyaml`. On Windows the interpreter is `python` or `py`.

Nothing is prepared by hand: `up` clones the pinned tag into `otel-demo/`,
which git ignores.

## Operations

    python scripts/demo_env.py up|fail|verify|reset|down

| Operation | What it does |
|---|---|
| `up` | Clones the pinned tag if absent, refuses to run over residue, applies the flag baseline, starts the minimal profile and waits for health |
| `fail` | Switches the declared failure flag on and restarts flagd; synthetic traffic keeps running |
| `verify` | Checks every service of the project, compares image digests against `demo/digests.lock`, rejects a host port that is undeclared or published outside its declared interface, and probes Grafana MCP |
| `reset` | Restores the flag baseline declared in the manifest and restarts flagd |
| `down` | Stops the environment and confirms no container of the project survived |

All five are idempotent and bounded to the Compose project `otel-demo`. None
removes resources of another project, and none runs a host-wide cleanup such as
`docker system prune`.

## Typical run

    python scripts/demo_env.py up
    python scripts/demo_env.py verify
    python scripts/demo_env.py fail
    python scripts/demo_env.py reset
    python scripts/demo_env.py down

`verify` exits non-zero when a service is unavailable, a digest no longer
matches the lock, a host port is undeclared or leaves its declared interface, or
Grafana MCP stops answering or accepts a caller without its token, so the
sequence can be scripted.

`verify` reports availability, not behaviour: it does not yet tell a degraded
environment from a healthy one. How the injected failure shows in metrics, logs
and traces, and how to read it, is in [demo-signals.md](demo-signals.md).

## Where the state lives

| Path | Purpose | Tracked |
|---|---|---|
| `otel-demo/` | Upstream checkout at the pinned tag | No |
| `.demo-state/flagd/` | Flag definitions the project owns and edits | No |
| `.demo-state/grafana-mcp.env` | Grafana MCP caller token, created by `up` | No |
| `demo/manifest.yaml` | What the environment is made of | Yes |
| `demo/digests.lock` | Digests validated for the pinned version | Yes |
| `compose.demo.yaml` | Overlay: owned flag directory, no flag cache in `checkout`, Grafana MCP, reset of undeclared host ports | Yes |

The upstream checkout stays pristine: `up` refuses to run if it reports local
modifications, and the flag working copy is never written back to it.

## Design notes

**`up` assumes nothing.** Container names are global to the Docker daemon, so
project isolation covers networks and volumes but not names; `up` reports
conflicts instead of failing halfway. It also applies the declared baseline
before starting, so a state left behind by an earlier session cannot leak into a
supposedly clean run.

**`verify` checks the whole project.** Approving an environment whose checkout
service is down would not report real failures, so every service of the
composition is checked. That is a superset of the six the acceptance criterion
names.

**`reset` is not a global switch-off.** `loadGeneratorTraffic` ships enabled and
sustains the traffic that failure injection needs; disabling it would leave the
environment without signals. `reset` restores the baseline declared in the
manifest, including flags that carry a rate or targeting rules.

**`checkout` evaluates flags without a cache.** Its flagd provider kept a cached
evaluation across the flagd restart, so the store went on failing after `reset`
until `checkout` itself was restarted. The overlay sets `FLAGD_CACHE=disabled`
for it, so `fail` and `reset` take effect without touching `checkout`.

**`down` confirms what it removed.** A `down` against a mismatched project name
returns success and removes nothing, so it checks afterwards that no container
labelled with the project survived.

## Grafana MCP

`grafana-mcp` runs `grafana/mcp-grafana` 1.3.0 inside the demo. It answers only
at `http://grafana-mcp:8000/mcp` (streamable HTTP), from a container on one of
its networks.

- **Read-only.** `--disable-write` plus three tool categories: `prometheus`,
  `elasticsearch` (the OpenSearch logs) and `datasource`. Ten tools, none of
  which writes. There is no Jaeger tool; follow a trace from its `trace_id`.
- **Caller token.** A request without `Authorization: Bearer` and the token in
  `.demo-state/grafana-mcp.env` gets HTTP 401. `up` creates the token and git
  ignores it. The gateway will hold it (#187); the harness must never receive it.
- **No published port.** A `Host` allowlist (`grafana-mcp:8000`) also answers
  HTTP 403 to any other host name.
- **Networks.** The demo network, to reach Grafana, and `sre-mcp-boundary`, an
  internal network reserved for the gateway. The project's `runtime` network,
  where the harness runs, is not attached: the harness can neither resolve nor
  route to the MCP.

The MCP reaches Grafana anonymously. Upstream grants the anonymous user Admin,
so read-only rests on `--disable-write`, not on Grafana; tightening Grafana is
pending. Do not paste the output of `docker compose config` as evidence: it
expands the token.

## Reaching the services

Everything goes through the proxy on `127.0.0.1:8090`: the store at the root,
Grafana under `/grafana`, Jaeger under `/jaeger/ui`, the flagd UI under
`/feature`. Upstream publishes most services on random host ports and the rest
on every interface; the overlay resets every publication the manifest does not
declare and binds the two it does to loopback, so Grafana, Jaeger and OpenSearch
are reachable only through the proxy, and the proxy only from this host.

Do not use the flagd UI to inject failures: it writes to the upstream file and
`reset` would not know about the change.
