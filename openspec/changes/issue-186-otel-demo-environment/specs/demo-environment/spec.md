# Demo Environment Specification

## Purpose

Define a reproducible OpenTelemetry Demo deployment that incident investigation runs can start, degrade on purpose, observe and restore, without modifying the upstream project and without reaching resources outside the demo.

## Requirements

### Requirement: Pin the environment reproducibly

The environment MUST declare an upstream tag and commit, and MUST pin container images explicitly. Pinning the repository alone is NOT sufficient, because upstream defaults resolve images to a moving tag. A lock file MUST record the digests validated for the declared version, and verification MUST compare current digests against it.

#### Scenario: Declared version is the version that runs

- GIVEN a clean host and the declared manifest
- WHEN the environment starts
- THEN every demo image resolves to the pinned version and none to a moving tag

#### Scenario: Registry drift is detected

- GIVEN a recorded digest lock
- WHEN an upstream tag has been repointed to different content
- THEN verification reports the mismatch and names the affected image

### Requirement: Compose the demo externally

The environment MUST be composed from outside the upstream project. Upstream files MUST NOT be modified, and the upstream agent, full, profiling and test layers MUST NOT be started.

#### Scenario: Upstream tree is unchanged

- GIVEN a checkout of the pinned tag
- WHEN the environment has been started and stopped
- THEN the upstream working tree reports no modifications

#### Scenario: Excluded layers never run

- GIVEN a started environment
- WHEN running services are listed
- THEN no upstream agent, MCP, chatbot, Kafka, profiling or test service is present

### Requirement: Bound every operation to the demo project

Operations MUST act only on the dedicated Compose project. They MUST NOT remove volumes, networks or containers belonging to other projects, and MUST NOT invoke host-wide cleanup.

#### Scenario: Reset leaves foreign resources untouched

- GIVEN unrelated containers and volumes present on the host
- WHEN reset runs
- THEN those resources remain present and unchanged

#### Scenario: Start refuses to run over residue

- GIVEN a container from a previous demo instance still present
- WHEN start runs
- THEN it reports the conflicting name and stops instead of starting partially

### Requirement: Report availability from observable evidence

Verification MUST report availability for frontend, load generator, Collector, Grafana, Prometheus and OpenSearch, and MUST report real failures rather than assuming health. Availability of Grafana MCP is added by the change that introduces it.

#### Scenario: A degraded service is reported as failing

- GIVEN one required service is not healthy
- WHEN verification runs
- THEN it reports that service as failing and exits with a non-zero status

### Requirement: Inject failure without suppressing traffic

Failure injection MUST activate the declared flag through the feature flag provider while synthetic traffic continues, so that the resulting signals are observable.

#### Scenario: Traffic survives failure injection

- GIVEN a healthy environment with synthetic traffic running
- WHEN failure injection runs
- THEN the declared flag is active and the load generator is still producing requests

### Requirement: Restore a declared baseline

Reset MUST restore the flag baseline declared in the manifest rather than switching every flag off. Flags carrying a rate or targeting rules MUST be restored to their declared value.

#### Scenario: Baseline traffic is preserved across reset

- GIVEN a baseline in which synthetic traffic is enabled
- WHEN reset runs
- THEN synthetic traffic remains enabled and verification passes

#### Scenario: Two cycles are reproducible

- GIVEN a verified baseline
- WHEN failure injection, verification and reset run twice in sequence
- THEN the baseline is confirmed before the second failure and both cycles report the same outcome
