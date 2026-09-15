# Demo environment operations

Operate the pinned OpenTelemetry Demo used by the incident vertical. The
environment is declared in `demo/manifest.yaml`; this page covers how to drive
it. Issue: #186.

## Prerequisites

- Docker Engine with Compose v2, **running**. Every operation probes the daemon
  first and stops with a readable message if it is unreachable.
- 4 CPUs, 4 GB of free memory, 15 GB of free disk. Observed on a reference host:
  2.8 GB of memory and 8.7 GB of images.
- Host ports 8090, 10000 and 9090 free.
- Python with `pyyaml`. On Windows the interpreter is `python` or `py`.

Nothing is prepared by hand: `up` clones the pinned tag into `otel-demo/`,
which git ignores.

## Operations

    python scripts/demo_env.py up|verify|down

| Operation | What it does |
|---|---|
| `up` | Clones the pinned tag if absent, refuses to run over residue, applies the flag baseline, starts the minimal profile and waits for health |
| `verify` | Checks every service of the project and compares image digests against `demo/digests.lock` |
| `down` | Stops the environment and confirms no container of the project survived |

All three are idempotent and bounded to the Compose project `otel-demo`. None
removes resources of another project, and none runs a host-wide cleanup such as
`docker system prune`.

`fail` and `reset`, and the signal check that tells a degraded environment from
a healthy one, arrive in the follow-up PR of this change.

## Typical run

    python scripts/demo_env.py up
    python scripts/demo_env.py verify
    python scripts/demo_env.py down

`verify` exits non-zero when a service is unavailable or a digest no longer
matches the lock, so the sequence can be scripted.

## Where the state lives

| Path | Purpose | Tracked |
|---|---|---|
| `otel-demo/` | Upstream checkout at the pinned tag | No |
| `.demo-state/flagd/` | Flag definitions the project owns and edits | No |
| `demo/manifest.yaml` | What the environment is made of | Yes |
| `demo/digests.lock` | Digests validated for the pinned version | Yes |
| `compose.demo.yaml` | Overlay mounting the owned flag directory | Yes |

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

**`down` confirms what it removed.** A `down` against a mismatched project name
returns success and removes nothing, so it checks afterwards that no container
labelled with the project survived.

## Reaching the services

Everything goes through the proxy on 8090: the store at the root, Grafana under
`/grafana`, Jaeger under `/jaeger/ui`, the flagd UI under `/feature`. Grafana,
Jaeger and OpenSearch are not published to the host.
