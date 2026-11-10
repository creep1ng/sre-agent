# Proposal: OpenTelemetry Demo Environment

## Intent

Pin a reproducible OpenTelemetry Demo deployment that the incident vertical can start, degrade on purpose, observe and restore on demand. Issue #186 blocks #45, #51 and #52: without a fixed environment, investigation runs cannot be repeated or compared across sessions.

## Scope

### In Scope

- Pin OpenTelemetry Demo to tag `3.0.0` (commit `1755859`) by image tag, with a companion digest lock that `verify` checks for registry drift.
- Compose the demo externally from `compose.yaml` and `compose.observability.yaml` under a dedicated Compose project, without modifying upstream files.
- Declare host prerequisites: published ports, memory footprint and disk footprint.
- Define `up`, `fail`, `verify`, `reset` and `down` as idempotent operations bounded to the demo project.
- Drive failure injection through flagd using `paymentUnreachable`, while synthetic traffic keeps running.
- Restore a declared flag baseline on `reset` instead of switching every flag off.

### Out of Scope

- Grafana MCP and its network boundary: delivered by a later PR of this change.
- Governed `harness -> gateway -> MCP` reachability, conditioned on #187 and non-blocking for this environment.
- Signal contract integration with #149; starting the base environment does not wait for it.
- Running the upstream agent, MCP, chatbot, full, profiling or test layers.
- Real remediation, mandatory Loki/Tempo, universal ingestion, anomaly detection.

## Capabilities

### New Capabilities

- `demo-environment`: reproducible external composition of OpenTelemetry Demo with bounded lifecycle operations and observable failure injection.

### Modified Capabilities

None.

## Approach

Leave the upstream demo untouched and drive it from outside. A manifest declares version, included layers, services, ports and host requirements; a lock file records the image digests validated on 2026-09-12. Operations run against a dedicated Compose project named `otel-demo`, which isolates networks and volumes from the project's own stack, so `reset` cannot reach `postgres_data` and the seeded principals.

Two upstream properties shape the design and were confirmed on a real host. First, the pinned tag ships `DEMO_VERSION=latest`, so pinning the repository does not pin the images; the manifest overrides the variable explicitly. Second, the demo hardcodes `container_name` for all 25 services in the minimal profile, and container names are global to the Docker daemon; project isolation therefore covers networks and volumes but not names, so `up` verifies the absence of residue instead of assuming it.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `demo/manifest.yaml` | Added | Version, layers, services, ports, host prerequisites |
| `demo/digests.lock` | Added | Validated image digests for drift detection |
| `demo/demo.env` | Added | Project overrides applied after the upstream env file |
| `scripts/demo.sh` | Added, later PR | Implementation of the five operations |
| `docs/demo-env.md` | Added, later PR | Operator guide and signal guide |
| `compose.demo.yaml` | Added, later PR | Additive overlay carrying Grafana MCP and its network boundary |
