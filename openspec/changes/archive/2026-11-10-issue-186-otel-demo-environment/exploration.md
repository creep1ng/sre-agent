# Exploration: OpenTelemetry Demo Environment

Validated on 2026-09-12 against a disposable clone outside the repository. Host: Docker 27.0.3, Compose v2.28.1, 8 CPUs, 8.25 GB VM, 150.9 GB free disk.

## Version selection

Upstream stopped prefixing tags with `v` after the 1.2.x generation. Requesting `v1.2.1` clones a valid tag from an older generation that predates `compose.yaml`, and git reports no error; composition then fails with a missing-file error and Compose falls back to a legacy `docker-compose.yml`.

`3.0.0`, released 2026-07-24, is the first release with modular Compose layers passed through `-f`. That is the mechanism this change needs to select a profile without editing upstream files; `2.2.0` is monolithic and would require hand-built composition. Layer selection and exclusions are recorded in `demo/manifest.yaml`.

## Image pinning

Resolved composition initially produced `demo:latest-<service>` for all 19 demo images despite the tag checkout. The reference is built from `${IMAGE_NAME}:${DEMO_VERSION}-<service>` and the upstream `.env` sets `DEMO_VERSION=latest`. `IMAGE_VERSION`, also present, feeds the `service.version` resource attribute and does not affect the image tag.

Overriding `DEMO_VERSION` resolves all 19 to the pinned version. The registry publishes per-service tags at that version, so digest-only pinning inside the composition is unnecessary. Under `latest`, `payment` remained in a restart loop; under `3.0.0` it reaches healthy.

## Ports

Three upstream variables reference 8080, which the project's `web` service already uses: `ENVOY_PORT`, `FRONTEND_PORT` and `PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`. The last is used by the browser to export its own telemetry; left unchanged while the proxy moves, the frontend would post traces at the project's `web` service.

With the declared overrides the resolved composition publishes exactly three host ports. A search of the project's own composition found no use of 9090 or 10000.

## Isolation

The 25 services declare fixed `container_name` values, and container names are global to the Docker daemon, so a dedicated project isolates networks and volumes but not names. A pre-existing instance blocked a new one: the start attempt failed at `flagd` after creating four containers.

A `docker compose down` invoked with a project name that does not match the running instance returns success and removes nothing. Cleanup required removing the 25 containers by explicit name, then the network. Host-wide cleanup was deliberately avoided: the host carries six unrelated containers from other projects, including a `postgres`.

## Measurements and functional evidence

Cold `pull` of 24 images took 1m40s; `up` with images cached took 57s. Memory settled at ~2.8 GB with opensearch the largest consumer at 824 MiB, leaving roughly 5.4 GB for the gateway and harness. Images occupy ~8.7 GB.

All four entry points served through the proxy responded: store, Grafana with 10 provisioned dashboards, Jaeger, and the flagd UI with 15 flags. Jaeger reported 17 services emitting traces, which demonstrates telemetry flowing end to end rather than containers merely reaching a healthy state. `loadGeneratorTraffic` is the only flag shipped `on`; two flags are rate-based and one carries targeting rules.
